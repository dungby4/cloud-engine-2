const {test}=require('node:test'),assert=require('node:assert/strict');const {parseServers:f}=require('../src/server_catalog');
const a={sid:'610084',name:'S84',server:'wss://example.test:9110/',status:'2'},b={sid:'610085',name:'S85',server:'wss://example.test:9111/',status:'1'};
test('latest server comes from current catalog rather than guessed port or old SID',()=>{assert.deepEqual(f([{all:[a,b]}]).map(x=>x.sid),['610085','610084']);assert.equal(f([b,a])[0].wsUrl,b.server);});
test('invalid addresses, duplicate servers and empty catalog cannot invent a new server',()=>{assert.equal(f({all:[a,a,{sid:'610086',server:'http://invalid.test'}]}).length,1);assert.deepEqual(f({}),[]);});
