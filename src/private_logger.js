const fs=require('fs'),path=require('path'),util=require('util');
function privateLogger(file){fs.mkdirSync(path.dirname(file),{recursive:true});const write=(level,args)=>fs.appendFileSync(file,`${new Date().toISOString()} [${level}] ${util.format(...args)}\n`,{mode:0o600});return {log:(...a)=>write('INFO',a),warn:(...a)=>write('WARN',a),error:(...a)=>write('ERROR',a)};}
module.exports={privateLogger};
