const API = '';
let token = localStorage.getItem('token');
let detected = [];
let camTarget = null;
let camStream = null;

window.onload = async () => {
  if (token) {
    try {
      const r = await af('/auth/me');
      if (r.ok) { const d = await r.json(); showApp(d.username); return; }
    } catch(e) {}
    token = null; localStorage.removeItem('token');
  }
  show('authScreen'); hide('appScreen');
};

function authTab(t) {
  document.querySelectorAll('.tab-btn').forEach((b,i)=>b.classList.toggle('on',['login','register'][i]===t));
  document.getElementById('loginForm').style.display = t==='login' ? '' : 'none';
  document.getElementById('regForm').style.display   = t==='register' ? '' : 'none';
}

async function doLogin() {
  const u=v('lu'), p=v('lp');
  if(!u||!p){set('le','Fill in all fields.');return;}
  load('loginBtn',true,'Signing in…');
  try {
    const r = await fetch('/auth/login',{method:'POST',headers:h(),body:JSON.stringify({username:u,password:p})});
    const d = await r.json();
    if(!r.ok){set('le',d.error);return;}
    token=d.token; localStorage.setItem('token',token); showApp(d.username);
  } catch(e){ set('le','Connection error.'); }
  finally { load('loginBtn',false,'Sign in'); }
}

async function doRegister() {
  const u=v('ru'),e=v('re'),p=v('rp');
  if(!u||!e||!p){set('ree','Fill in all fields.');return;}
  load('regBtn',true,'Creating…');
  try {
    const r = await fetch('/auth/register',{method:'POST',headers:h(),body:JSON.stringify({username:u,email:e,password:p})});
    const d = await r.json();
    if(!r.ok){set('ree',d.error);return;}
    toast('Account created — sign in','ok');
    authTab('login');
    document.getElementById('lu').value=u;
  } catch(e){ set('ree','Connection error.'); }
  finally { load('regBtn',false,'Create account'); }
}

function doLogout() {
  token=null; localStorage.removeItem('token');
  hide('appScreen'); show('authScreen');
  document.getElementById('lp').value=''; set('le','');
}

function showApp(username) {
  hide('authScreen'); show('appScreen');
  document.getElementById('navUser').textContent = username;
}

const panels = ['detect','assign','train','attend'];
function go(name) {
  document.querySelectorAll('.step').forEach((s,i)=>s.classList.toggle('on',panels[i]===name));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('on'));
  document.getElementById('p-'+name).classList.add('on');
  if(name==='assign') syncAssign();
}

async function checkStatus() {
  const cid=croom(); if(!cid)return;
  try {
    const r = await af('/classroom/'+cid+'/status');
    if(r.status===401){doLogout();return;}
    const d = await r.json();
    show('statusCard');
    document.getElementById('sModel').innerHTML = d.model_trained
      ? '<span class="pill pill-ok">Trained</span>'
      : '<span class="pill pill-no">Not trained</span>';
    document.getElementById('sFaces').textContent = d.labeled_faces_count;
  } catch(e){ toast('Could not reach server','err'); }
}

function pickFile(input, imgId) {
  const file = input.files[0]; if(!file) return;
  document.getElementById(imgId).src = URL.createObjectURL(file);
  document.getElementById(imgId+'-wrap').style.display = '';
}

function clearPreview(wrapId, inputId) {
  document.getElementById(wrapId).style.display = 'none';
  document.getElementById(inputId).value = '';
}

async function openCam(target) {
  camTarget = target;
  try {
    camStream = await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment'}});
    document.getElementById('camVideo').srcObject = camStream;
    document.getElementById('camModal').classList.add('open');
  } catch(e) {
    toast('Camera not available: '+e.message,'err');
  }
}

function closeCam() {
  if(camStream){ camStream.getTracks().forEach(t=>t.stop()); camStream=null; }
  document.getElementById('camModal').classList.remove('open');
}

function snapPhoto() {
  const video = document.getElementById('camVideo');
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth; canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video,0,0);
  canvas.toBlob(function(blob) {
    const file   = new File([blob],'camera.jpg',{type:'image/jpeg'});
    const imgId  = camTarget==='detect' ? 'dp' : 'ap';
    const inputId= camTarget==='detect' ? 'df' : 'af';
    const dt = new DataTransfer(); dt.items.add(file);
    document.getElementById(inputId).files = dt.files;
    document.getElementById(imgId).src = URL.createObjectURL(file);
    document.getElementById(imgId+'-wrap').style.display = '';
    closeCam();
  },'image/jpeg',0.92);
}

async function detectFaces() {
  const cid=croom(); if(!cid)return;
  const file = document.getElementById('df').files[0];
  if(!file){toast('Choose or capture a photo first','err');return;}
  load('detectBtn',true,'Detecting…');
  const form=new FormData(); form.append('file',file);
  try {
    const r = await af('/classroom/'+cid+'/detect_faces',{method:'POST',body:form});
    if(r.status===401){doLogout();return;}
    const d = await r.json();
    if(!r.ok){toast(d.error||'Detection failed','err');return;}
    detected = d.faces||[];
    renderDetected(detected);
    toast('Found '+detected.length+' face(s)','ok');
  } catch(e){ toast(e.message,'err'); }
  finally { load('detectBtn',false,'Detect faces'); }
}

