'use strict';
/* £UVR€ studio — the atelier door. Studio-only: the demo's open
   registration is intentionally retired (AGENTS.md §2.5). The two
   founders sign in, hang drafts with real photographs, and keep the
   commissions desk (mark-paid / schedule / complete / cancel).
   Buyers never hold accounts.
   Shares globals with app.js (classic scripts): $, pad, toast,
   addPiece, glideTo, pieces, LUVRE_API. */
var veilOpen=false,session=null;

const consign=$('consign');
const studioForm=$('studioForm'),studioMsg=$('studioMsg');
const postForm=$('postForm'),postFile=$('postFile'),
      fileLine=$('fileLine'),filePrev=$('filePrev'),
      orderDesk=$('orderDesk');
let prevUrl=null;

function studioHeaders(extra){
  return Object.assign({Authorization:'Bearer '+session.token},extra||{});
}
function renderPortal(){
  $('authBox').hidden=!!session;
  $('deskBox').hidden=!session;
  if(session)$('deskHandle').textContent=session.handle;
}
/* The door is unlisted: no visible entry. Three touches on the
   wordmark within a breath reveal it for the session; the #atelier
   road opens it straight away. Tell Raph privately — never in print. */
function revealDoor(){
  $('consignOpen').hidden=false;
  try{sessionStorage.setItem('luvre.door','1')}catch(e){}
}
(function knock(){
  let taps=[],timer=null;
  const mark=()=>{revealDoor();openVeil()};
  document.querySelector('.logo-wrap').addEventListener('click',()=>{
    const now=performance.now();
    taps=taps.filter(t=>now-t<1200);taps.push(now);
    clearTimeout(timer);timer=setTimeout(()=>{taps=[]},1300);
    if(taps.length>=3){taps=[];mark()}
  });
  try{
    if(sessionStorage.getItem('luvre.door')==='1')revealDoor();
  }catch(e){}
  if(location.hash==='#atelier'){
    revealDoor();openVeil();
    history.replaceState(null,'',location.pathname+location.search);
  }
})();
function openVeil(){veilOpen=true;consign.hidden=false;requestAnimationFrame(()=>consign.classList.add('on'));refreshDesk()}
function closeVeil(){consign.classList.remove('on');setTimeout(()=>{consign.hidden=true;veilOpen=false},480)}
$('consignOpen').addEventListener('click',openVeil);
$('consignClose').addEventListener('click',closeVeil);
consign.addEventListener('click',e=>{if(e.target===consign.querySelector('.veil-bg'))closeVeil()});

studioForm.addEventListener('submit',async e=>{
  e.preventDefault();
  const fd=new FormData(studioForm);
  studioMsg.textContent='';
  try{
    session=await LUVRE_API.login({email:String(fd.get('email')||'').trim(),pass:fd.get('pass')});
    renderPortal();studioForm.reset();
    toast('Welcome back. The vault kept your secrets.');
  }catch(err){studioMsg.textContent=err.message}
});
$('signOut').addEventListener('click',async()=>{
  if(session)await LUVRE_API.logout(session.token);
  session=null;renderPortal();
});
postFile.addEventListener('change',()=>{
  const f=postFile.files&&postFile.files[0];
  if(f){
    fileLine.textContent=f.name;
    if(/^image\//.test(f.type)){
      if(prevUrl)URL.revokeObjectURL(prevUrl);
      prevUrl=URL.createObjectURL(f);
      filePrev.src=prevUrl;filePrev.hidden=false;
    }
  }else{
    fileLine.textContent='select a photograph of the piece';
    filePrev.hidden=true;
  }
});
postForm.addEventListener('submit',async e=>{
  e.preventDefault();
  if(!session)return;
  const fd=new FormData(postForm);
  const postMsg=$('postMsg');
  postMsg.textContent='';
  const pseudonym=String(fd.get('pseudonym')||'').trim(),
        title=String(fd.get('title')||'').trim();
  if(!pseudonym||!title){postMsg.textContent='A house and a title, at minimum.';return}
  const file=postFile.files&&postFile.files[0];
  if(!file){postMsg.textContent='The piece needs a plate image.';return}
  // Money is integer cents (CAD) from input onward — no floats in the money path.
  const dollars=String(fd.get('price')||'').trim();
  if(dollars&&!/^\d+$/.test(dollars)){postMsg.textContent='The price is counted in whole dollars.';return}
  const out=new FormData();
  out.append('pseudonym',pseudonym);
  out.append('title',title);
  out.append('year',String(fd.get('year')||'').trim());
  out.append('price_cents',dollars?String(parseInt(dollars,10)*100):'0');
  out.append('textile',String(fd.get('textile')||'').trim());
  out.append('dims',String(fd.get('dims')||'').trim());
  out.append('story',String(fd.get('story')||'').trim());
  out.append('care',String(fd.get('care')||'').trim());
  out.append('images',file,file.name);
  postMsg.textContent='Hanging it…';
  let created;
  try{
    const res=await fetch('/api/pieces',{method:'POST',headers:studioHeaders(),body:out});
    if(!res.ok)throw new Error((await res.json()).detail||'The gallery refused the hanging.');
    created=await res.json();
  }catch(err){postMsg.textContent=err.message;return}
  const listing=await LUVRE_API.getPiece(created.id);
  addPiece(listing);
  postForm.reset();
  fileLine.textContent='select a photograph of the piece';
  filePrev.hidden=true;
  closeVeil();
  glideTo(pieces.length-1);
  toast(`N° ${pad(pieces.length)} now hangs in the gallery. The house remains unnamed.`);
});

