'use strict';
/* =====================================================================
   £UVR€ — gallery.
   Ported from the single-file demo (kept at repo-root index.html as the
   design reference): marble, textile renderer, stage motion, FLIP
   dossier, auto-frame, toasts. Easing/physics constants untouched.

   TRANSPORT = 'http': LUVRE_API below maps 1:1 onto the backend —
   method names and promise shapes kept, bodies are fetch calls.
   Field mapping (wire → wall):
     pseudonym → maker · price_cents (int CAD) → price display string
     images[0].plate_url → img · images[0].palette → fixture frame seed
   Pieces without a plate yet are hung with the generative renderer as
   a dev fixture (never product imagery); the auto-frame still derives
   from the artwork itself.
   window.LUVRE_API is exposed for external tooling / testing.
   ===================================================================== */
const LUVRE_API=(()=>{
  const tokenKey='luvre.studio.token';
  function savedToken(){try{return localStorage.getItem(tokenKey)}catch(e){return null}}
  function hexRgb(h){
    h=String(h||'').replace('#','');
    if(!/^[0-9a-fA-F]{6}$/.test(h))return null;
    const v=parseInt(h,16);
    return [v>>16&255,v>>8&255,v&255];
  }
  function fromProjection(p){
    const first=(p.images||[])[0]||null;
    const dollars=(p.price_cents/100).toLocaleString('en-CA',{maximumFractionDigits:0});
    const pal3=first&&first.palette?first.palette.map(hexRgb).filter(Boolean):[];
    return {id:p.id,maker:p.pseudonym,title:p.title,year:p.year,
      micro:p.micro||'',textile:p.textile,dims:p.dims,
      price:'CAD '+dollars,price_cents:p.price_cents,
      story:p.story,care:p.care,status:p.status||'published',
      img:first&&first.plate_url?first.plate_url:null,
      _palette:pal3.length>=3?pal3:null,user:false};
  }
  // Stand-in renderer inputs for pieces awaiting their plate (M1):
  // derived from the piece's own palette so the frame stays truthful.
  function fixtureParams(p){
    if(p.seed&&p.pal)return p;
    const base=(p._palette&&p._palette.length?p._palette:[[29,59,42],[202,196,206],[14,31,22]]);
    const pal=[base[0],base[1]||base[0],base[2]||base[0],base[0],base[1]||base[0]];
    return Object.assign({},p,{seed:((Number(p.id)||1)*7919+13)>>>0,
      pal:pal,accent:base[1]||base[0],foldN:9,pins:4,warp:1,sheen:50});
  }
  async function publicListings(){
    const res=await fetch('/api/pieces');
    if(!res.ok)throw new Error('The wall could not be hung.');
    return (await res.json()).map(fromProjection);
  }
  async function getPiece(id){
    const res=await fetch('/api/pieces/'+id);
    if(!res.ok)throw new Error('This piece is not on the wall.');
    return fromProjection(await res.json());
  }
  async function login({email,pass}){
    const res=await fetch('/api/auth/login',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({email:email,password:pass})});
    if(!res.ok)throw new Error('Those details do not open the studio.');
    const data=await res.json();
    try{localStorage.setItem(tokenKey,data.access_token)}catch(e){}
    return {token:data.access_token,handle:email};
  }
  async function logout(){
    try{localStorage.removeItem(tokenKey)}catch(e){}
  }
  async function me(token){
    const res=await fetch('/api/me',{headers:{Authorization:'Bearer '+token}});
    if(!res.ok)return null;
    const data=await res.json();
    return {handle:data.email};
  }
  async function createListing(token,data){
    const res=await fetch('/api/pieces',{method:'POST',
      headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},
      body:JSON.stringify(data)});
    if(!res.ok)throw new Error('The gallery refused the hanging.');
    return getPiece((await res.json()).id);
  }
  async function myListings(){return []}   // the desk arrives with the order desk (M2)
  async function register(){
    throw new Error('The atelier keeps two keys; write to the curatorial desk to be considered.');
  }
  return {register,login,logout,me,createListing,publicListings,getPiece,
    myListings,savedToken,fixtureParams,fromProjection};
})();
window.LUVRE_API=LUVRE_API; // exposed for external tooling / testing

/* ---------- deterministic randomness & noise ---------- */
function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
function hash2i(x,y,s){let h=Math.imul(x|0,374761393)+Math.imul(y|0,668265263)+Math.imul(s|0,1442695041);h=h^h>>>13;h=Math.imul(h,1274126177);h^=h>>>16;return(h>>>0)/4294967296}
function vnoise(x,y,s){const xi=Math.floor(x),yi=Math.floor(y),xf=x-xi,yf=y-yi;
  const u=xf*xf*(3-2*xf),v=yf*yf*(3-2*yf);
  const a=hash2i(xi,yi,s),b=hash2i(xi+1,yi,s),c=hash2i(xi,yi+1,s),d=hash2i(xi+1,yi+1,s);
  return a+(b-a)*u+(c-a)*v+(a-b-c+d)*u*v}
function fbm(x,y,s,o){let v=0,a=.5,f=1,t=0;for(let i=0;i<o;i++){v+=a*vnoise(x*f,y*f,s+i*77);t+=a;a*=.5;f*=2.03}return v/t}
const clamp=(v,a,b)=>v<a?a:v>b?b:v;
const pad=n=>String(n).padStart(2,'0');
const $=id=>document.getElementById(id);

/* ---------- fallback hangings (dev fixture only) ----------
   Shown only when the backend cannot be reached or the wall is empty.
   Real plates replace these from M1 on. */
