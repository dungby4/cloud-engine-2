const fs=require('fs');const path=require('path');
function readJSON(file,fallback){try{return JSON.parse(fs.readFileSync(file,'utf8'))}catch(e){if(e.code==='ENOENT'&&fallback!==undefined)return fallback;throw e}}
function atomicJSON(file,data){fs.mkdirSync(path.dirname(file),{recursive:true});const tmp=`${file}.${process.pid}.${Date.now()}.tmp`;fs.writeFileSync(tmp,JSON.stringify(data,null,2)+'\n',{mode:0o600});fs.renameSync(tmp,file)}
function lock(file){fs.mkdirSync(path.dirname(file),{recursive:true});let fd;try{fd=fs.openSync(file,'wx',0o600);fs.writeFileSync(fd,JSON.stringify({pid:process.pid,at:new Date().toISOString()}))}catch(e){if(e.code==='EEXIST')throw Error('WORKER_ALREADY_RUNNING: remove lock only after verifying its process is stopped');throw e}return()=>{fs.closeSync(fd);fs.unlinkSync(file)}}
module.exports={readJSON,atomicJSON,lock};
