const crypto=require('crypto');
const digest=s=>crypto.createHash('sha256').update(String(s)).digest('hex');
function normalize(rows){if(!Array.isArray(rows))throw Error('Input must be a JSON array');const names=new Map(),ids=new Set();return rows.map(a=>{if(!a||typeof a.username!=='string'||!a.username.trim())throw Error('Account missing username');const n=a.username.trim().toLowerCase();if(names.has(n))throw Error('Duplicate username in input');names.set(n,true);if(a.accId){const id=String(a.accId);if(!/^\d+$/.test(id))throw Error('Invalid account ID');if(ids.has(id))throw Error('Duplicate account ID in input');ids.add(id)}return {...a,username:a.username.trim()}})}
function plan(rows,{mode='reroll',sid='',shards=1,shard=1,protectedAccounts=[]}={}){
 if(!['reg','reroll'].includes(mode))throw Error('Mode must be reg or reroll');if(!Number.isInteger(shards)||shards<1||shards>20||!Number.isInteger(shard)||shard<1||shard>shards)throw Error('Invalid shard (1..20)');if(mode==='reroll'&&!/^\d+$/.test(String(sid)))throw Error('Explicit numeric --sid required');
 const blockedNames=new Set(protectedAccounts.map(x=>String(x.username||'').trim().toLowerCase()).filter(Boolean)),blockedIds=new Set(protectedAccounts.map(x=>String(x.accId||'')).filter(Boolean));
 return normalize(rows).filter(a=>!blockedNames.has(a.username.toLowerCase())&&!blockedIds.has(String(a.accId||''))).map(account=>{const identity=`user:${account.username.toLowerCase()}`;const owner=Number(BigInt('0x'+digest(identity).slice(0,12))%BigInt(shards))+1;const key=`${mode}:${mode==='reroll'?sid+':':''}${digest(account.username.toLowerCase()).slice(0,24)}`;return {key,owner,account}}).filter(x=>x.owner===shard);
}
module.exports={plan,normalize,digest};