const SEED=[
 {seed:911,   maker:'Maison Verrière',    title:'Reliquary Drap',  year:2025, micro:'madder & iron on silk',
  textile:'Mulberry silk, 22 momme · cut on the bias · hand-rolled hem', dims:'96 × 158 cm', price:'CAD 3,900',
  story:'Dyed in a single bath of madder and iron, folded wet and left to sleep for eleven days. The creases you see are the record of that rest — the house calls it the memory of the cloth.',
  care:'Dry clean only · fold in acid-free tissue',
  pal:[[52,14,18],[118,34,38],[186,92,78],[104,30,34],[38,12,14]], accent:[214,150,96], foldN:11, pins:5, warp:1.2, sheen:60},
 {seed:4127,  maker:'Atelier Ondine',     title:'Tide Study Nº 4', year:2024, micro:'four indigos, one warp',
  textile:'Indigo-dyed silk twill, 9.2 mm · rolled selvedge', dims:'104 × 150 cm', price:'CAD 4,200',
  story:'A single warp passed four times through indigo of decreasing strength, so the colour deepens like water taking light. It was worn once, for one hour, at low tide.',
  care:'Dry clean only · keep from direct light',
  pal:[[16,24,48],[40,58,102],[94,122,170],[36,50,86],[14,20,40]], accent:[176,206,232], foldN:8, pins:4, warp:.8, sheen:78},
 {seed:77,    maker:'House of Salt',      title:'Vespers',         year:2023, micro:'loom-state raw silk',
  textile:'Raw silk noil · loom-state edges · undyed', dims:'112 × 162 cm', price:'CAD 2,850',
  story:'Undyed raw silk from the last vertical mill on the coast. Nothing was corrected; every slub and knot stands exactly where the loom left it.',
  care:'Hand wash cold, dry flat · never iron the slubs',
  pal:[[150,132,104],[204,188,158],[234,224,200],[172,152,120],[126,110,86]], accent:[240,232,208], foldN:12, pins:6, warp:1.3, sheen:34},
 {seed:2601,  maker:'Studio Callais',     title:'Patina II',        year:2025, micro:'salt-fixed patina',
  textile:'Cotton lamé with copper weft · patina arrested in sea salt', dims:'98 × 146 cm', price:'CAD 5,100',
  story:'Copper thread buried in sea-salt and yarrow for a season, then hung to stop the green exactly where it had arrived. The result cannot be repeated; it was not attempted.',
  care:'Do not wash · the patina is the piece',
  pal:[[14,44,36],[38,96,76],[104,156,122],[52,116,88],[20,58,46]], accent:[198,124,72], foldN:9, pins:4, warp:1.0, sheen:26},
 {seed:883,   maker:'Atelier Brume',     title:'Ash Liturgy',      year:2022, micro:'rain-washed wool–silk',
  textile:'Wool–silk, 62 / 38 · washed in collected rain', dims:'108 × 156 cm', price:'CAD 3,300',
  story:'A charcoal warp crossed with a bone weft, washed in rain gathered from the workshop roof. The grey is not dyed; it is allowed.',
  care:'Dry clean only · air for a day each season',
  pal:[[224,218,206],[178,170,156],[64,60,56],[150,142,130],[210,204,192]], accent:[112,106,98], foldN:7, pins:3, warp:.7, sheen:20},
 {seed:1543,  maker:'Maison Solaire',    title:'Hour of the Lion',  year:2024, micro:'double-dyed saffron',
  textile:'Lampas-weave silk · double-dyed saffron and madder', dims:'100 × 152 cm', price:'CAD 4,600',
  story:'Saffron and madder layered while the vat was deliberately too hot. The weaver records the minute the colour broke: 15:40, late August.',
  care:'Dry clean only · the saffron fades proudly',
  pal:[[112,52,18],[196,110,38],[236,168,86],[158,78,26],[84,38,14]], accent:[244,196,120], foldN:10, pins:5, warp:1.15, sheen:64},
 {seed:3366,  maker:'Compagnie Minérale', title:'Sterling Rite',   year:2023, micro:'true metallic thread',
  textile:'Silver lamé on slate silk ground · weighted hem', dims:'92 × 144 cm', price:'CAD 6,800',
  story:'True metallic thread on a slate ground, woven so slowly the loom was said to be thinking. It holds light the way stone holds rain — briefly, and all at once.',
  care:'Surface wipe only · avert perfume',
  pal:[[104,112,124],[168,178,192],[224,232,240],[136,144,158],[78,84,96]], accent:[238,246,252], foldN:13, pins:6, warp:1.35, sheen:92},
];
let pieces=[];                       // the wall, hung from /api/pieces
const WORDS=['zero','one','two','three','four','five','six','seven','eight','nine','ten','eleven','twelve'];
const VLBL=['I — The hanging','II — Counter view','III — Macro · weave','IV — Macro · dye'];

