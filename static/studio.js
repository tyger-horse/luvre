'use strict';
/* £UVR€ studio — the atelier desk. No accounts: the knock is the whole
   key. Three touches on the wordmark reveal the entry; three touches
   on the entry open the desk. The money roads already pay Raph
   directly, so there is nothing here to steal but the hanging itself.
   Shares globals with app.js (classic scripts): $, pad, toast,
   addPiece, glideTo, pieces, LUVRE_API. */
var veilOpen=false;

const consign=$('consign');
const postForm=$('postForm'),postFile=$('postFile'),
      fileLine=$('fileLine'),filePrev=$('filePrev'),
      pieceDesk=$('pieceDesk'),orderDesk=$('orderDesk');
let prevUrl=null;

function renderPortal(){
  $('deskBox').hidden=false;
  refreshPieces();
  refreshDesk();
}
function openVeil(){veilOpen=true;consign.hidden=false;requestAnimationFrame(()=>consign.classList.add('on'));refreshPieces();refreshDesk()}
function closeVeil(){consign.classList.remove('on');setTimeout(()=>{consign.hidden=true;veilOpen=false},480)}
$('consignClose').addEventListener('click',closeVeil);
consign.addEventListener('click',e=>{if(e.target===consign.querySelector('.veil-bg'))closeVeil()});

/* The knock, twice, in order: three touches on the wordmark reveal
   the entry — nothing more. Three touches on the entry open the desk.
   Every visit starts shut; nothing remembers. */
function revealDoor(){
  $('consignOpen').hidden=false;
}
function triple(el,fn){
  let taps=[],timer=null;
  el.addEventListener('click',()=>{
    const now=performance.now();
    taps=taps.filter(t=>now-t<1200);taps.push(now);
    clearTimeout(timer);timer=setTimeout(()=>{taps=[]},1300);
    if(taps.length>=3){taps=[];fn()}
  });
}
(function knock(){
  // Belt and braces: the door starts shut even if the browser cached an old page.
  $('consignOpen').hidden=true;
  triple(document.querySelector('.logo-wrap'),revealDoor);
  triple($('consignOpen'),openVeil);
  if(location.hash==='#atelier'){
    revealDoor();openVeil();
    history.replaceState(null,'',location.pathname+location.search);
  }
})();
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
    fileLine.textContent='Choose a photo of the piece';
    filePrev.hidden=true;
  }
});
postForm.addEventListener('submit',async e=>{
  e.preventDefault();
  const fd=new FormData(postForm);
  const postMsg=$('postMsg');
  postMsg.textContent='';
  const pseudonym=String(fd.get('pseudonym')||'').trim(),
        title=String(fd.get('title')||'').trim();
  if(!pseudonym||!title){postMsg.textContent='Pseudonym and title are required.';return}
  const file=postFile.files&&postFile.files[0];
  if(!file){postMsg.textContent='Choose a photo of the piece.';return}
  // Money is integer cents (CAD) from input onward — no floats in the money path.
  const dollars=String(fd.get('price')||'').trim();
  if(dollars&&!/^\d+$/.test(dollars)){postMsg.textContent='Price must be whole dollars (no cents or decimals).';return}
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
  postMsg.textContent='Uploading…';
  let created;
  try{
    const res=await fetch('/api/pieces',{method:'POST',body:out});
    if(!res.ok)throw new Error((await res.json()).detail||'Upload failed.');
    created=await res.json();
  }catch(err){postMsg.textContent=err.message;return}
  postForm.reset();
  fileLine.textContent='Choose a photo of the piece';
  filePrev.hidden=true;
  postMsg.textContent='';
  await refreshPieces();
  toast('Saved as a draft — publish it from the pieces list.');
});

