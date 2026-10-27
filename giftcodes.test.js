const assert = require('node:assert/strict');
const { test } = require('node:test');
const { redeemGiftcodes } = require('./giftcodes');
const fast = {pause: async () => {}};
test('attempts every code and retries only missing responses', async () => {
  const calls = [];
  const r = await redeemGiftcodes(['A','B','C'], async code => {
    calls.push(code);
    return {sent:true,responseObserved:code !== 'B' || calls.filter(c=>c==='B').length===2};
  }, fast);
  assert.deepEqual(calls,['A','B','C','B']);
  assert.equal(r.sentCount,3); assert.equal(r.responseCount,3);
});
test('a sent request without a response remains unconfirmed', async () => {
  const r = await redeemGiftcodes(['A'], async () => ({sent:true,responseObserved:false}),fast);
  assert.equal(r.sentCount,1); assert.equal(r.responseCount,0);
  assert.equal(r.details[0].attempts,3); assert.deepEqual(r.unconfirmedCodes,['A']);
});
test('a disconnected request is never counted as sent', async () => {
  const r = await redeemGiftcodes(['A'], async () => {throw Error('Socket closed')},fast);
  assert.equal(r.sentCount,0); assert.equal(r.responseCount,0);
  assert.deepEqual(r.unconfirmedCodes,['A']);
});

test('general mail toasts cannot confirm a giftcode', () => {
  const {classifyGiftcodeNotice} = require('./giftcodes');
  assert.equal(classifyGiftcodeNotice('Đã nhận tệp đính kèm'),null);
  assert.equal(classifyGiftcodeNotice('Không thể dùng'),null);
  assert.equal(classifyGiftcodeNotice('Đã nhận tối đa rồi! Hốt nữa là Thiên Đình bị vặt sạch lông luôn!'),'already_claimed');
  assert.equal(classifyGiftcodeNotice('Mã hết hạn'),'rejected');
});
test('already claimed codes are preserved as terminal responses without retry', async () => {
  let calls = 0;
  const r=await redeemGiftcodes(['A'],async()=>{calls++;return {sent:true,responseObserved:true,status:'already_claimed',message:'Đã nhận tối đa rồi!'}},fast);
  assert.equal(calls,1); assert.equal(r.details[0].status,'already_claimed'); assert.equal(r.responseCount,1);
});
test('a saved confirmed response avoids resending that code', async () => {
  const calls=[];
  const r=await redeemGiftcodes(['A','B'],async code=>{calls.push(code);return {sent:true,responseObserved:true,status:'redeemed'}},{...fast,previous:[{code:'A',sent:true,responseObserved:true,status:'already_claimed',attempts:1}]});
  assert.deepEqual(calls,['B']); assert.equal(r.responseCount,2); assert.equal(r.details[0].reused,true);
});
test('an unconfirmed saved request must still be sent again', async () => {
  let calls=0;
  await redeemGiftcodes(['A'],async()=>{calls++;return {sent:true,responseObserved:true,status:'redeemed'}},{...fast,previous:[{code:'A',sent:true,responseObserved:false,status:'unconfirmed'}]});
  assert.equal(calls,1);
});
test('raw Chinese notices distinguish claimed, expired and throttled',()=>{
 const {giftcodeNoticeOutcome:f}=require('./giftcodes');
 assert.equal(f('已达到领取上限').status,'already_claimed');
 assert.equal(f('过期的，老君拒收！').status,'rejected');
 assert.deepEqual(f('操作过于频繁||2').retryAfterMs,2000);
 assert.equal(f('操作过于频繁||2').responseObserved,false);
 assert.equal(f('Thư mới'),null);
});
test('ambiguous socket halts batch without assigning a late ACK to next code',async()=>{
 const calls=[];const r=await redeemGiftcodes(['A','B'],async code=>{calls.push(code);return {sent:true,responseObserved:false,halt:true};},fast);
 assert.deepEqual(calls,['A']);assert.equal(r.halted,true);assert.deepEqual(r.unconfirmedCodes,['A','B']);
});
test('server wait longer than cap defers batch without shortening wait',async()=>{
 const waits=[];const r=await redeemGiftcodes(['A','B'],async()=>({sent:true,responseObserved:false,retryAfterMs:61000}),{pause:async ms=>waits.push(ms)});
 assert.equal(r.halted,true);assert.equal(waits.includes(61000),false);assert.equal(r.responseCount,0);
});
