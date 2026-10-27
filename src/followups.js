const path=require('path');const {readJSON,atomicJSON,lock}=require('./storage');
async function followups({stateDir,sid,live=false,limit=10,soldAccounts=[],deliver}){
 if(!Number.isInteger(limit)||limit<1||limit>10000)throw Error('Invalid followup limit');
 if(!/^\d+$/.test(String(sid)))throw Error('Explicit SID required');
 const file=path.join(stateDir,`reroll-${sid}.json`);const initial=readJSON(file,{tasks:{}});const vault=readJSON(path.join(stateDir,'jackpot_locked_vault.json'),[]);
 const soldNames=new Set(soldAccounts.map(a=>String(a.username||'').toLowerCase()).filter(Boolean));const soldIds=new Set(soldAccounts.map(a=>String(a.accId||'')).filter(Boolean));
 const select=state=>Object.entries(state.tasks).filter(([,x])=>x.status==='JACKPOT_LOCKED'&&x.jackpotFollowupPending&&(x.deliveryAttempts||1)<3).map(([key,entry])=>({key,entry,account:vault.find(a=>a.username===entry.result?.username)})).filter(x=>x.account&&!soldNames.has(x.account.username.toLowerCase())&&!soldIds.has(String(x.account.accId||'')));
 if(!live)return {dryRun:true,pending:select(initial).map(x=>x.key)};
 const release=lock(path.join(stateDir,`reroll-${sid}.lock`));
 try{const state=readJSON(file,{tasks:{}});let attempted=0,complete=0;for(const {entry,account} of select(state).slice(0,limit)){
  attempted++;entry.deliveryAttempts=(entry.deliveryAttempts||1)+1;
  try{entry.delivery=await (deliver||require('./jackpot').prepareAndNotify)(account,entry.result,{stateDir});entry.jackpotFollowupPending=!entry.delivery.complete;if(entry.delivery.complete)complete++;}catch{entry.delivery={complete:false,errorCode:'JACKPOT_FOLLOWUP_FAILED'};entry.jackpotFollowupPending=true}
  atomicJSON(file,state);
 }return {dryRun:false,attempted,complete};}finally{release()}
}
module.exports={followups};