/* ---------- procedural emerald marble ---------- */
function paintMarble(canvas){
  const iw=innerWidth,ih=innerHeight;
  let mw=Math.min(860,Math.max(460,Math.round(iw*.55)));
  let mh=Math.max(240,Math.round(mw*ih/iw));
  canvas.width=mw;canvas.height=mh;
  const x=canvas.getContext('2d');
  const img=x.createImageData(mw,mh),d=img.data,S=4021;
  let q=0;
  for(let j=0;j<mh;j++){
    for(let i=0;i<mw;i++){
      const nx=i*.0038,ny=j*.0038;
      const q1=fbm(nx*1.7,ny*1.7,S,4);
      const t=Math.pow(1-Math.abs(Math.sin(nx*1.15+ny*.5+(q1-.5)*8.5)),4);
      const q2=fbm(nx*2.7+7.7,ny*2.7+3.1,S+31,3);
      const t2=Math.pow(1-Math.abs(Math.sin(nx*2.4-ny*1.35+(q2-.5)*9)),10)*.55;
      const patch=fbm(nx*.55+13,ny*.55+5,S+77,3);
      const gx=i/mw,gy=j/mh;
      let r=5+11*patch+5*(1-gy), g=13+23*patch+7*(1-gy), b=10+17*patch+6*(1-gy);
      const vm=t*(.45+.55*q1);  r+=34*vm; g+=84*vm; b+=64*vm;
      const fm=t2*(.35+.65*q2); r+=66*fm; g+=128*fm; b+=102*fm;
      const diag=Math.max(0,gx*.72+gy*.5-.55)*.55;
      const vg=1-.4*Math.pow(Math.min(1,Math.hypot(gx-.5,(gy-.46)*1.15)*1.9),2);
      const k=(1-diag)*vg;
      d[q]=r*k;d[q+1]=g*k;d[q+2]=b*k;d[q+3]=255;q+=4;
    }
  }
  x.putImageData(img,0,0);
}

/* ---------- generative textile renderer (dev fixture) ----------
   variant 0: primary drape · 1: counter drape · 2: macro weave · 3: macro dye */
function renderGarment(p,variant,W,H){
  const cv=document.createElement('canvas');cv.width=W;cv.height=H;
  const ctx=cv.getContext('2d');
  const img=ctx.createImageData(W,H),d=img.data;
  const seed=(p.seed*2654435761^variant*97531)>>>0;
  const R=mulberry32(seed);
  const zoom=variant>=2?(variant===2?3.4:2.7):1, span=1/zoom;
  const cx=zoom>1?0.40+R()*0.20:0.5, cy=zoom>1?0.38+R()*0.20:0.5;
  const mirrored=variant===1;
  const foldN=p.foldN*(mirrored?0.8:1);
  const warpA=p.warp*(mirrored?1.3:1);
  const phOff=variant*1.9+R()*6.283;
  const lightTilt=(mirrored?-1:1)*(0.09+R()*0.05);
  const jit=[];for(let k=0;k<24;k++)jit.push((R()-0.5)*1.5);
  const dyePh=R()*6.283,driftF=1.2+R()*1.4,driftA=0.16+R()*0.14;
  const cloudS=(p.seed%997)+variant*131,cloudA=0.45+R()*0.3;
  const sheenPh=R()*6.283,sheenF=2.2+R()*1.6;
  const sheenAmt=(variant>=2?(variant===2?15:30):p.sheen)*(mirrored?0.75:1);
  const threads=120+(R()*30|0);
  const threadA=variant===2?32:variant===3?9:5.5;
  const blobs=[],nb=variant===3?3:2;
  for(let k=0;k<nb;k++)blobs.push({x:.3+R()*.4,y:.26+R()*.42,r:.16+R()*.2,a:.3+R()*.3,c:variant===2?p.pal[2]:p.accent});
  const pal=p.pal,pins=p.pins,sd=seed&1023,stitch=variant===0;

  function rampCol(t){
    const n=pal.length;t=t-Math.floor(t);
    const f=t*n,i=f|0,fr=f-i,a=pal[i%n],b=pal[(i+1)%n];
    return[a[0]+(b[0]-a[0])*fr,a[1]+(b[1]-a[1])*fr,a[2]+(b[2]-a[2])*fr];
  }
  let q=0;
  for(let py=0;py<H;py++){
    const fy=py/H;
    for(let px=0;px<W;px++){
      const fx=px/W;
      const u=cx+(fx-0.5)*span, v=cy+(fy-0.5)*span;
      let alpha=255,dTop=1,ed=1,hem=1;
      if(zoom===1){
        const hw=0.335*(1+0.05*Math.sin(v*4.2+1.7)+0.05*(vnoise(v*2.1,3.3,21)-.5));
        const top=0.05+0.026*(1-Math.cos(6.2832*u*pins));
        hem=0.955-0.02*vnoise(u*4.4,3.1,55)-0.012*Math.sin(u*7+2);
        const edr=Math.min(hw-Math.abs(u-0.5),v-top,hem-v);
        if(edr<=0){q+=4;continue}
        const ew=0.006;
        if(edr<ew)alpha=255*edr/ew;
        ed=Math.min(1,edr/0.05);
        dTop=Math.min(1,(v-top)/0.16);
      }
      const drift=Math.sin(u*driftF*3.1416+dyePh)*driftA;
      const cloud=(fbm(u*2.3+cloudS*.011,v*2.7+cloudS*.017,cloudS,3)-.5)*cloudA;
      const c=rampCol(v*1.12+drift+cloud);
      for(let k=0;k<blobs.length;k++){
        const b=blobs[k],dd=Math.hypot(u-b.x,(v-b.y)*1.15);
        if(dd<b.r){const w=1-dd/b.r,kk=w*w*(3-2*w)*b.a;
          c[0]+=(b.c[0]-c[0])*kk;c[1]+=(b.c[1]-c[1])*kk;c[2]+=(b.c[2]-c[2])*kk}
      }
      const ju=jit[Math.min(23,Math.abs(u*24)|0)]*Math.sin(v*1.7+1.3);
      const sh=Math.sin(u*foldN*6.2832+warpA*Math.sin(v*2.6+phOff)+ju+(mirrored?3.1416:0));
      let lum=1+sh*(0.15+0.11*(1-v));
      lum*=1.05-v*0.26+lightTilt*(u-0.5)*2;
      const swv=Math.sin(u*sheenF*3.1416+v*1.9+sheenPh);
      if(swv>0)lum+=Math.pow(swv,16)*(sheenAmt/90);
      lum*=0.5+0.5*dTop;
      lum*=0.55+0.45*ed;
      if(stitch){
        const band=v-(hem-0.045);
        if(band>0&&band<0.007&&Math.sin(u*150+1)>0.15)lum*=0.7;
      }
      let th=Math.pow(Math.abs(Math.sin(3.14159*v*threads)),1.6)*(0.55+0.8*hash2i(v*threads|0,7,sd));
      th+=Math.pow(Math.abs(Math.sin(3.14159*u*threads*1.9)),1.6)*0.4;
      const tAdd=(th-0.8)*threadA*(0.35+0.65*Math.min(lum,1.4));
      const g=(hash2i(px,py,sd)-.5)*7;
      const r0=c[0]*lum+tAdd+g,g0=c[1]*lum+tAdd+g,b0=c[2]*lum+tAdd+g;
      d[q]=r0<0?0:r0>255?255:r0;d[q+1]=g0<0?0:g0>255?255:g0;d[q+2]=b0<0?0:b0>255?255:b0;
      d[q+3]=alpha;q+=4;
    }
  }
  ctx.putImageData(img,0,0);
  return cv;
}

