const {test} = require('node:test');
const assert = require('node:assert/strict');
const {validateSettings} = require('./runtime_settings');
test('runtime settings support bounded concurrency changes',()=>{
  assert.equal(validateSettings({concurrency:48}).concurrency,48);
  for(const bad of [-1,0,65,2.5,'36']) assert.throws(()=>validateSettings({concurrency:bad}));
});
test('invalid delay and inverted timeouts are rejected',()=>{
  assert.throws(()=>validateSettings({codeDelayMs:0}));
  assert.throws(()=>validateSettings({codeTimeoutMs:3000,codeRetryTimeoutMs:2500}));
  assert.throws(()=>validateSettings({codeRounds:6}));
});
