"""Login to the existing Funtap account through the game's SDK REST endpoint."""
import hashlib,json,ssl,urllib.request,urllib.parse,urllib.error
APP_KEY='2a456b78cf5122cd9278ef24b4d7bfb9'
VERSION='9.9.9.5'
ENDPOINT=f'https://core.sdkmain.com/api/v1/apps/{APP_KEY}/{VERSION}/auth/login'
def sdk_login(username,password):
 if not username or not password:raise ValueError('Thiếu tài khoản hoặc mật khẩu')
 fields={'email':username.strip(),'password':password,'device_id':hashlib.sha1(b'vn.ftg.hactaydu.pixel6.device').hexdigest(),'fcm_token':'','package_name':'vn.ftg.hactaydu','appsflyer_id':'1729500000000-1234567890123456789','advertising_id':'00000000-0000-0000-0000-000000000000'}
 req=urllib.request.Request(ENDPOINT,data=urllib.parse.urlencode(fields).encode(),headers={'Content-Type':'application/x-www-form-urlencoded','Accept':'application/json','X-Request':APP_KEY,'app-Version':VERSION,'sdk-Version':'6.1.2','Language':'vi-VN','X-Android-Notch':'false'},method='POST')
 try:
  with urllib.request.urlopen(req,timeout=15,context=ssl.create_default_context()) as response:data=json.load(response)
 except urllib.error.HTTPError as exc:raise ValueError('Funtap từ chối đăng nhập (HTTP %s)'%exc.code) from None
 user=data.get('data') or {};token=data.get('access_token') or user.get('accessToken') or user.get('access_token');account=(user.get('account') or {}).get('account_id');code=data.get('error_code',0)
 if not account or not token or (isinstance(code,(int,float)) and code<0):raise ValueError(str(data.get('message') or 'Funtap chưa xác nhận đăng nhập'))
 return {'accountId':str(account),'accessToken':str(token),'username':str((user.get('account') or {}).get('username') or user.get('name') or username)}
