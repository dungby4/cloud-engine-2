const fs=require('fs');const path=require('path');const {readJSON}=require('./storage');
const esc=x=>String(x??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
function captionFor(account,result,prepared,title='NỔ NÒNG CỐT & ĐÃ QUA TÂN THỦ'){
 const machine=readJSON(path.join(__dirname,'../machine.json'),{});const machineName=machine.machineName||`M${machine.machineId||1}`;
 const pairs=[['Dương Tiễn',result.countDT],['Tôn Ngộ Không',result.countTNK],['Na Tra',result.countNT],['Đường Tam Tạng',result.countDTT],['Cang Kim Tinh Quân',result.countCK],['Hồng Hài Nhi',result.countHHN],['Trấn Nguyên Tử',result.countTNT]].filter(([,n])=>n>0).map(([n,c])=>`${n} x${c}`).join(' + ');
 return `🔥🔥 <b>[${esc(title)}]</b>\n🖥 Máy chạy: <b>${esc(machineName)}</b>\n🌐 Server: <b>${esc(result.serverName)}</b> (<code>${esc(result.sid)}</code>)\n👤 TK: <code>${esc(account.username)}</code> | MK: <code>${esc(account.password)}</code>\n🆔 UID: <code>${esc(prepared.roleUid)}</code> | AccID: <code>${esc(account.accId)}</code>\n🎭 Nhân vật: <b>${esc(prepared.roleName)}</b> (Lv.${esc(prepared.roleLv)}) | Ngọc: <b>${esc(prepared.zuanshiLeft)} 💎</b>\n🔥 Tướng nổ: <b>${esc(pairs)}</b> (Tổng 5★: <b>${esc(result.heroes5StarCount)}</b>)\n🔒 <i>Đã khóa két bảo vệ &amp; rút khỏi kho reroll!</i>`;
}
async function prepareAndNotify(account,result,{signal,verifiedServer,replaceMessageId,recoverSkippedCampaign=false,quietLogPath,onBeforeTelegram}={}){
 const {prepareAndScreenshotJackpotAccount}=require('../prepare_jackpot_account');
 const srv=verifiedServer||await require('./adapters/reroll').server(result.sid);
 if(String(srv.sid)!==String(result.sid)||!/^wss:\/\//.test(srv.wsUrl))throw Error('Invalid server for jackpot preparation');
 const winningNames=[['Dương Tiễn',result.countDT],['Tôn Ngộ Không',result.countTNK],['Na Tra',result.countNT],['Đường Tam Tạng',result.countDTT],['Cang Kim Tinh Quân',result.countCK],['Hồng Hài Nhi',result.countHHN],['Trấn Nguyên Tử',result.countTNT]].filter(([,n])=>n>=2).map(([name])=>name);
 const recoveryMode=recoverSkippedCampaign||!!(result.rawV79&&result.rawV79.guideSkipSent!==false);
 const params={username:account.username,accId:String(account.accId),sid:String(result.sid),serverName:result.serverName,wsUrl:srv.wsUrl,targetHeroId:result.jackpotTargetHeroId||3014,resumeGuideStepId:result.rawV79?.guideState?.gid||null,recoverSkippedCampaign:recoveryMode,targetHeroNames:winningNames,minimumPhotoLevel:8,logger:require('./private_logger').privateLogger(quietLogPath||path.join(__dirname,'../state/tutorial-logs',`${result.sid}-${account.accId}.log`))};
 let prepared=await prepareAndScreenshotJackpotAccount(params);
 if(prepared.tutorialCleared&&prepared.roleLv<8)prepared=await prepareAndScreenshotJackpotAccount({...params,recoverSkippedCampaign:true});
 if(prepared.roleLv<8||!prepared.tutorialCleared||!require('./tutorial_evidence').tutorialConfirmed(prepared.tutorialEvidence))return {complete:false,errorCode:'TUTORIAL_NOT_CONFIRMED',prepared};
 if(!prepared.winnerPhotoOrdered)return {complete:false,errorCode:'WINNER_PHOTO_ORDER_NOT_CONFIRMED',prepared};
 if(!prepared.heroShotPath||!fs.existsSync(prepared.heroShotPath))return {complete:false,errorCode:'HERO_PHOTO_MISSING',prepared};
 const local=readJSON(path.join(__dirname,'../telegram.local.json'),{});const token=process.env.TELEGRAM_BOT_TOKEN||local.botToken;const chatId=process.env.TELEGRAM_CHAT_ID||local.chatId;
 if(!token||!chatId)return {complete:false,errorCode:'TELEGRAM_NOT_CONFIGURED',prepared};
 const caption=captionFor(account,result,prepared);
 const form=new FormData();form.append('chat_id',chatId);form.append('caption',caption);form.append('parse_mode','HTML');form.append('photo',new Blob([fs.readFileSync(prepared.heroShotPath)],{type:'image/png'}),path.basename(prepared.heroShotPath));
 if(replaceMessageId){form.delete('photo');form.delete('caption');form.delete('parse_mode');form.append('message_id',String(replaceMessageId));form.append('media',JSON.stringify({type:'photo',media:'attach://photo',caption,parse_mode:'HTML'}));form.append('photo',new Blob([fs.readFileSync(prepared.heroShotPath)],{type:'image/png'}),path.basename(prepared.heroShotPath));}
 if(onBeforeTelegram)await onBeforeTelegram();
 const response=await fetch(`https://api.telegram.org/bot${token}/${replaceMessageId?'editMessageMedia':'sendPhoto'}`,{method:'POST',body:form,signal:signal||AbortSignal.timeout(30000)});const data=await response.json();
 if(!response.ok||!data.ok)return {complete:false,errorCode:'TELEGRAM_SEND_FAILED',prepared};
 return {complete:true,messageId:data.result.message_id,prepared};
}
async function markPendingCaption(account,result,prepared,messageId){
 const c=readJSON(path.join(__dirname,'../telegram.local.json'),{});const token=process.env.TELEGRAM_BOT_TOKEN||c.botToken,chatId=process.env.TELEGRAM_CHAT_ID||c.chatId;
 if(!token||!chatId)throw Error('TELEGRAM_NOT_CONFIGURED');
 const response=await fetch(`https://api.telegram.org/bot${token}/editMessageCaption`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chat_id:chatId,message_id:messageId,caption:captionFor(account,result,prepared,'NỔ NÒNG CỐT • CHỜ HOÀN TẤT TÂN THỦ'),parse_mode:'HTML'}),signal:AbortSignal.timeout(30000)});const d=await response.json();if((!response.ok||!d.ok)&&!String(d.description||'').includes('message is not modified'))throw Error('CAPTION_CORRECTION_FAILED');return true;
}
module.exports={prepareAndNotify,markPendingCaption,captionFor};
