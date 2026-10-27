function progressLine({server,done,total,elapsedMs,username,sent,responses,totalCodes=28,tickets,stars,gems,heroes,jackpot=false}){
 const rate=elapsedMs>0?done/(elapsedMs/60000):0,remaining=Math.max(0,total-done);
 const value=x=>Number.isFinite(x)?String(x):'chưa rõ';
 const clock=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date());
 const ok=responses===totalCodes;
 return `[${clock}] [${server}: ${done}/${total} (${total?(100*done/total).toFixed(1):'0.0'}%) | Còn: ${remaining} | ~${rate.toFixed(1)} acc/p | ETA: ${rate>0?Math.ceil(remaining/rate)+'p':'đang đo'}] ${ok?'✅':'⚠️'}${jackpot?' 🔥🔥':''} ${username} -> Gửi: ${value(sent)}/${totalCodes} | Phản hồi: ${responses}/${totalCodes} | Vé TM còn: ${value(tickets)} | 5★: ${stars} | Ngọc: ${value(gems)} | Tướng: ${heroes||'Thường'}`;
}
module.exports={progressLine};
