import ast
import asyncio
from collections import Counter
from pathlib import Path
import struct
import sys
import json
import random
import re
import ssl
import threading
import time
from types import SimpleNamespace
import unittest

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from giftcode_claims import GiftcodeClaims


ACK = struct.pack(">HH", 0, 144)


def notice(text):
  raw = text.encode("utf-8")
  return struct.pack(">HHiiH", 10 + len(raw), 10, 0, 0, len(raw)) + raw


class GiftcodePacketTests(unittest.TestCase):
  def setUp(self):
    self.claims = GiftcodeClaims()
    self.claims._pending = "FIRST"

  def test_unrelated_broadcast_does_not_finish_request(self):
    self.claims.record_packet(notice("Không đủ vé triệu hồi"))
    self.assertFalse(self.claims._event.is_set())
    self.assertEqual(self.claims.confirmed, set())

  def test_success_notice_waits_for_ack(self):
    self.claims.record_packet(notice("急急如律令，兑！请前往信件查收"))
    self.assertFalse(self.claims._event.is_set())
    self.claims.record_packet(ACK)
    self.assertEqual(self.claims.confirmed, {"FIRST"})

  def test_already_claimed_is_confirmed_without_ack(self):
    self.claims.record_packet(notice("已达到领取上限，再薅，天庭都要秃了"))
    self.assertEqual(self.claims.confirmed, {"FIRST"})

  def test_rate_limit_is_failure_with_server_cooldown(self):
    self.claims.record_packet(notice("操作过于频繁，请{1}秒后再试||2.5"))
    self.assertTrue(self.claims._event.is_set())
    self.assertEqual(self.claims._retry_after, 2.5)
    self.assertEqual(self.claims.confirmed, set())

  def test_expired_code_is_failure(self):
    self.claims.record_packet(notice("过期的，老君拒收！"))
    self.assertTrue(self.claims._terminal)
    self.assertEqual(self.claims.confirmed, set())

  def test_unbounded_cooldown_aborts_instead_of_waiting_forever(self):
    self.claims.record_packet(notice("操作过于频繁，请{1}秒后再试||" + "9" * 400))
    self.assertTrue(self.claims._abort)
    self.assertTrue(self.claims._event.is_set())
    self.assertEqual(self.claims.confirmed, set())

  def test_late_reply_on_tainted_connection_is_ignored(self):
    self.claims.needs_reconnect = True
    self.claims.record_packet(ACK)
    self.assertEqual(self.claims.confirmed, set())

  def test_malformed_packets_are_ignored(self):
    for packet in ("text", b"", ACK + b"extra", notice("test")[:-1]):
      self.claims.record_packet(packet)
    self.assertFalse(self.claims._event.is_set())


