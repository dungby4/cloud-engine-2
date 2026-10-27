function detectVerification(html){const text=typeof html==='string'?html:'';return {requiresCaptcha:/g-recaptcha|h-captcha|hcaptcha|recaptcha|captcha[-_ ]?(?:widget|challenge|token)/i.test(text),requiresOtp:/<input\b[^>]*(?:name|id)\s*=\s*["'](?:otp|sms_code|verification_code)["']/i.test(text)}}
module.exports={detectVerification};