/* ---------- commissions desk ---------- */
const DESK_WORDS={created:'opened',awaiting_payment:'awaiting the transfer',reserved:'held for the handover',
  paid:'settled',handover_scheduled:'the hour is named',completed:'handed over',cancelled:'released',refunded:'returned'};
async function deskAction(id,verb,body){
  const r=await fetch(`/api/studio/orders/${id}/${verb}`,{method:'POST',
    headers:studioHeaders(body?{'Content-Type':'application/json'}:{}),
    body:body?JSON.stringify(body):undefined});
  if(!r.ok)toast((await r.json()).detail||'The desk refused.');
  refreshDesk();
}
async function refreshDesk(){
  if(!session)return;
  let all=[];
  try{
    const res=await fetch('/api/studio/orders',{headers:studioHeaders()});
    if(res.ok)all=await res.json();
  }catch(e){return}
  orderDesk.innerHTML='';
  const head=document.createElement('p');
  head.className='s-over';
  head.textContent=all.length?'Commissions — '+all.length+' on the books':'Commissions — the books are quiet';
  orderDesk.appendChild(head);
  all.forEach(o=>{
    const row=document.createElement('div');
    row.className='desk-head';
    row.style.flexWrap='wrap';
    const label=document.createElement('span');
    const b=document.createElement('b');
    b.textContent=`${o.reference_code} · ${o.piece_title}`;
    const sub=document.createElement('span');
    const amount=(o.amount_cents/100).toLocaleString('en-CA',{maximumFractionDigits:0});
    sub.textContent=` — ${o.buyer_name} · CAD ${amount} · ${DESK_WORDS[o.status]||o.status}`;
    label.append(b,sub);
    if(o.handover_area||o.handover_window){
      const meet=document.createElement('span');
      meet.textContent=` · meet: ${[o.handover_area,o.handover_window].filter(Boolean).join(' — ')}`;
      label.appendChild(meet);
    }
    const btns=document.createElement('span');
    btns.style.cssText='display:flex;gap:10px;flex-wrap:wrap';
    const mk=(word,verb,body)=>{
      const btn=document.createElement('button');
      btn.type='button';btn.className='so';btn.textContent=word;
      btn.addEventListener('click',()=>deskAction(o.id,verb,body));
      return btn;
    };
    if(o.status==='awaiting_payment'||o.status==='reserved'){
      btns.append(mk('mark paid','mark-paid'),mk('release','cancel'));
    }
    if(o.status==='paid'){
      const win=document.createElement('input');
      win.placeholder='hour — e.g. Saturday, late morning';
      win.setAttribute('aria-label','Handover hour');
      win.style.cssText='background:none;border:0;border-bottom:1px solid rgba(202,196,206,.25);color:inherit;font:400 14px var(--f-serif);padding:4px 2px;min-width:200px';
      const place=document.createElement('input');
      place.placeholder='place — e.g. the café on Fairmount';
      place.setAttribute('aria-label','Handover place');
      place.style.cssText=win.style.cssText;
      const go=document.createElement('button');
      go.type='button';go.className='so';go.textContent='name the hour';
      go.addEventListener('click',()=>deskAction(o.id,'schedule',
        {handover_window:win.value,handover_place_note:place.value}));
      btns.append(win,place,go);
    }
    if(o.status==='handover_scheduled')btns.append(mk('handed over','complete'));
    row.append(label,btns);
    orderDesk.appendChild(row);
  });
}