class GiftcodeWireTests(unittest.IsolatedAsyncioTestCase):
  async def exchange(self, handler, codes, claims=None, stopped=lambda: False, sent_times=None):
    claims = claims or GiftcodeClaims(min_interval=0.01, timeout=0.10)
    server_connections = []

    async def handle(ws):
      server_connections.append(ws)
      async for packet in ws:
        size, msg_id, text_size = struct.unpack(">HHH", packet[:6])
        self.assertEqual(msg_id, 143)
        self.assertEqual(size, text_size + 2)
        await handler(ws, packet[6:].decode("utf-8"), len(server_connections))

    async with websockets.serve(handle, "127.0.0.1", 0) as server:
      address = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
      connection = None
      reader = None
      reconnect_count = 0

      async def receive(ws):
        async for packet in ws:
          claims.record_packet(packet)

      async def reconnect():
        nonlocal connection, reader, reconnect_count
        if reader is not None:
          reconnect_count += 1
          reader.cancel()
          await asyncio.gather(reader, return_exceptions=True)
          await connection.close()
        connection = await websockets.connect(address)
        reader = asyncio.create_task(receive(connection))

      async def send(code):
        raw = code.encode("utf-8")
        if sent_times is not None:
          sent_times.append(asyncio.get_running_loop().time())
        await connection.send(struct.pack(">HHH", len(raw) + 2, 143, len(raw)) + raw)

      await reconnect()
      try:
        await claims.claim_all(codes, send, reconnect, stopped, lambda *args: None)
        return claims, reconnect_count
      finally:
        reader.cancel()
        await asyncio.gather(reader, return_exceptions=True)
        await connection.close()

  async def test_minimum_spacing_even_with_immediate_acks(self):
    sent_at = []

    async def handler(ws, code, connection):
      await ws.send(ACK)

    claims, reconnects = await self.exchange(
        handler, ["FIRST", "SECOND", "THIRD"],
        GiftcodeClaims(min_interval=0.04, timeout=0.2),
        sent_times=sent_at,
    )
    self.assertEqual(claims.confirmed, {"FIRST", "SECOND", "THIRD"})
    self.assertTrue(all(b - a >= 0.04 for a, b in zip(sent_at, sent_at[1:])), sent_at)
    self.assertEqual(reconnects, 0)

  async def test_unrelated_notice_cannot_release_next_code(self):
    received = []

    async def handler(ws, code, connection):
      received.append(code)
      await ws.send(notice("Không đủ vé triệu hồi"))
      await asyncio.sleep(0.03)
      self.assertEqual(received[-1], code)
      await ws.send(ACK)

    claims, _ = await self.exchange(handler, ["FIRST", "SECOND"])
    self.assertEqual(claims.confirmed, {"FIRST", "SECOND"})

  async def test_timeout_reconnects_and_retries_same_code(self):
    received = []

    async def handler(ws, code, connection):
      received.append((connection, code))
      if connection == 1:
        return  # No ACK: new code must not be sent on this socket.
      if code == "FIRST":
        await ws.send(notice("已达到领取上限，再薅，天庭都要秃了"))
      else:
        await ws.send(ACK)

    claims, reconnects = await self.exchange(handler, ["FIRST", "SECOND"])
    self.assertEqual(received, [(1, "FIRST"), (2, "FIRST"), (2, "SECOND")])
    self.assertEqual(claims.confirmed, {"FIRST", "SECOND"})
    self.assertEqual(claims.errors, {})
    self.assertEqual(reconnects, 1)

  async def test_rate_limit_waits_and_retries_without_reconnect(self):
    sent_at = []

    async def handler(ws, code, connection):
      sent_at.append(asyncio.get_running_loop().time())
      await ws.send(notice("操作过于频繁，请{1}秒后再试||0.12") if len(sent_at) == 1 else ACK)

    claims, reconnects = await self.exchange(handler, ["FIRST"])
    self.assertEqual(claims.confirmed, {"FIRST"})
    self.assertGreaterEqual(sent_at[1] - sent_at[0], 0.12)
    self.assertEqual(reconnects, 0)

  async def test_expired_code_is_not_retried_or_counted(self):
    received = []

    async def handler(ws, code, connection):
      received.append(code)
      await ws.send(notice("过期的，老君拒收！") if code == "EXPIRED" else ACK)

    claims, _ = await self.exchange(handler, ["EXPIRED", "SECOND"])
    self.assertEqual(received, ["EXPIRED", "SECOND"])
    self.assertEqual(claims.confirmed, {"SECOND"})
    self.assertEqual(claims.errors, {"EXPIRED": "过期的，老君拒收！"})

  async def test_exhausted_timeout_is_reported_and_next_code_uses_new_socket(self):
    received = []

    async def handler(ws, code, connection):
      received.append((connection, code))
      if code == "SECOND":
        await ws.send(ACK)

    claims, reconnects = await self.exchange(handler, ["FIRST", "SECOND"])
    self.assertEqual([code for _, code in received], ["FIRST"] * 3 + ["SECOND"])
    self.assertEqual(len({conn for conn, _ in received}), 4)
    self.assertEqual(claims.confirmed, {"SECOND"})
    self.assertIn("FIRST", claims.errors)
    self.assertEqual(reconnects, 3)

  async def test_stop_during_cooldown_sends_no_retry(self):
    stop = False
    received = []

    async def handler(ws, code, connection):
      nonlocal stop
      received.append(code)
      await ws.send(notice("操作过于频繁，请{1}秒后再试||10"))
      stop = True

    claims, _ = await self.exchange(handler, ["FIRST", "SECOND"], stopped=lambda: stop)
    self.assertEqual(received, ["FIRST"])
    self.assertEqual(claims.confirmed, set())

  async def test_excessive_cooldown_stops_codes_without_early_retry(self):
    received = []

    async def handler(ws, code, connection):
      received.append(code)
      await ws.send(notice("操作过于频繁，请{1}秒后再试||120"))

    claims, _ = await asyncio.wait_for(self.exchange(handler, ["FIRST", "SECOND"]), 2)
    self.assertEqual(received, ["FIRST"])
    self.assertIn("FIRST", claims.errors)
    self.assertEqual(claims.confirmed, set())

  async def test_send_failure_reconnects_and_retries_same_code(self):
    claims = GiftcodeClaims(min_interval=0, timeout=0.1)
    sent = []
    reconnects = []

    async def send(code):
      sent.append(code)
      if len(sent) == 1:
        raise ConnectionError("connection lost during send")
      claims.record_packet(ACK)

    async def reconnect():
      reconnects.append(True)

    await claims.claim_all(["FIRST", "SECOND"], send, reconnect, lambda: False, lambda *args: None)
    self.assertEqual(sent, ["FIRST", "FIRST", "SECOND"])
    self.assertEqual(len(reconnects), 1)
    self.assertEqual(claims.confirmed, {"FIRST", "SECOND"})
    self.assertEqual(claims.errors, {})

  async def test_transient_reconnect_failure_is_retried(self):
    claims = GiftcodeClaims(min_interval=0, timeout=0.1)
    sent = []
    reconnects = []

    async def send(code):
      sent.append(code)
      if len(sent) == 1:
        raise ConnectionError("connection lost during send")
      claims.record_packet(ACK)

    async def reconnect():
      reconnects.append(True)
      if len(reconnects) == 1:
        raise ConnectionError("transient login failure")

    await claims.claim_all(["FIRST", "SECOND"], send, reconnect, lambda: False, lambda *args: None)
    self.assertEqual(sent, ["FIRST", "FIRST", "SECOND"])
    self.assertEqual(len(reconnects), 2)
    self.assertEqual(claims.confirmed, {"FIRST", "SECOND"})
    self.assertEqual(claims.errors, {})

  async def test_36_accounts_keep_confirmations_separate(self):
    codes = [f"CODE{index}" for index in range(28)]
    received = Counter()

    async def handler(ws, code, connection):
      received[code] += 1
      await ws.send(ACK)

    results = await asyncio.gather(*(self.exchange(
        handler, codes, GiftcodeClaims(min_interval=0.005, timeout=2),
    ) for _ in range(36)))
    self.assertTrue(all(claims.confirmed == set(codes) for claims, _ in results))
    self.assertEqual(received, Counter({code: 36 for code in codes}))


