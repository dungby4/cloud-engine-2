const fs=require('fs'),path=require('path'),{spawn}=require('child_process');const root=path.resolve(__dirname,'..'),{readJSON,atomicJSON}=require('../src/storage');
let build;try{build=require('./check-build').checkBuild(root)}catch(e){console.error(e.message);process.exit(1)}
console.log(`Phiên bản ${build.version} | ${root}`);
function alive(pid){try{process.kill(pid,0);return true}catch{return false}}
const state=path.join(root,'state');fs.mkdirSync(state,{recursive:true});const file=path.join(state,'latest-runner.lock');let running=false;
if(fs.existsSync(file)&&alive(readJSON(file).pid))running=true;
if(running&&build.version!=='dev'&&readJSON(path.join(state,'v79-latest-process.json'),{}).version!==build.version){console.error('Runner đang dùng phiên bản cũ. Bấm DUNG ở bản cũ, chờ dừng hẳn rồi mở CHAY ở bản mới.');process.exit(1)}
if(!running){
 const clean=dir=>{for(const entry of fs.readdirSync(dir,{withFileTypes:true})){const p=path.join(dir,entry.name);if(entry.isDirectory())clean(p);else if(entry.isFile()&&entry.name.endsWith('.lock')){const d=readJSON(p);if(!alive(d.pid))fs.unlinkSync(p);}}};clean(state);
}
const python=path.join(root,'python_v79','.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
if(!fs.existsSync(python)){console.error('Chạy CAI_DAT trước để cài Python/Node dependencies.');process.exit(1)}
try{require.resolve('playwright')}catch{console.error('Thiếu dependencies: chạy CAI_DAT.');process.exit(1)}
if(!running){fs.rmSync(path.join(state,'stop-requested.json'),{force:true});const log=fs.openSync(path.join(state,'v79-latest-run.log'),'a',0o600);const child=spawn(process.execPath,[path.join(root,'scripts/run-v79-latest.js')],{cwd:root,detached:true,stdio:['ignore',log,log],windowsHide:true});fs.closeSync(log);child.on('error',()=>console.error('Không khởi động được runner'));atomicJSON(path.join(state,'v79-latest-process.json'),{pid:child.pid,...readJSON(path.join(root,'machine.json')),...readJSON(path.join(state,'live-settings.json')),version:build.version});child.unref();console.log('Đã mở runner; tự chọn server mới nhất.');}else console.log('Runner đang hoạt động; chỉ mở lại màn hình log.');
const viewer=spawn(python,[path.join(root,'scripts/watch-v79.py')],{cwd:root,stdio:'inherit'});viewer.on('exit',code=>{process.exitCode=code||0});
