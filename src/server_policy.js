function serverAllowed(server,settings={}){const min=String(settings.minimumServerSid||'0');if(!/^\d+$/.test(min))throw Error('INVALID_MINIMUM_SERVER');return Number(server.sid)>=Number(min);}
module.exports={serverAllowed};