/* ---------- uploaded-image plates ----------
   v0: cover-fit full view · v1: re-framed view · v2/v3: true macro crops */
function loadImgEl(p){return new Promise((res,rej)=>{
  if(p._imgEl)return res(p._imgEl);
  const im=new Image();
  im.onload=()=>{p._imgEl=im;res(im)};
  im.onerror=()=>rej(new Error('image'));
  im.src=p.img;
})}
async function imagePlate(p,variant,W,H){
  const im=await loadImgEl(p);
  const c=document.createElement('canvas');c.width=W;c.height=H;
  const x=c.getContext('2d');
  x.fillStyle='#070b09';x.fillRect(0,0,W,H);
  if(variant===0){
    const s=Math.max(W/im.width,H/im.height);
    x.drawImage(im,(W-im.width*s)/2,(H-im.height*s)/2,im.width*s,im.height*s);
  }else{
    const Z=[0,1.28,2.9,2.4][variant];
    const C=[0,[.42,.38],[.5,.5],[.68,.72]][variant];
    const cw=im.width/Z,ch=im.height/Z;
    const cx=clamp(im.width*C[0]-cw/2,0,Math.max(0,im.width-cw));
    const cy=clamp(im.height*C[1]-ch/2,0,Math.max(0,im.height-ch));
    x.drawImage(im,cx,cy,cw,ch,0,0,W,H);
  }
  return c;
}
/* downscale an uploaded file into a storable plate */
function fileToPlate(file){
  return new Promise((res,rej)=>{
    if(!/^image\//.test(file.type))return rej(new Error('not an image'));
    const url=URL.createObjectURL(file);
    const im=new Image();
    im.onload=()=>{
      try{
        const MAX=960,s=Math.min(1,MAX/Math.max(im.width,im.height));
        const c=document.createElement('canvas');
        c.width=Math.max(1,Math.round(im.width*s));
        c.height=Math.max(1,Math.round(im.height*s));
        const x=c.getContext('2d');
        x.fillStyle='#070b09';x.fillRect(0,0,c.width,c.height);
        x.drawImage(im,0,0,c.width,c.height);
        res({url:c.toDataURL('image/jpeg',.85)});
      }catch(err){rej(err)}finally{URL.revokeObjectURL(url)}
    };
    im.onerror=()=>{URL.revokeObjectURL(url);rej(new Error('would not open'))};
    im.src=url;
  });
}

/* ---------- auto-frame engine: dominant-colour extraction ----------
   Works identically on generated canvases and uploaded photographs. */
function extractPalette(srcCanvas){
  const w=48,h=60,c=document.createElement('canvas');c.width=w;c.height=h;
  const x=c.getContext('2d');x.drawImage(srcCanvas,0,0,w,h);
  const data=x.getImageData(0,0,w,h).data;
  const buckets=new Map();
  for(let i=0;i<data.length;i+=4){
    if(data[i+3]<128)continue;
    const key=(data[i]>>4)<<8|(data[i+1]>>4)<<4|(data[i+2]>>4);
    let e=buckets.get(key);if(!e){e={n:0,r:0,g:0,b:0};buckets.set(key,e)}
    e.n++;e.r+=data[i];e.g+=data[i+1];e.b+=data[i+2];
  }
  const sorted=[...buckets.values()].sort((a,b)=>b.n-a.n).map(e=>[e.r/e.n,e.g/e.n,e.b/e.n]);
  const picks=[];
  for(const s of sorted){
    if(picks.length>=3)break;
    let ok=true;
    for(const pck of picks)if(Math.hypot(s[0]-pck[0],s[1]-pck[1],s[2]-pck[2])<70){ok=false;break}
    if(ok)picks.push(s);
  }
  while(picks.length<3)picks.push(sorted[0]||[60,140,110]);
  return picks;
}
function applyFrame(art,pal){
  const dom=pal[0],acc=pal[1]||dom;
  const lift=c=>c.map(v=>Math.round(v+(250-v)*.45));
  const line=lift(acc),dv=dom.map(v=>v|0),hi=dom.map(v=>Math.round(v*.08+5));
  const s=art.style;
  s.setProperty('--l',`rgb(${line})`);
  s.setProperty('--l-soft',`rgba(${line},.38)`);
  s.setProperty('--l-line',`rgba(${line},.16)`);
  s.setProperty('--dom',`rgba(${dv},.5)`);
  s.setProperty('--dom2',`rgba(${dv},.18)`);
  s.setProperty('--matHi',`rgb(${hi})`);
}

/* ---------- stage construction ---------- */
const track=$('track'),stage=$('stage');
const slideEls=[],wrapEls=[],capEls=[];
function buildSlide(p,i){
  const s=document.createElement('div');
  s.className='slide';s.style.left=(i*100)+'%';s.dataset.i=i;
  const acquired=p.status==='sold';
  s.innerHTML=`
    <div class="inner">
      <div class="art-wrap${acquired?' sold':''}">
        <div class="art"><i class="deco"></i><div class="mat"><i class="mat-bg"></i></div></div>
        <div class="plaque">${acquired?'Acquired':`Veil — N° ${pad(i+1)}`}</div>
      </div>
      <div class="caption">
        <span class="cap-no">N° ${pad(i+1)} · one of one</span>
        <h2 class="cap-maker">${p.maker}</h2>
        <p class="cap-title">${p.title}</p>
        <span class="cap-rule"></span>
        <span class="cap-year">${p.year} — ${p.micro}</span>
      </div>
    </div>`;
  track.appendChild(s);
  slideEls.push(s);wrapEls.push(s.querySelector('.art-wrap'));capEls.push(s.querySelector('.caption'));
}
async function renderPiece(i){
  const p=pieces[i];
  if(p._pal||p._pending)return;
  p._pending=true;
  try{
    const art=slideEls[i].querySelector('.art');
    const cv=p.img?await imagePlate(p,0,560,700):renderGarment(LUVRE_API.fixtureParams(p),0,560,700);
    p._mainCv=cv;
    art.querySelector('.mat').appendChild(cv);
    p._pal=extractPalette(cv);          // the frame is derived from the artwork itself
    applyFrame(art,p._pal);
  }finally{p._pending=false}
}
function refreshCollectionLabel(){
  $('colSub').textContent='Veil — '+(WORDS[pieces.length]||pieces.length)+' hangings';
}
function addPiece(p){
  pieces.push(p);
  buildSlide(p,pieces.length-1);
  $('tot').textContent=pad(pieces.length);
  refreshCollectionLabel();
  renderPiece(pieces.length-1);
  dirty=true;
}

/* ---------- gallery motion (drag / glide / parallax) ---------- */
let current=0,dirty=true,glide=null,drag=null,lastIdx=-1,hintHidden=false;
const bgWrap=$('bgWrap'),barFill=$('barFill'),idxEl=$('idx');
function apply(){
  const vw=innerWidth;
  track.style.transform=`translate3d(${(-current*vw).toFixed(2)}px,0,0)`;
  bgWrap.style.transform=`translate3d(${(-current*10).toFixed(1)}px,0,0)`;
  for(let i=0;i<pieces.length;i++){
    const off=current-i,a=Math.abs(off);
    if(a>1.35||!pieces[i]._pal){slideEls[i].style.visibility='hidden';continue}
    slideEls[i].style.visibility='visible';
    wrapEls[i].style.transform=`translate3d(${(off*-6).toFixed(2)}vw,0,0) scale(${(1-Math.min(a*.05,.08)).toFixed(3)})`;
    capEls[i].style.transform=`translate3d(${(off*-26).toFixed(2)}vw,0,0)`;
    capEls[i].style.opacity=Math.max(0,1-Math.max(0,a-.14)*2.2).toFixed(3);
  }
  barFill.style.transform=`scaleX(${(clamp(current,0,pieces.length-1)/(pieces.length-1)).toFixed(4)})`;
  const ci=Math.round(clamp(current,0,pieces.length-1));
  if(ci!==lastIdx){
    lastIdx=ci;idxEl.textContent=pad(ci+1);
    $('navPrev').classList.toggle('off',ci<=0);
    $('navNext').classList.toggle('off',ci>=pieces.length-1);
  }
}
function glideTo(t){
  t=clamp(t,0,pieces.length-1);
  const from=current,d=t-from,t0=performance.now(),dur=clamp(420+Math.abs(d)*260,420,900);
  glide=now=>{
    const p=Math.min(1,(now-t0)/dur);
    current=from+d*(1-Math.pow(1-p,4));dirty=true;
    if(p>=1)glide=null;
  };
}
function loop(now){
  if(glide)glide(now);
  if(dirty){apply();dirty=false}
  requestAnimationFrame(loop);
}
function hideHint(){if(hintHidden)return;hintHidden=true;$('hint').classList.add('gone')}

stage.addEventListener('pointerdown',e=>{
  if(overlayOpen||veilOpen)return;
  if(e.pointerType==='mouse'&&e.button!==0)return;
  drag={x0:e.clientX,y0:e.clientY,t0:performance.now(),i:current,moved:false,
        tgt:e.target.closest('.art-wrap'),lv:{x:e.clientX,t:performance.now()}};
  stage.setPointerCapture(e.pointerId);
});
stage.addEventListener('pointermove',e=>{
  if(!drag)return;
  const dx=e.clientX-drag.x0,dy=e.clientY-drag.y0;
  if(!drag.moved&&Math.hypot(dx,dy)>7)drag.moved=true;
  if(!drag.moved)return;
  drag.lv={x:e.clientX,t:performance.now()};
  let raw=drag.i-dx/innerWidth;
  if(raw<0)raw*=.32;else if(raw>pieces.length-1)raw=(pieces.length-1)+(raw-(pieces.length-1))*.32;
  current=raw;dirty=true;hideHint();
});
stage.addEventListener('pointerup',()=>{
  if(!drag)return;
  const d=drag;drag=null;
  if(!d.moved){
    if(d.tgt&&!overlayOpen&&!veilOpen)openDossier(Math.round(clamp(current,0,pieces.length-1)));
    return;
  }
  const dt=d.lv.t-d.t0;
  const v=dt>0?(d.lv.x-d.x0)/dt:0;
  let tgt;
  if(v<-.32)tgt=Math.ceil(current-.08);
  else if(v>.32)tgt=Math.floor(current+.08);
  else tgt=Math.round(current);
  glideTo(tgt);
});
stage.addEventListener('pointercancel',()=>{drag=null});

let wheelLock=0;
addEventListener('wheel',e=>{
  if(overlayOpen||veilOpen)return;
  const dx=e.deltaX,dy=e.deltaY;
  if(Math.abs(dx)>10&&Math.abs(dx)>Math.abs(dy)){
    const now=performance.now();
    if(now<wheelLock)return;
    wheelLock=now+700;
    glideTo(Math.round(current)+(dx>0?1:-1));hideHint();
    e.preventDefault();
  }
},{passive:false});

addEventListener('keydown',e=>{
  if(e.key==='Escape'){
    if(acquireOpen)closeAcquire();
    else if(veilOpen)closeVeil();
    else if(overlayOpen)closeDossier();
    return;
  }
  if(veilOpen)return;
  if(overlayOpen){
    if(e.key==='ArrowRight')gStep(1);
    if(e.key==='ArrowLeft')gStep(-1);
    return;
  }
  if(e.key==='ArrowRight'){glideTo(Math.round(current)+1);hideHint()}
  if(e.key==='ArrowLeft'){glideTo(Math.round(current)-1);hideHint()}
});
 $('navPrev').addEventListener('click',()=>{glideTo(Math.round(current)-1);hideHint()});
 $('navNext').addEventListener('click',()=>{glideTo(Math.round(current)+1);hideHint()});
addEventListener('resize',()=>{dirty=true;if(overlayOpen)applyG()});

/* ---------- dossier (FLIP expansion) ---------- */
const dossier=$('dossier'),dPanel=$('dPanel'),gStage=$('gStage'),gTrack=$('gTrack'),
      gDots=$('gDots'),gLabel=$('gLabel'),gIdxEl=$('gIdx'),enqBtn=$('enquire');
let overlayOpen=false,dossierIndex=0,flipArt=null;
let gCur=0,gLast=-1,gDrag=null,gAnim=null;

function applyG(){
  gTrack.style.transform=`translate3d(${(-gCur*gStage.clientWidth).toFixed(1)}px,0,0)`;
  const gi=Math.round(clamp(gCur,0,3));
  if(gi!==gLast){
    gLast=gi;
    gLabel.textContent=VLBL[gi];
    gIdxEl.textContent=(gi+1)+' / 4';
    [...gDots.children].forEach((d,k)=>d.classList.toggle('on',k===gi));
  }
}
function gGlide(t){
  t=clamp(t,0,3);
  if(gAnim)cancelAnimationFrame(gAnim);
  const from=gCur,d=t-from,t0=performance.now();
  const step=now=>{
    const p=Math.min(1,(now-t0)/460);
    gCur=from+d*(1-Math.pow(1-p,3));applyG();
    if(p<1)gAnim=requestAnimationFrame(step);else{gCur=t;applyG()}
  };
  gAnim=requestAnimationFrame(step);
}
function gStep(dir){gGlide(Math.round(clamp(gCur,0,3))+dir)}
 $('gPrev').addEventListener('click',()=>gStep(-1));
 $('gNext').addEventListener('click',()=>gStep(1));

gStage.addEventListener('pointerdown',e=>{
  gDrag={x0:e.clientX,y0:e.clientY,t0:performance.now(),base:gCur,moved:false,
         lv:{x:e.clientX,t:performance.now()}};
  gStage.setPointerCapture(e.pointerId);
});
gStage.addEventListener('pointermove',e=>{
  if(!gDrag)return;
  const dx=e.clientX-gDrag.x0,dy=e.clientY-gDrag.y0;
  if(!gDrag.moved&&Math.hypot(dx,dy)>7)gDrag.moved=true;
  if(!gDrag.moved)return;
  gDrag.lv={x:e.clientX,t:performance.now()};
  if(Math.abs(dx)>Math.abs(dy))gCur=clamp(gDrag.base-dx/gStage.clientWidth,0,3);
  applyG();
});
gStage.addEventListener('pointerup',e=>{
  if(!gDrag)return;
  const d=gDrag;gDrag=null;
  if(!d.moved)return;
  const dy=e.clientY-d.y0,dx=e.clientX-d.x0;
  if(dy>70&&Math.abs(dy)>Math.abs(dx)){closeDossier();return}
  const dt=d.lv.t-d.t0,v=dt>0?(d.lv.x-d.x0)/dt:0;
  let t;
  if(v<-.32)t=Math.ceil(gCur-.05);
  else if(v>.32)t=Math.floor(gCur+.05);
  else t=Math.round(gCur);
  gGlide(t);
});
gStage.addEventListener('pointercancel',()=>{gDrag=null});

async function buildGallery(i){
  const p=pieces[i];
  if(!p._vars)p._vars=[];
  gTrack.innerHTML='';gDots.innerHTML='';
  for(let v=0;v<4;v++)gDots.appendChild(document.createElement('span'));
  for(let v=0;v<4;v++){
    const item=document.createElement('div');
    item.className='g-item';
    item.innerHTML='<div class="art"><i class="deco"></i><div class="mat"><i class="mat-bg"></i></div></div>';
    let cv=p._vars[v];
    if(!cv){
      if(p.img)cv=await imagePlate(p,v,640,800);
      else if(v===0&&p._mainCv){cv=document.createElement('canvas');cv.width=640;cv.height=800;
        cv.getContext('2d').drawImage(p._mainCv,0,0,640,800)}
      else cv=renderGarment(LUVRE_API.fixtureParams(p),v,640,800);
      p._vars[v]=cv;
    }
    item.querySelector('.mat').appendChild(cv);
    applyFrame(item.querySelector('.art'),p._pal);
    gTrack.appendChild(item);
  }
  gCur=0;gLast=-1;applyG();
}
function fillPanel(p,i){
  $('dOver').textContent=`Dossier · N° ${pad(i+1)} — Veil Collection`;
  $('dMaison').textContent=p.maker;
  $('dTitle').innerHTML=`<em>${p.title}</em> — ${p.year}`;
  $('dStory').textContent=p.story;
  $('dSpecs').innerHTML=
    `<div><dt>Textile</dt><dd>${p.textile}</dd></div>`+
    `<div><dt>Dimensions</dt><dd>${p.dims}</dd></div>`+
    `<div><dt>Edition</dt><dd>1 of 1 · signed in thread</dd></div>`+
    `<div><dt>Provenance</dt><dd>${p.user?'£UVR€ Vault · deposited by the house':'£UVR€ Vault · Geneva'}</dd></div>`+
    `<div><dt>Care</dt><dd>${p.care}</dd></div>`;
  $('dPrice').textContent=p.price;
  if(p.status==='sold'){
    $('dPrice').textContent='Acquired';
    enqBtn.hidden=true;
  }else{
    enqBtn.hidden=false;enqBtn.disabled=false;enqBtn.textContent='Enquire';
  }
}
async function openDossier(i){
  if(overlayOpen||!pieces[i]._pal)return;
  overlayOpen=true;dossierIndex=i;
  const p=pieces[i];
  fillPanel(p,i);
  await buildGallery(i);
  dossier.hidden=false;
  requestAnimationFrame(()=>dossier.classList.add('open'));
  // FLIP: artwork grows out of its frame; the frame scales up and dissolves
  const srcArt=slideEls[i].querySelector('.art');
  flipArt=gTrack.children[0].querySelector('.art');
  const src=srcArt.getBoundingClientRect();
  const dst=flipArt.getBoundingClientRect();
  flipArt.style.transition='none';
  flipArt.style.transformOrigin='0 0';
  flipArt.style.transform=`translate(${src.left-dst.left}px,${src.top-dst.top}px) scale(${src.width/dst.width},${src.height/dst.height})`;
  void flipArt.offsetWidth;
  requestAnimationFrame(()=>requestAnimationFrame(()=>{
    flipArt.style.transition='transform .9s var(--curve)';
    flipArt.style.transform='none';
    flipArt.classList.add('ghost');
    dPanel.classList.add('in');
  }));
}
function closeDossier(){
  if(!overlayOpen)return;
  gCur=0;applyG();
  const flip=flipArt;
  const src=slideEls[dossierIndex].querySelector('.art').getBoundingClientRect();
  const dst=flip.getBoundingClientRect();
  dossier.classList.remove('open');
  dPanel.classList.remove('in');
  flip.style.transition='transform .85s var(--curve)';
  flip.style.transform=`translate(${src.left-dst.left}px,${src.top-dst.top}px) scale(${src.width/dst.width},${src.height/dst.height})`;
  setTimeout(()=>flip.classList.remove('ghost'),300);
  setTimeout(()=>{
    dossier.hidden=true;overlayOpen=false;
    flip.style.transform='';flip.style.transition='';
  },950);
}
 $('dClose').addEventListener('click',closeDossier);

enqBtn.addEventListener('click',()=>{
  if(enqBtn.disabled)return;
  openAcquire(pieces[dossierIndex]);
});

/* ---------- a commission: guest checkout, no accounts ---------- */
const acquire=$('acquire');
let acquireOpen=false,acquirePiece=null;
const AC_WORDS={created:'opened',awaiting_payment:'awaiting your transfer',reserved:'held for you',
  paid:'settled — the desk will write with the hour',handover_scheduled:'the hour is named',
  completed:'handed over — keep it in good light',cancelled:'released back to the wall',refunded:'returned'};
function openAcquire(p){
  acquirePiece=p;
  const dollars=(p.price_cents/100).toLocaleString('en-CA',{maximumFractionDigits:0});
  $('acTitle').textContent=p.title+' — '+p.maker;
  $('acPrice').textContent='One of one · CAD '+dollars+' · '+p.year;
  $('acForm').hidden=false;$('acDone').hidden=true;$('acMsg').textContent='';
  acquireOpen=true;acquire.hidden=false;
  requestAnimationFrame(()=>acquire.classList.add('on'));
}
function closeAcquire(){acquire.classList.remove('on');setTimeout(()=>{acquire.hidden=true;acquireOpen=false},480)}
$('acquireClose').addEventListener('click',closeAcquire);
acquire.addEventListener('click',e=>{if(e.target===acquire.querySelector('.veil-bg'))closeAcquire()});
document.querySelectorAll('#acMethods input').forEach(r=>r.addEventListener('change',()=>{
  $('acMeet').hidden=document.querySelector('#acMethods input:checked').value!=='on_delivery';
}));
$('acSubmit').addEventListener('click',async()=>{
  if(!acquirePiece)return;
  const msg=$('acMsg');msg.textContent='';
  const method=document.querySelector('#acMethods input:checked').value;
  const name=document.querySelector('#acquire input[name=name]').value.trim();
  const email=document.querySelector('#acquire input[name=email]').value.trim();
  const phone=document.querySelector('#acquire input[name=phone]').value.trim();
  const area=document.querySelector('#acquire input[name=area]').value.trim();
  const window_=document.querySelector('#acquire input[name=window]').value.trim();
  if(!name||!email){msg.textContent='A name and a reachable contact, so the desk can find you.';return}
  if(method==='on_delivery'&&!area){msg.textContent='Choose the quarter where you would like to meet.';return}
  msg.textContent='Opening the commission…';
  let order;
  try{
    const res=await fetch('/api/orders',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({piece_id:acquirePiece.id,method:method,buyer_name:name,
        buyer_email:email,buyer_phone:phone||null,
        handover_area:method==='on_delivery'?area:null,
        handover_window:method==='on_delivery'?(window_||null):null})});
    if(!res.ok)throw new Error((await res.json()).detail||'The commission would not open.');
    order=await res.json();
  }catch(err){msg.textContent=err.message;return}
  $('acForm').hidden=true;$('acDone').hidden=false;
  $('acRef').textContent=order.reference_code;
  $('acInstr').textContent=order.instructions||(order.method==='paypal'
    ?'Continue among PayPal’s walls — the wall keeps your reference meanwhile.'
    :'The desk has it in hand.');
  const cont=$('acContinue');
  const roadOut=order.approval_url||order.checkout_url;
  if(roadOut){cont.hidden=false;cont.href=roadOut;
    cont.textContent=order.method==='crypto'?'Continue to the charge':'Continue to PayPal'}
  else cont.hidden=true;
  $('acLookId').value=order.id;$('acLookCode').value=order.reference_code;
  $('acStatus').textContent='';
});
$('acCheck').addEventListener('click',async()=>{
  const id=$('acLookId').value.trim(),code=$('acLookCode').value.trim();
  const out=$('acStatus');out.textContent='';
  if(!id||!code){out.textContent='The number and the reference, both.';return}
  try{
    const res=await fetch(`/api/orders/${id}?code=${encodeURIComponent(code)}`);
    if(!res.ok)throw new Error('This commission cannot be found.');
    const o=await res.json();
    const meet=[o.handover_window,o.handover_place_note].filter(Boolean).join(' — ');
    out.textContent=`${o.reference_code} — ${AC_WORDS[o.status]||o.status}. `+(o.instructions||'')+(meet?` The hour: ${meet}.`:'');
  }catch(err){out.textContent=err.message}
});
/* returning from PayPal's walls: the number travels in the road, the
   reference stayed in the buyer's keeping */
