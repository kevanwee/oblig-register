
const form=document.querySelector('#decision'), approve=document.querySelector('#approve');
function ready(){
 approve.disabled=review.blocked || [...document.querySelectorAll('[data-change]')].some(x=>x.value!=='accept')
 || [...document.querySelectorAll('[data-impact]')].some(x=>!x.checked);
}
document.addEventListener('change',ready); ready();
form.addEventListener('submit',event=>{
 event.preventDefault(); const outcome=event.submitter.value;
 const actor=document.querySelector('#actor').value.trim(), evidence=document.querySelector('#basis').value.trim();
 if(!actor||evidence.length<8){document.querySelector('#status').textContent='Enter your name and a review basis of at least eight characters.';return;}
 if(outcome==='approved'&&approve.disabled)return;
 const value={schema_version:'1',package_digest:review.digest,outcome,actor,evidence,
 reviewed_at:new Date().toISOString(),synthetic:review.synthetic,
 changes:Object.fromEntries([...document.querySelectorAll('[data-change]')].map(x=>[x.dataset.change,x.value])),
 impacts_acknowledged:[...document.querySelectorAll('[data-impact]:checked')].map(x=>x.dataset.impact)};
 const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)+'\n'],{type:'application/json'}));
 const link=document.createElement('a');link.href=url;link.download='amendment-decision.json';link.click();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
 document.querySelector('#status').textContent='Decision downloaded. Run obligreg amend apply to validate it and record the result.';
});
