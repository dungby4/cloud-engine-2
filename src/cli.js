const fs=require('fs');const path=require('path');const {readJSON,atomicJSON}=require('./storage');
function args(values){const out={};for(let i=0;i<values.length;i++){const v=values[i];if(!v.startsWith('--'))throw Error('Unexpected argument');if(!['--live','--help','--input','--sid','--shards','--shard','--output','--state','--limit','--interval-ms'].includes(v))throw Error('Unknown argument');if(['--live','--help'].includes(v))out[v.slice(2)]=true;else {if(!values[i+1]||values[i+1].startsWith('--'))throw Error('Missing value for '+v);out[v.slice(2)]=values[++i]}}return out}
async function main(){const [mode,...values]=process.argv.slice(2);const a=args(values);if(a.help||!mode||mode==='--help'){console.log('node src/cli.js reg|reroll|followup --input file.json [--sid 610083] [--shards 20 --shard 1] [--output output/plan.json] [--live --limit 5]');return}
 if(mode==='followup'){
  const report=await require('./followups').followups({stateDir:path.resolve(a.state||'state'),sid:a.sid,live:!!a.live,limit:Number(a.limit||10),soldAccounts:readJSON(path.join(__dirname,'../protection.json'),[])});
  console.log(JSON.stringify(report));return;
 }
 if(!a.input)throw Error('--input is required');const accountRows=readJSON(path.resolve(a.input));const stateDir=path.resolve(a.state||'state');
 const protectedAccounts=[...readJSON(path.join(__dirname,'../protection.json'),[]),...readJSON(path.join(__dirname,'../jackpot_locked_vault.json'),[]),...readJSON(path.join(stateDir,'jackpot_locked_vault.json'),[])];
 const controller=new AbortController();for(const sig of ['SIGINT','SIGTERM'])process.once(sig,()=>controller.abort());
 const {run}=require('./worker');const report=await run({mode,accounts:accountRows,sid:a.sid||'',shards:Number(a.shards||1),shard:Number(a.shard||1),stateDir,protectedAccounts,live:!!a.live,limit:Number(a.limit||100),intervalMs:Number(a['interval-ms']||1000),signal:controller.signal});
 if(a.output)atomicJSON(path.resolve(a.output),report);console.log(JSON.stringify(report));if(report.halted)process.exitCode=2;
}
if(require.main===module)main().catch(()=>{console.error('RUN_FAILED: check input/settings or private local checkpoint; no credentials printed');process.exitCode=1});
module.exports={args,main};
