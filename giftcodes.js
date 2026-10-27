async function redeemGiftcodes(codes, send, options = {}) {
  const rounds = options.rounds ?? 3;
  const timeoutMs = options.timeoutMs ?? 3000;
  const pause = options.pause ?? (ms => new Promise(r => setTimeout(r, ms)));
  const previous = new Map((options.previous || []).filter(x => x && x.responseObserved && ['redeemed','already_claimed','rejected'].includes(x.status)).map(x => [x.code,x]));
  const details = new Map(codes.map(code => [code, previous.has(code) ? {...previous.get(code), reused:true} : { code, attempts: 0, sent: false, responseObserved: false }]));
  let halted = false;
  for (let round = 0; round < rounds; round++) {
    for (const item of details.values()) {
      if (halted) break;
      if (item.responseObserved) continue;
      item.attempts++;
      try {
        const outcome = await send(item.code, timeoutMs + round * (options.timeoutStepMs ?? 1000));
        item.sent ||= outcome.sent;
        item.responseObserved = !!outcome.responseObserved;
        if (outcome.status) item.status = outcome.status;
        if (outcome.halt) halted = true;
        if (outcome.retryAfterMs > 0) {
          if (!Number.isFinite(outcome.retryAfterMs) || outcome.retryAfterMs > 60000) halted = true;
          else await pause(outcome.retryAfterMs);
        }
        if (outcome.message) item.message = outcome.message;
        if (outcome.error) item.error = outcome.error;
        else delete item.error;
      } catch (err) { item.error = err.message; }
      await pause(options.intervalMs ?? 80);
    }
    if (halted) break;
    if ([...details.values()].every(x => x.responseObserved)) break;
    if (round + 1 < rounds) await pause(500 + round * 500);
  }
  const rows = [...details.values()];
  return {
    halted,
    sentCount: rows.filter(x => x.sent).length,
    responseCount: rows.filter(x => x.responseObserved).length,
    unconfirmedCodes: rows.filter(x => !x.responseObserved).map(x => x.code),
    details: rows
  };
}
function classifyGiftcodeNotice(message) {
  if (/已达到领取上限|đã nhận tối đa|đã sử dụng.*mã|mã.*đã sử dụng/i.test(message)) return 'already_claimed';
  if (/过期的，老君拒收！|mã.*(hết hạn|không tồn tại|không hợp lệ)|giftcode.*(expired|invalid)/i.test(message)) return 'rejected';
  return null;
}
function giftcodeNoticeOutcome(message) {
  if (/操作过于频繁|thao tác.*(quá nhanh|quá thường xuyên)/i.test(message)) {
    const seconds = /\|\|(\d+(?:\.\d+)?)/.exec(message);
    return {responseObserved:false,status:'rate_limited',retryAfterMs:seconds ? Number(seconds[1])*1000 : 1500,message};
  }
  const status=classifyGiftcodeNotice(message);
  return status ? {responseObserved:true,status,message} : null;
}
module.exports = { redeemGiftcodes, classifyGiftcodeNotice, giftcodeNoticeOutcome };
