const fs = require('fs');
const path = require('path');
const DEFAULTS = {concurrency:24,codeDelayMs:180,codeTimeoutMs:1800,codeRetryTimeoutMs:3000,codeRounds:2};
function validateSettings(value = {}) {
  const r = {...DEFAULTS};
  const bounds = {concurrency:[1,64],codeDelayMs:[140,1000],codeTimeoutMs:[1500,6000],codeRetryTimeoutMs:[2000,10000],codeRounds:[1,5]};
  for (const [key,[min,max]] of Object.entries(bounds)) {
    if (value[key] === undefined) continue;
    if (!Number.isInteger(value[key]) || value[key] < min || value[key] > max) throw Error(`Cấu hình ${key} phải từ ${min} đến ${max}`);
    r[key] = value[key];
  }
  if (r.codeRetryTimeoutMs < r.codeTimeoutMs) throw Error('Timeout retry phải >= timeout đầu');
  return r;
}
function readSettings(root = __dirname) {
  const p = path.join(root,'reroll_runtime.json');
  return validateSettings(fs.existsSync(p) ? JSON.parse(fs.readFileSync(p,'utf8')) : {});
}
module.exports = {readSettings,validateSettings,DEFAULTS};
