async function register(account){
 if(account.phone_source!=='operator')return {status:'VERIFICATION_REQUIRED',requiresOtp:true,messageCode:'OPERATOR_PHONE_REQUIRED'};
 const {FuntapRegistrationClient,validateRegistrationInput}=require('../../funtap-registration/src/registration-client');
 const valid=validateRegistrationInput(account);if(!valid.valid)return {status:'INVALID_INPUT',errorCount:valid.errors.length};
 const client=new FuntapRegistrationClient();
 const r=await client.registerAccount(account,{operatorConfirmed:true});
 return {status:r.status,httpStatus:r.httpStatus,requiresCaptcha:r.requiresCaptcha,requiresOtp:r.requiresOtp,isNewAccountCreated:r.isNewAccountCreated,funid:r.extractedUser?.id,retryAfter:r.retryAfter};
}
module.exports={register};