/* ---------- pieces: publish and retire ---------- */
async function pieceAction(id,verb,okMsg){
  const r=await fetch(`/api/pieces/${id}/${verb}`,{method:'POST'});
  toast(r.ok?okMsg:(await r.json()).detail||'Failed.');
  refreshPieces();
}
async function refreshPieces(){
  let all=[];
  try{
    const res=await fetch('/api/studio/pieces');
    if(res.ok)all=await res.json();
  }catch(e){return}
  pieceDesk.innerHTML='';
  const head=document.createElement('p');
  head.className='s-over';
  head.textContent=all.length?'Pieces — '+all.length:'Pieces — nothing here yet';
  pieceDesk.appendChild(head);
  all.forEach(p=>{
    const row=document.createElement('div');
    row.className='desk-head';
    row.style.flexWrap='wrap';
    const label=document.createElement('span');
    const b=document.createElement('b');
    const amount=(p.price_cents/100).toLocaleString('en-CA',{maximumFractionDigits:0});
    b.textContent=p.title;
    const sub=document.createElement('span');
    sub.textContent=` — ${p.pseudonym} · CAD ${amount} · ${p.status}`;
    label.append(b,sub);
    const btns=document.createElement('span');
    btns.style.cssText='display:flex;gap:10px;flex-wrap:wrap';
    const mk=(word,verb,msg)=>{
      const btn=document.createElement('button');
      btn.type='button';btn.className='so';btn.textContent=word;
      btn.addEventListener('click',()=>pieceAction(p.id,verb,msg));
      return btn;
    };
    if(p.status==='draft')btns.append(mk('Publish','publish','Published — it is on the wall.'));
    if(p.status==='published')btns.append(mk('Retire','retire','Retired — off the wall.'));
    if(p.status==='sold'){
      const done=document.createElement('span');
      done.textContent='Sold';
      btns.append(done);
    }
    row.append(label,btns);
    pieceDesk.appendChild(row);
  });
}

/* ---------- commissions ---------- */
const DESK_WORDS={created:'Created',awaiting_payment:'Awaiting payment',reserved:'Reserved',
  paid:'Paid',handover_scheduled:'Handover scheduled',completed:'Completed',cancelled:'Cancelled',refunded:'Refunded'};
async function deskAction(id,verb,body,okMsg){
  const r=await fetch(`/api/studio/orders/${id}/${verb}`,{method:'POST',
    headers:body?{'Content-Type':'application/json'}:{},
    body:body?JSON.stringify(body):undefined});
  toast(r.ok?(okMsg||'Saved.'):(await r.json()).detail||'Failed.');
  refreshDesk();
}
async function refreshDesk(){
  let all=[];
  try{
    const res=await fetch('/api/studio/orders');
    if(res.ok)all=await res.json();
  }catch(e){return}
  orderDesk.innerHTML='';
  const head=document.createElement('p');
  head.className='s-over';
  head.textContent=all.length?'Commissions ('+all.length+')':'No commissions yet';
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
    if(o.tx_hash){
      const proof=document.createElement('span');
      const coin=(o.pay_currency||'eth').toUpperCase();
      const short=o.tx_hash.length>18?o.tx_hash.slice(0,12)+'…'+o.tx_hash.slice(-6):o.tx_hash;
      const link=document.createElement('a');
      const base=o.pay_currency==='btc'?'https://mempool.space/tx/':'https://etherscan.io/tx/';
      link.href=base+o.tx_hash;link.target='_blank';link.rel='noopener';
      link.textContent=`${coin} · ${short}`;
      link.style.color='inherit';
      proof.append(' · chain proof ',link);
      proof.style.wordBreak='break-all';
      label.appendChild(proof);
    }
    const btns=document.createElement('span');
    btns.style.cssText='display:flex;gap:10px;flex-wrap:wrap';
    const mk=(word,verb,body,msg)=>{
      const btn=document.createElement('button');
      btn.type='button';btn.className='so';btn.textContent=word;
      btn.addEventListener('click',()=>deskAction(o.id,verb,body,msg));
      return btn;
    };
    if(o.status==='awaiting_payment'||o.status==='reserved'){
      btns.append(mk('Mark paid','mark-paid',null,'Marked paid — the piece shows as sold.'),mk('Cancel','cancel',null,'Cancelled — the piece is back on the wall.'));
    }
    if(o.status==='paid'){
      const win=document.createElement('input');
      win.placeholder='e.g. Saturday morning';
      win.setAttribute('aria-label','Handover time');
      win.style.cssText='background:none;border:0;border-bottom:1px solid rgba(202,196,206,.25);color:inherit;font:400 14px var(--f-serif);padding:4px 2px;min-width:200px';
      const place=document.createElement('input');
      place.placeholder='e.g. Café on Fairmount';
      place.setAttribute('aria-label','Handover place');
      place.style.cssText=win.style.cssText;
      const go=document.createElement('button');
      go.type='button';go.className='so';go.textContent='Schedule';
      go.addEventListener('click',()=>deskAction(o.id,'schedule',
        {handover_window:win.value,handover_place_note:place.value},'Scheduled.'));
      btns.append(win,place,go);
    }
    if(o.status==='handover_scheduled')btns.append(mk('Complete','complete',null,'Completed.'));
    row.append(label,btns);
    orderDesk.appendChild(row);
  });
}