class RerollIntegrationTests(unittest.IsolatedAsyncioTestCase):
  async def test_reconnect_keeps_account_and_does_not_duplicate_heroes(self):
    # Loading only these definitions avoids the app's startup vault migration.
    source = Path(__file__).resolve().parents[1] / "chay_web_auto.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names = {"_reroll_single_account", "_pkt_msg", "_pkt_str", "_parse_hero_gt", "_parse_hero_packet"}
    selected = [node for node in tree.body if getattr(node, "name", None) in names]
    code_node = next(node for node in tree.body if isinstance(node, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == "REROLL_GIFTCODES" for t in node.targets))
    codes = ast.literal_eval(code_node.value)
    auth_requests = []

    def auth(account, token):
      auth_requests.append((account, token))
      return {"timestamp": 1, "authKey": "test-auth"}

    def connect(uri, **kwargs):
      # TLS is the only difference from the real caller's transport settings.
      kwargs.pop("ssl")
      return websockets.connect(uri, **kwargs)

    ns = dict(asyncio=asyncio, struct=struct, json=json, random=random, re=re,
              ssl=ssl, time=time, REROLL_LOCK=threading.Lock(),
              REROLL_STATE={"stopRequested": False}, VN_LANG_MAP={}, PORT=8088,
              REROLL_GIFTCODES=codes, fetch_fresh_authkey=auth,
              websockets=SimpleNamespace(connect=connect),
              GiftcodeClaims=lambda: GiftcodeClaims(min_interval=0.005, timeout=0.2))
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), "exec"), ns)
    pkt_str = ns["_pkt_str"]
    pkt_msg = ns["_pkt_msg"]
    hero = (struct.pack(">i", 3001) + pkt_str("hero-uid") + pkt_str("test hero")
            + pkt_str("") + bytes(20) + bytes([5, 0, 0]))
    snapshot = pkt_msg(38, struct.pack(">H", 8) + hero * 8)
    connections = 0
    logins = []
    code_requests = []

    async def handler(ws):
      nonlocal connections
      connections += 1
      connection_id = connections
      async for packet in ws:
        msg_id = struct.unpack_from(">H", packet, 2)[0]
        if msg_id == 56:
          logins.append(packet)
          await ws.send(snapshot)
          await ws.send(pkt_msg(599, b"\0"))
        elif msg_id == 143:
          code = packet[6:].decode()
          code_requests.append((connection_id, code))
          if connection_id > 1:
            await ws.send(notice("已达到领取上限，再薅，天庭都要秃了") if code == codes[0] else ACK)

    async with websockets.serve(handler, "127.0.0.1", 0) as server:
      address = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
      result = await ns["_reroll_single_account"](
          {"username": "test-account", "password": "test-password", "accountId": "123", "accessToken": "test-token"},
          {"sid": "610074", "server": address, "name": "test server"}, "test",
      )
    self.assertEqual(connections, 2)
    self.assertEqual(auth_requests, [("123", "test-token")] * 2)
    self.assertEqual(logins[0], logins[1])
    self.assertEqual(code_requests, [(1, codes[0])] + [(2, code) for code in codes])
    self.assertEqual(result["codesClaimed"], "28/28")
    self.assertEqual(result["unconfirmedCodes"], [])
    self.assertEqual(result["codeErrors"], {})
    self.assertEqual(len(result["heroes5Star"]), 8)


if __name__ == "__main__":
  unittest.main()