function renderDetected(faces) {
  document.getElementById('dfCard').style.display = '';
  document.getElementById('dfTitle').textContent = faces.length+' face'+(faces.length!==1?'s':'')+' detected';
  document.getElementById('dfGrid').innerHTML = faces.length
    ? faces.map(function(f){
        return '<div class="face-tile"><img src="'+API+f.face_image_url+'" alt="'+f.face_id+'"/>'
          +'<div class="face-tile-body"><div class="face-tile-id">'+f.face_id+'</div></div></div>';
      }).join('')
    : '<p class="empty">No faces detected.</p>';
}

function syncAssign() {
  const grid=document.getElementById('agGrid');
  const hint=document.getElementById('assignHint');
  const btn =document.getElementById('assignBtn');
  if(!detected.length){ grid.innerHTML=''; hint.style.display=''; btn.style.display='none'; return; }
  hint.style.display='none'; btn.style.display='';
  grid.innerHTML = detected.map(function(f){
    return '<div class="face-tile"><img src="'+API+f.face_image_url+'" alt="'+f.face_id+'"/>'
      +'<div class="face-tile-body"><div class="face-tile-id">'+f.face_id+'</div>'
      +'<input type="text" id="r_'+f.face_id+'" placeholder="Roll no."/></div></div>';
  }).join('');
}

async function assignRolls() {
  const cid=croom(); if(!cid)return;
  const assignments = detected.map(function(f){
    var el = document.getElementById('r_'+f.face_id);
    return {face_id:f.face_id, roll_number:(el?el.value:'').trim()};
  }).filter(function(a){return a.roll_number;});
  if(!assignments.length){toast('Enter at least one roll number','err');return;}
  load('assignBtn',true,'Saving…');
  try {
    const r = await af('/classroom/'+cid+'/assign_roll_numbers',{
      method:'POST', headers:h(), body:JSON.stringify({assignments:assignments})
    });
    if(r.status===401){doLogout();return;}
    const d = await r.json();
    if(!r.ok){toast(d.error||'Failed','err');return;}
    toast('Saved '+d.successful.length+' roll number(s)','ok');
  } catch(e){toast(e.message,'err');}
  finally{load('assignBtn',false,'Save roll numbers');}
}

async function trainModel() {
  const cid=croom(); if(!cid)return;
  load('trainBtn',true,'Training… (may take a few minutes)');
  set('trainMsg','');
  try {
    const r = await af('/classroom/'+cid+'/train_model',{method:'POST'});
    if(r.status===401){doLogout();return;}
    const d = await r.json();
    const ok = r.ok && d.status==='success';
    document.getElementById('trainMsg').innerHTML =
      '<span class="pill '+(ok?'pill-ok':'pill-no')+'">'+(ok?'Done: '+d.message:'Error: '+(d.error||d.message))+'</span>';
    toast(ok?'Training complete!':'Training failed', ok?'ok':'err');
  } catch(e){toast(e.message,'err');}
  finally{load('trainBtn',false,'Start training');}
}

async function takeAttend() {
  const cid=croom(); if(!cid)return;
  const file = document.getElementById('af').files[0];
  if(!file){toast('Choose or capture a photo first','err');return;}
  load('attendBtn',true,'Recognizing…');
  const form=new FormData(); form.append('file',file);
  try {
    const r = await af('/classroom/'+cid+'/recognize_faces',{method:'POST',body:form});
    if(r.status===401){doLogout();return;}
    const d = await r.json();
    if(!r.ok){toast(d.error||'Failed','err');return;}
    renderAttend(d);
    toast('Recognized '+(d.recognized_faces?d.recognized_faces.length:0)+' face(s)','ok');
  } catch(e){toast(e.message,'err');}
  finally{load('attendBtn',false,'Recognize faces');}
}

function renderAttend(data) {
  show('attResCard');
  const img = document.getElementById('attResImg');
  if(data.resultImage){img.src=API+data.resultImage; img.style.display='';}
  const faces = data.recognized_faces||[];
  document.getElementById('attResList').innerHTML = faces.length
    ? faces.map(function(f){
        var pct=Math.round(parseFloat(f.confidence)*100);
        var known=f.roll_number!=='Unknown';
        return '<div class="att-row">'
          +'<img src="'+API+f.face_image_url+'" onerror="this.style.display=\'none\'"/>'
          +'<div class="att-info"><div class="att-roll">'+f.roll_number+'</div>'
          +'<div class="att-conf">Confidence: '+pct+'%</div></div>'
          +'<span class="badge '+(known?'badge-p':'badge-a')+'">'+(known?'Present':'Unknown')+'</span>'
          +'</div>';
      }).join('')
    : '<p class="empty">No faces recognized.</p>';
}

function af(url,opts){
  if(!opts) opts={};
  opts.headers = opts.headers||{};
  if(token) opts.headers['Authorization']='Bearer '+token;
  return fetch(API+url,opts);
}
function h(){ return {'Content-Type':'application/json'}; }
function v(id){ return document.getElementById(id).value.trim(); }
function set(id,val){ document.getElementById(id).textContent=val; }
function show(id){ document.getElementById(id).style.display=''; }
function hide(id){ document.getElementById(id).style.display='none'; }
function croom(){
  var c=document.getElementById('cid').value.trim();
  if(!c){toast('Enter a classroom ID','err');return null;}
  return c;
}
function load(id,on,label){
  var b=document.getElementById(id); b.disabled=on;
  b.textContent = label;
}
function toast(msg,type){
  var t=document.getElementById('toast');
  t.textContent=msg;
  t.className='show'+(type==='ok'?' ok':type==='err'?' err':'');
  clearTimeout(t._timer);
  t._timer=setTimeout(function(){t.className='';},3000);
}
