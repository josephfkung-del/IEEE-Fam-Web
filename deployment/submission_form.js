let photo=null, processingPhoto=false, submitting=false;
const f=document.querySelector('#form'),msg=document.querySelector('#msg'),prev=document.querySelector('#prev');
const submitButton=f.querySelector('button[type="submit"],button:not([type])');
const originalButtonText=submitButton.textContent;
function M(t,c=''){msg.textContent=t;msg.className='msg '+c;msg.setAttribute('role',c==='bad'?'alert':'status')}
function refreshButton(){submitButton.disabled=submitting||processingPhoto;submitButton.textContent=submitting?'Submitting…':originalButtonText}
document.querySelector('#pic').onchange=e=>{
  photo=null;prev.hidden=true;
  const x=e.target.files[0];if(!x)return;
  processingPhoto=true;refreshButton();
  const fail=()=>{photo=null;processingPhoto=false;refreshButton();M('Could not read that photo. Please select an image again.','bad')};
  const r=new FileReader();r.onerror=fail;r.onload=()=>{
    const i=new Image();i.onerror=fail;i.onload=()=>{
      try{const s=Math.min(1,1400/Math.max(i.width,i.height)),c=document.createElement('canvas');c.width=Math.max(1,Math.round(i.width*s));c.height=Math.max(1,Math.round(i.height*s));c.getContext('2d').drawImage(i,0,0,c.width,c.height);photo=c.toDataURL('image/jpeg',.78);prev.src=photo;prev.hidden=false;processingPhoto=false;refreshButton();M('Photo ready.')}catch{fail()}
    };i.src=r.result;
  };r.readAsDataURL(x);
};
let retryPayload='',retryKey='';
async function submissionKey(payload){
  if(payload===retryPayload&&retryKey)return retryKey;
  const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(payload)))).map(x=>x.toString(16).padStart(2,'0')).join('');
  let previous=null;try{previous=JSON.parse(sessionStorage.getItem('familieeeRetry')||'null')}catch{}
  retryKey=previous&&previous.digest===digest?previous.key:crypto.randomUUID();retryPayload=payload;
  try{sessionStorage.setItem('familieeeRetry',JSON.stringify({digest,key:retryKey}))}catch{}
  return retryKey;
}
f.onsubmit=async e=>{
  e.preventDefault();if(submitting)return;
  if(processingPhoto)return M('Please wait for the photo to finish processing.','bad');
  if(!photo)return M('Please upload a photo.','bad');
  submitting=true;refreshButton();f.setAttribute('aria-busy','true');M('Submitting…');
  try{
    const d=new FormData(f),p=Object.fromEntries(d);p.member_count=+p.member_count;p.fam_head_present=d.get('fam_head_present')==='on';p.advertised_beforehand=d.get('advertised_beforehand')==='on';p.photo_data=photo;
    const payload=JSON.stringify(p),key=await submissionKey(payload);
    const r=await fetch('/api/submissions',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':key},body:payload});
    let x=null;try{x=await r.json()}catch{}
    if(!r.ok||!x||x.ok!==true){const detail=x&&typeof x.detail==='string'?x.detail:'Could not confirm your submission. Your entries are kept—please retry the same event.';M(detail,'bad');return}
    f.reset();photo=null;prev.hidden=true;retryPayload='';retryKey='';try{sessionStorage.removeItem('familieeeRetry')}catch{}
    M(x.duplicate?'Already received! Your event is saved.':'Submitted! Your event is waiting for admin review.','ok');void leaders();
  }catch{M('Could not confirm your submission. Your entries are kept—please retry the same event.','bad')}
  finally{submitting=false;refreshButton();f.setAttribute('aria-busy','false')}
};
async function leaders(){
  const el=document.querySelector('#leaders');
  try{const r=await fetch('/api/leaderboard');if(!r.ok)throw Error();const x=await r.json();el.replaceChildren();
    const rows=(x.leaderboard||[]).slice(0,8);
    if(!rows.length){const p=document.createElement('p');p.className='msg';p.textContent='No approved events yet.';el.append(p);return}
    rows.forEach((a,i)=>{const row=document.createElement('div');row.className='lr';for(const [tag,text] of [['span',i+1],['span',a.family_name],['b',a.points+' pts']]){const child=document.createElement(tag);child.textContent=String(text);row.append(child)}el.append(row)});
  }catch{el.textContent='Leaderboard temporarily unavailable.'}
}
void leaders();