function openReturnLookup(id,cancelled){
  $('acTitle').textContent='Welcome back';
  $('acPrice').textContent=cancelled
    ?'The road broke off — your reference still holds the piece until its hour runs out.'
    :'The walls parted — ask after your commission with its reference.';
  $('acForm').hidden=true;$('acDone').hidden=false;
  $('acRef').textContent='';$('acInstr').textContent='';$('acContinue').hidden=true;
  $('acLookId').value=id;$('acLookCode').value='';$('acStatus').textContent='';
  acquireOpen=true;acquire.hidden=false;
  requestAnimationFrame(()=>acquire.classList.add('on'));
}

/* ---------- toasts ---------- */
function toast(msg){
  const t=document.createElement('div');
  t.className='toast';t.textContent=msg;
  $('toasts').appendChild(t);
  requestAnimationFrame(()=>requestAnimationFrame(()=>t.classList.add('on')));
  setTimeout(()=>{t.classList.remove('on');setTimeout(()=>t.remove(),500)},4200);
}

/* ---------- boot: the wall hangs from the backend ---------- */
(async function boot(){
  paintMarble($('marble'));                       // the room is built first
  let remote=[];
  try{remote=await LUVRE_API.publicListings()}catch(e){remote=[]}
  pieces=remote.length?remote:[...SEED];          // empty/unreachable wall → fixture hangings
  pieces.forEach((p,i)=>buildSlide(p,i));
  $('tot').textContent=pad(pieces.length);
  refreshCollectionLabel();
  renderPortal();
  document.body.classList.add('ready');
  apply();
  requestAnimationFrame(loop);
  try{
    const params=new URLSearchParams(location.search);
    const ret=params.get('commission');
    if(ret){
      openReturnLookup(ret,params.get('cancelled')==='1');
      history.replaceState(null,'',location.pathname);
    }
  }catch(e){}
  let i=1;
  (function next(){
    if(i>=pieces.length)return;
    setTimeout(()=>{renderPiece(i++);dirty=true;next()},150);
  })();
})();
