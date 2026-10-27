function tutorialConfirmed({explicitGuideNull=false,stepsCompleted=0,lastGuideStepId=0,roleLv=0,campaignEvidence=null}={}){
 const c=campaignEvidence;
 if(c&&roleLv>=8&&c.wins>0&&Number.isInteger(c.initialChapterID)&&Number.isInteger(c.currentChapterID)&&c.currentChapterID>c.initialChapterID)return true;
 return explicitGuideNull===true && ((stepsCompleted>0&&lastGuideStepId===1827)||roleLv>=8);
}
function tutorialReady(evidence){return tutorialConfirmed(evidence)&&evidence.roleLv>=8;}
module.exports={tutorialConfirmed,tutorialReady};
