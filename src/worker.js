const path=require('path');const {readJSON,atomicJSON,lock}=require('./storage');const {plan}=require('./planner');const {invoke,sleep}=require('./retry');
const TERMINAL=new Set(['REGISTER_SUCCESS','COMPLETE','JACKPOT_LOCKED','ALREADY_EXISTS']);
async function run({mode,accounts,sid='',shards=1,shard=1,stateDir,protectedAccounts=[],live=false,limit=100,intervalMs=1000,adapters={},pause=sleep,signal}){
 const tasks=plan(accounts,{mode,sid,shards,shard,protectedAccounts});
 if(!live)return {mode,dryRun:true,shard,shards,selected:tasks.length,tasks:tasks.map(t=>({key:t.key,owner:t.owner}))};
 if(shards!==1)throw Error('LIVE_DISTRIBUTED_DISABLED: this lab does not distribute provider traffic across IPs to evade blocking');
 if(!stateDir)throw Error('State directory required');if(!Number.isInteger(limit)||limit<1||limit>10000||!Number.isInteger(intervalMs)||intervalMs<1000)throw Error('Invalid limit or pacing');
 const release=lock(path.join(stateDir,`${mode}-${sid||'registration'}.lock`));
 const file=path.join(stateDir,`${mode}-${sid||'registration'}.json`);const state=readJSON(file,{version:1,tasks:{},accounts:[]});const report={mode,dryRun:false,selected:tasks.length,attempted:0,skipped:0,complete:0,pending:0,halted:false};
 const save=()=>{if(adapters.followupStatus)for(const e of Object.values(state.tasks)){if(e.status==='JACKPOT_LOCKED'&&e.result){const d=adapters.followupStatus(e.result);if(d){e.delivery=d;e.jackpotFollowupPending=!d.complete;}}}atomicJSON(file,state);};
 try{for(const task of tasks){
  if(signal?.aborted||report.attempted>=limit)break;
  const prior=state.tasks[task.key];if(TERMINAL.has(prior?.status)){report.skipped++;continue;}
  const action=mode==='reg'?(adapters.register||require('./adapters/register').register):(adapters.reroll||require('./adapters/reroll').reroll);
  const r=await invoke(()=>action(task.account,{sid,previous:prior?.result,signal}),{pause,signal});report.attempted++;
  const status=r.status||'UNKNOWN';const entry={status,updatedAt:new Date().toISOString(),retryDeferred:!!r.retryDeferred};
  if(mode==='reg'&&status==='REGISTER_SUCCESS'&&r.isNewAccountCreated===true){
   const account={...task.account,funid:String(r.funid||''),registeredAt:entry.updatedAt,gameState:'not_checked'};
   if(!account.funid)throw Error('Registration success missing identity evidence');
   if(!state.accounts.some(x=>x.username.toLowerCase()===account.username.toLowerCase()))state.accounts.push(account);
   report.complete++;
  }else if(mode==='reg'&&status==='REGISTER_SUCCESS'){entry.status='UNVERIFIED_REGISTRATION';report.pending++;}
  else if(mode==='reroll'){
   if(status==='COMPLETE'&&r.result?.rewardCollectionComplete!==true)entry.status='PENDING';
   if(r.result)entry.result=r.result;
   if(status==='COMPLETE'&&r.result?.rewardCollectionComplete===true)report.complete++;
   else if(status==='JACKPOT_LOCKED'){
    const vaultFile=path.join(stateDir,'jackpot_locked_vault.json');const vault=readJSON(vaultFile,[]);
    const a=r.account||task.account;if(!vault.some(x=>x.username===a.username))vault.push({...a,lockedAt:entry.updatedAt});atomicJSON(vaultFile,vault);
    entry.jackpotFollowupPending=true;entry.deliveryAttempts=1;state.tasks[task.key]=entry;save();
    try{const delivery=await (adapters.jackpot||require('./jackpot').prepareAndNotify)(a,r.result,{stateDir,signal,checkpointFile:file,taskKey:task.key});entry.delivery=delivery;entry.jackpotFollowupPending=!delivery.complete;}catch{entry.jackpotFollowupPending=true;entry.delivery={complete:false,errorCode:'JACKPOT_FOLLOWUP_FAILED'}}
    report.complete++;
   }else report.pending++;
  }else report.pending++;
  state.tasks[task.key]=entry;save();
  if(r.halt){report.halted=true;report.haltReason=status;break;}
  await pause(intervalMs,signal);
 }
 return report;}finally{release()}
}
module.exports={run};
