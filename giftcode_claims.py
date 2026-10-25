"""Sequential giftcode requests over a connection whose ACK has no request ID."""

import asyncio
import math
import random
import re
import struct
import weakref
from websockets.exceptions import ConnectionClosed

_LOOP_NEXT_CDK_SEND = weakref.WeakKeyDictionary()
_GLOBAL_MIN_CDK_GAP = 0.145


class GiftcodeClaims:
  def __init__(self, min_interval=0.48, timeout=2.40, max_attempts=4, reconnect_on_timeout=False):
    self.min_interval = min_interval
    self.timeout = timeout
    self.max_attempts = max_attempts
    self.reconnect_on_timeout = reconnect_on_timeout
    self.confirmed = set()
    self.errors = {}
    self.needs_reconnect = False
    self._pending = None
    self._attempt = 0
    self._had_retry = False
    self._event = asyncio.Event()
    self._next_send = 0.0
    self._retry_after = 0.0
    self._terminal = False
    self._abort = False
    self._last_notice = ""
    self._consec_timeouts = 0

  def new_connection(self):
    self._pending = None
    self.needs_reconnect = False
    self._had_retry = False
    self._event.clear()

  def record_packet(self, packet):
    if not self._pending or self.needs_reconnect or self._event.is_set():
      return
    if not isinstance(packet, bytes) or len(packet) < 4:
      return
    size, msg_id = struct.unpack(">HH", packet[:4])
    if len(packet) != size + 4:
      return
    if msg_id == 144:
      self.confirmed.add(self._pending)
      self.errors.pop(self._pending, None)
      self._had_retry = self._attempt >= 1
      self._event.set()
    elif msg_id == 10 and size >= 10:
      # GC_BROADCAST(int, int, string), as decoded by the game client.
      text_size = struct.unpack_from(">H", packet, 12)[0]
      if text_size != size - 10:
        return
      message = packet[14:].decode("utf-8", errors="replace")
      self._last_notice = message
      if message.startswith("已达到领取上限"):
        # If the previous code required retries and we are on attempt 0 of a new code,
        # this notice is a trailing duplicate reply from the previous code's retry.
        if self._attempt == 0 and self._had_retry:
          return
        self.confirmed.add(self._pending)
        self.errors.pop(self._pending, None)
        self._had_retry = self._attempt >= 1
        self._event.set()
      elif message.startswith("操作过于频繁"):
        # The client's string formatter substitutes || arguments into {1}.
        seconds = re.search(r"\|\|(\d+(?:\.\d+)?)", message)
        self._retry_after = float(seconds[1]) if seconds else 1.5
        self.errors[self._pending] = message
        if not math.isfinite(self._retry_after) or self._retry_after > 60:
          # Do not retry sooner than requested or leave a worker waiting forever.
          self._abort = True
          self.errors[self._pending] = "Dừng nhập code: thời gian chờ server vượt 60s"
        self._event.set()
      elif message == "过期的，老君拒收！":
        self._terminal = True
        self.errors[self._pending] = message
        self._event.set()
      # Success notices precede ACK 144. Other broadcasts aren't CDK replies.

  async def _pause(self, seconds, stopped):
    end = asyncio.get_running_loop().time() + seconds
    while not stopped():
      remaining = end - asyncio.get_running_loop().time()
      if remaining <= 0:
        return True
      await asyncio.sleep(min(0.05, remaining))
    return False

  async def claim_all(self, codes, send, reconnect, stopped, progress):
    if self._abort:
      return
    loop = asyncio.get_running_loop()
    for index, code in enumerate(codes, 1):
      if code in self.confirmed:
        continue
      for attempt in range(self.max_attempts):
        if attempt >= 2 and self._consec_timeouts >= 5:
          break
        if stopped():
          return
        now = loop.time()
        global_next = _LOOP_NEXT_CDK_SEND.get(loop, 0.0)
        slot_ts = max(now, self._next_send, global_next)
        _LOOP_NEXT_CDK_SEND[loop] = slot_ts + _GLOBAL_MIN_CDK_GAP
        if not await self._pause(max(0.0, slot_ts - now), stopped):
          return
        self._retry_after = 0.0
        self._terminal = False
        self._last_notice = ""
        reconnecting = self.needs_reconnect
        try:
          if reconnecting:
            await reconnect()
            self.new_connection()
          self._pending = code
          self._attempt = attempt
          self._event.clear()
          progress(index, len(codes), code, attempt + 1)
          await send(code)
          self._next_send = loop.time() + self.min_interval
          await asyncio.wait_for(self._event.wait(), self.timeout)
          self._next_send = max(self._next_send, loop.time() + min(0.08, self.min_interval))
        except asyncio.TimeoutError:
          self.errors[code] = ("Hết thời gian chờ kết nối lại" if reconnecting and not self._pending
                               else "Hết thời gian chờ xác nhận") + (
              f"; thông báo gần nhất: {self._last_notice}" if self._last_notice else ""
          )
          if self.reconnect_on_timeout or (reconnecting and not self._pending):
            self.needs_reconnect = True
        except (OSError, ConnectionClosed) as error:
          self.errors[code] = f"Lỗi kết nối giftcode: {type(error).__name__}"
          self.needs_reconnect = True
        finally:
          self._pending = None
        if self._abort:
          return
        if code in self.confirmed or self._terminal:
          if code in self.confirmed:
            self._consec_timeouts = 0
          break
        if self._retry_after > 0:
          backoff = self._retry_after + random.uniform(0.05, 0.20)
        elif self.reconnect_on_timeout:
          backoff = self.min_interval * 2 ** (attempt + 1) + random.uniform(0.05, 0.20)
        else:
          backoff = 0.50 + attempt * 0.35 + random.uniform(0.05, 0.18)
        self._next_send = max(self._next_send, loop.time() + backoff)
      if code not in self.confirmed and not self._terminal:
        self._consec_timeouts += 1
