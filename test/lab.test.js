const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('fs');const os=require('os');const path=require('path');
const {plan}=require('../src/planner');const {invoke,retryAfter}=require('../src/retry');const {run}=require('../src/worker');const {readJSON}=require('../src/storage');
const accounts=Array.from({length:200},(_,i)=>({username:`example_${i}`,accId:String(i+1000),password:'TEST_ONLY'}));const noWait=async()=>{};
function state(){return fs.mkdtempSync(path.join(os.tmpdir(),'hactaydu-lab-test-'))}
test('20 plans have complete, non-overlapping stable coverage',()=>{
 const all=[];for(let shard=1;shard<=20;shard++)all.push(...plan(accounts,{sid:'610083',shards:20,shard}));
 assert.equal(all.length,accounts.length);assert.equal(new Set(all.map(x=>x.key)).size,accounts.length);
 assert.deepEqual(plan(accounts,{sid:'610083',shards:20,shard:3}).map(x=>x.key).sort(),plan(accounts.slice().reverse(),{sid:'610083',shards:20,shard:3}).map(x=>x.key).sort());
});
test('mapping an account ID never moves its username to another shard',()=>{
 const a={username:'mapping_example'};let original,mapped;
 for(let shard=1;shard<=20;shard++){if(plan([a],{sid:'610083',shards:20,shard}).length)original=shard;if(plan([{...a,accId:'123456'}],{sid:'610083',shards:20,shard}).length)mapped=shard}
 assert.equal(original,mapped);
});
test('protected username and ID are excluded, bad shard and duplicates fail closed',()=>{
 assert.equal(plan(accounts,{sid:'610083',protectedAccounts:[{username:accounts[0].username},{accId:accounts[1].accId}]}).length,198);
 assert.throws(()=>plan(accounts,{sid:'610083',shards:20,shard:0}));
 assert.throws(()=>plan([accounts[0],{...accounts[0],username:accounts[0].username.toUpperCase()}],{sid:'610083'}));
 assert.throws(()=>plan([{username:'a',accId:'1'},{username:'b',accId:'1'}],{sid:'610083'}));
});
test('registration-only persists verified creation and never calls reroll',async()=>{
 const dir=state();let reg=0,reroll=0;
 const adapters={register:async()=>{reg++;return {status:'REGISTER_SUCCESS',isNewAccountCreated:true,funid:'42'}},reroll:async()=>{reroll++;throw Error('must not run')}};
 const opts={mode:'reg',accounts:accounts.slice(0,2),stateDir:dir,live:true,pause:noWait,adapters};
 const report=await run(opts);assert.equal(reg,2);assert.equal(reroll,0);assert.equal(report.complete,2);
 const saved=readJSON(path.join(dir,'reg-registration.json'));assert.equal(saved.accounts[0].gameState,'not_checked');
 await run(opts);assert.equal(reg,2);
});
test('HTTP/login success alone cannot mark new registration',async()=>{
 const dir=state();const r=await run({mode:'reg',accounts:accounts.slice(0,1),stateDir:dir,live:true,pause:noWait,adapters:{register:async()=>({status:'REGISTER_SUCCESS',httpStatus:200})}});
 assert.equal(r.complete,0);assert.equal(readJSON(path.join(dir,'reg-registration.json')).accounts.length,0);
});
test('verification stops the batch without rotating workers',async()=>{
 let calls=0;const r=await run({mode:'reg',accounts,stateDir:state(),live:true,pause:noWait,adapters:{register:async()=>{calls++;return {status:'VERIFICATION_REQUIRED',requiresCaptcha:true}}}});
 assert.equal(calls,1);assert.equal(r.halted,true);
});
test('rate limit honors Retry-After and stops after bounded retries',async()=>{
 let calls=0;const waits=[];const r=await invoke(async()=>{calls++;return {httpStatus:429,status:'RATE_LIMITED',retryAfter:'7'}},{maxRetries:2,pause:async x=>waits.push(x)});
 assert.equal(calls,3);assert.deepEqual(waits,[7000,7000]);assert.equal(r.halt,true);
});
test('a long server-directed wait is deferred, never shortened to bypass it',async()=>{
 let waited=false;const r=await invoke(async()=>({httpStatus:429,retryAfter:'3600'}),{pause:async()=>{waited=true},maxWaitMs:300000});assert.equal(waited,false);assert.equal(r.retryDeferred,true);
 assert.equal(retryAfter('Thu, 01 Jan 1970 00:00:10 GMT',0),10000);
});
test('sending all codes is not completion; pending remains resumable',async()=>{
 const dir=state();let calls=0;const opts={mode:'reroll',sid:'610083',accounts:accounts.slice(0,1),stateDir:dir,live:true,pause:noWait,adapters:{reroll:async()=>{calls++;return {status:'COMPLETE',result:{rewardCollectionComplete:false,cdkSentCount:28}}}}};
 await run(opts);await run(opts);assert.equal(calls,2);assert.equal(readJSON(path.join(dir,'reroll-610083.json')).tasks[plan(opts.accounts,{sid:'610083'})[0].key].status,'PENDING');
});
test('reroll resume passes prior per-server result and skips verified completion',async()=>{
 const dir=state();let calls=0;const opts={mode:'reroll',sid:'610083',accounts:accounts.slice(0,1),stateDir:dir,live:true,pause:noWait,adapters:{reroll:async(a,{previous})=>{calls++;if(calls===1)return {status:'PENDING',result:{rewardCollectionComplete:false,cdkSentCount:28}};assert.equal(previous.cdkSentCount,28);return {status:'COMPLETE',result:{rewardCollectionComplete:true}}}}};
 await run(opts);await run(opts);await run(opts);assert.equal(calls,2);
 await run({...opts,sid:'610084',adapters:{reroll:async(a,{previous})=>{assert.equal(previous,undefined);return {status:'PENDING'}}}});
});
test('jackpot is protected before preparation and delivery errors stay pending',async()=>{
 const dir=state();let lockedBefore=false;await run({mode:'reroll',sid:'610083',accounts:accounts.slice(0,1),stateDir:dir,live:true,pause:noWait,adapters:{reroll:async a=>({status:'JACKPOT_LOCKED',account:a,result:{isJackpotAlert:true}}),jackpot:async()=>{lockedBefore=readJSON(path.join(dir,'jackpot_locked_vault.json')).length===1;throw Error('delivery failed')}}});
 assert.equal(lockedBefore,true);const d=readJSON(path.join(dir,'reroll-610083.json'));assert.equal(Object.values(d.tasks)[0].jackpotFollowupPending,true);
});
test('dry run never loads live adapters; distributed live traffic is disabled',async()=>{
 const r=await run({mode:'reroll',sid:'610083',accounts,shards:20,shard:1,live:false,adapters:{reroll:()=>{throw Error('network')}}});assert.equal(r.dryRun,true);
 await assert.rejects(()=>run({mode:'reroll',sid:'610083',accounts,shards:20,shard:1,live:true,stateDir:state()}),/LIVE_DISTRIBUTED_DISABLED/);
});
test('CAPTCHA and OTP in the form are detected before submission',()=>{
 const {detectVerification}=require('../src/verification');
 assert.equal(detectVerification('<div class="g-recaptcha"></div>').requiresCaptcha,true);
 assert.equal(detectVerification('<input name="otp">').requiresOtp,true);
 assert.deepEqual(detectVerification('<form><input name="username"></form>'),{requiresCaptcha:false,requiresOtp:false});
});
test('failed jackpot delivery resumes without rerolling or touching sold accounts',async()=>{
 const dir=state();let gameCalls=0;
 await run({mode:'reroll',sid:'610083',accounts:accounts.slice(0,1),stateDir:dir,live:true,pause:noWait,adapters:{reroll:async a=>{gameCalls++;return {status:'JACKPOT_LOCKED',account:a,result:{username:a.username,sid:'610083',isJackpotAlert:true}}},jackpot:async()=>({complete:false})}});
 const {followups}=require('../src/followups');
 let calls=0;
 const blocked=await followups({stateDir:dir,sid:'610083',live:true,soldAccounts:[accounts[0]],deliver:async()=>{calls++;return {complete:true}}});assert.equal(blocked.attempted,0);
 await followups({stateDir:dir,sid:'610083',live:true,deliver:async()=>{calls++;return {complete:true,messageId:1}}});
 assert.equal(gameCalls,1);assert.equal(calls,1);
 const saved=readJSON(path.join(dir,'reroll-610083.json'));assert.equal(Object.values(saved.tasks)[0].jackpotFollowupPending,false);
});
test('registration adapter stops on a challenge form before any POST',async()=>{
 const {FuntapRegistrationClient}=require('../funtap-registration/src/registration-client');let posts=0;
 const client=new FuntapRegistrationClient({sessionManager:{requestWithRedirects:async()=>{posts++;throw Error('No POST allowed')}}});
 client.initializeSessionAndFetchForm=async()=>({httpStatus:200,requiresCaptcha:true,requiresOtp:false});
 const r=await client.registerAccount({username:'example',phone_source:'operator'},{operatorConfirmed:true});assert.equal(r.status,'VERIFICATION_REQUIRED');assert.equal(posts,0);
});
