const crypto=require('crypto');
function validateMachine({machineId=1,machineCount=1}={}){if(!Number.isInteger(machineId)||!Number.isInteger(machineCount)||machineCount<1||machineCount>20||machineId<1||machineId>machineCount)throw Error('INVALID_MACHINE_PARTITION');return {machineId,machineCount};}
function owner(username,machineCount){validateMachine({machineId:1,machineCount});return Number(BigInt('0x'+crypto.createHash('sha256').update(String(username).trim().toLowerCase()).digest('hex').slice(0,12))%BigInt(machineCount))+1;}
function forMachine(rows,settings){const s=validateMachine(settings);return rows.filter(a=>owner(a.username,s.machineCount)===s.machineId);}
module.exports={owner,forMachine,validateMachine};
