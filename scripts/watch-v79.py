import pathlib,json,time,re
root=pathlib.Path(__file__).resolve().parent.parent
file=root/'state/v79-latest-run.log'
def visible(line):
 if re.match(r'^\[\d\d:\d\d:\d\d\] \[',line) or line.startswith('🔥🔥') or 'RUNNER_FAILED' in line:return line
 try:
  d=json.loads(line)
  if d.get('event')=='WAITING_FOR_REQUIRED_SERVER':return f"⏳ Chờ server {d['minimumSid']} trở lên; hiện mới có {d['latestSeen']}. Không nhận nick mới."
  if d.get('event')=='START':return f"▶ {d['server']} | {d['concurrency']} luồng / {d['codeDelayMs']} ms | {d['selected']} nick"
  if d.get('event')=='STOPPED':return '⏹ Đã dừng an toàn; hàng đợi chưa xong được lưu lại.'
  if d.get('event')=='NEW_SERVER':return f"🌐 Có server mới {d['to']}; chờ nick hiện tại xong để chuyển"
  if d.get('event') in ['WAITING_FOR_NEW_SERVER','SERVER_LOOKUP_FAILED']:return line
 except (ValueError,TypeError):pass
 return None
print('REROLL • Chi tiết tân thủ lưu riêng • Chỉ báo kết quả Telegram/lỗi',flush=True)
position=0
if file.exists():
 with file.open(encoding='utf-8',errors='replace') as f:
  f.seek(max(0,file.stat().st_size-131072))
  if f.tell():f.readline()
  lines=[x.rstrip() for x in f if visible(x.rstrip())]
  for x in lines[-10:]:print(visible(x),flush=True)
  position=f.tell()
while True:
 try:
  if file.stat().st_size<position:position=0
  with file.open(encoding='utf-8',errors='replace') as f:
   f.seek(position)
   for line in f:
    text=visible(line.rstrip())
    if text:print(text,flush=True)
   position=f.tell()
 except FileNotFoundError:pass
 time.sleep(1)
