const API = "http://localhost:5000";

let cameraStream   = null;
let enrollStream   = null;
let capturedPhotos = [];
let allRecords     = [];
let allPersons     = [];
let scanLog        = [];
let schedules      = [];
let deleteTarget   = null;

/* ===== STORAGE ===== */
function saveSchedules(){ localStorage.setItem('fa_schedules', JSON.stringify(schedules)); }
function loadSchedules() { try{ schedules = JSON.parse(localStorage.getItem('fa_schedules')||'[]'); }catch{ schedules=[]; } }

/* ===== AVATAR ===== */
const PAL = [
  ['#ede9fe','#6d28d9'],['#d1fae5','#047857'],['#fef3c7','#b45309'],
  ['#fce7f3','#9d174d'],['#dbeafe','#1d4ed8'],['#f0fdf4','#15803d'],
  ['#ccfbf1','#0d9488'],['#ffedd5','#c2410c'],['#fae8ff','#7e22ce'],
  ['#fef9c3','#a16207'],['#fee2e2','#b91c1c'],['#e0f2fe','#0369a1'],
];
function getAv(name){ let h=0; for(let c of name) h=(h*31+c.charCodeAt(0))&0xffff; return PAL[h%PAL.length]; }
function ini(name)  { return name.split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase(); }
function avEl(name,size=36){
  const[bg,col]=getAv(name);
  return `<div class="avatar" style="width:${size}px;height:${size}px;min-width:${size}px;background:${bg};color:${col};">${ini(name)}</div>`;
}

/* ===== CLOCK ===== */
function updateClock(){
  const n=new Date();
  const el=document.getElementById('sys-time');
  if(el) el.textContent=n.toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
  const de=document.getElementById('dash-date');
  if(de) de.textContent=n.toLocaleDateString('en-IN',{weekday:'long',year:'numeric',month:'long',day:'numeric'});
  updateClassDisplay();
}
setInterval(updateClock,1000); updateClock();

/* ===== SCHEDULE ===== */
function toMin(t){ if(!t)return 0; const[h,m]=t.split(':').map(Number); return h*60+m; }
function toTime(m){ return String(Math.floor(m/60)).padStart(2,'0')+':'+String(m%60).padStart(2,'0'); }
function getNow(){ const n=new Date(); return n.getHours()*60+n.getMinutes(); }
function getDay(){ return['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][new Date().getDay()]; }

function getCurrent(){
  const now=getNow(), day=getDay();
  for(const s of schedules){
    if(!s.days||!s.days.includes(day)) continue;
    const start=toMin(s.startTime), end=toMin(s.endTime);
    if(now>=start-5&&now<=end) return{...s,now,start,end};
  }
  return null;
}
function getStatus(cls){
  if(!cls) return{status:'noclass',label:'No active class',badge:'noclass'};
  const grace=parseInt(cls.graceMinutes)||10;
  if(cls.now<=cls.start+grace) return{status:'present',label:`On time (within ${grace} min)`,badge:'window'};
  return{status:'late',label:`Late by ${cls.now-cls.start-grace} min`,badge:'late'};
}
function getNext(){
  const now=getNow(),day=getDay();
  let next=null,nxt=Infinity;
  for(const s of schedules){
    if(!s.days||!s.days.includes(day)) continue;
    const st=toMin(s.startTime);
    if(st>now&&st<nxt){nxt=st;next=s;}
  }
  return next?next.startTime+' '+next.subject:'None today';
}

function updateClassDisplay(){
  const cls=getCurrent(), info=getStatus(cls);
  const bar=document.getElementById('class-info-bar');
  if(bar){
    document.getElementById('cib-subject').textContent=cls?cls.subject:'No class scheduled now';
    document.getElementById('cib-time').textContent=cls?cls.startTime+' – '+cls.endTime:'—';
    const st=document.getElementById('cib-status');
    st.textContent=info.label; st.className='cib-status '+info.badge;
  }
  const ssb=document.getElementById('schedule-status-bar');
  if(ssb){
    const lbl=document.getElementById('ssb-subject'),val=document.getElementById('ssb-time'),bdg=document.getElementById('ssb-badge');
    if(cls){
      if(lbl) lbl.textContent=cls.subject||'Active Class';
      if(val) val.textContent=cls.startTime+' → '+cls.endTime;
      if(bdg){bdg.textContent=info.label;bdg.style.background=info.status==='present'?'rgba(4,120,87,.25)':'rgba(180,83,9,.25)';}
    } else {
      if(lbl) lbl.textContent='No class right now';
      if(val) val.textContent='Next: '+getNext();
      if(bdg){bdg.textContent='Free period';bdg.style.background='rgba(255,255,255,.15)';}
    }
  }
}

/* ===== API ===== */
async function checkAPI(){
  try{ await fetch(`${API}/`); setAPI(true); return true; }
  catch{ setAPI(false); return false; }
}
function setAPI(on){
  const b=document.getElementById('api-badge'),s=document.getElementById('sys-api-status');
  if(b){b.className='api-badge '+(on?'online':'offline');b.innerHTML=`<span class="api-dot"></span>${on?'API Online':'API Offline'}`;}
  if(s){s.textContent=on?'Online':'Offline — run app.py';s.className='sysinfo-val '+(on?'green':'red');}
}

/* ===== DASHBOARD ===== */
async function loadDashboard(){
  await checkAPI();
  try{
    const[sR,aR,pR]=await Promise.all([fetch(`${API}/stats`),fetch(`${API}/attendance`),fetch(`${API}/persons`)]);
    const stats=await sR.json(), attend=await aR.json(), persons=await pR.json();
    animateCount('stat-enrolled',stats.total_enrolled||0);
    animateCount('stat-present', stats.present_today||0);
    animateCount('stat-late',    stats.late_today||0);
    animateCount('stat-absent',  stats.absent_today||0);
    const total=stats.total_enrolled||1;
    const pct=Math.round(((stats.present_today||0)+(stats.late_today||0))/total*100);
    const pEl=document.getElementById('stat-pct'); if(pEl) pEl.textContent=pct+'% rate';

    const feed=document.getElementById('activity-feed'),cnt=document.getElementById('activity-count');
    if(feed){
      if(!attend.length){feed.innerHTML='<div class="empty-msg">No attendance recorded yet today</div>';if(cnt)cnt.textContent='0 today';}
      else{
        if(cnt) cnt.textContent=attend.length+' today';
        feed.innerHTML=attend.slice(0,8).map(r=>`
          <div class="activity-item">
            ${avEl(r.name)}
            <div class="activity-info">
              <div class="activity-name">${r.name}</div>
              <div class="activity-meta">${r.employee_id} · ${r.check_in||'—'}</div>
            </div>
            <span class="badge ${(r.status||'present').toLowerCase()}">${r.status||'Present'}</span>
          </div>`).join('');
      }
    }

    const mini=document.getElementById('enrolled-mini');
    if(mini){
      mini.innerHTML=!persons.length?'<div class="empty-msg">No one enrolled yet</div>'
        :persons.slice(0,5).map(p=>`
          <div class="activity-item">
            ${avEl(p.name,30)}
            <span style="font-size:.92rem;font-weight:700;">${p.name}</span>
            <span style="font-size:.78rem;color:var(--ink-g);margin-left:auto;font-weight:700;">${p.department||'—'}</span>
          </div>`).join('');
    }
  }catch(e){console.error('Dashboard:',e);}
}
function animateCount(id,target){
  const el=document.getElementById(id); if(!el)return;
  let v=0;const step=Math.max(1,Math.ceil(target/24));
  const t=setInterval(()=>{v=Math.min(v+step,target);el.textContent=v;if(v>=target)clearInterval(t);},40);
}

/* ===== PEOPLE PAGE ===== */
async function loadPeople(query='',deptFilter=''){
  try{
    const res=await fetch(`${API}/persons`);
    allPersons=await res.json();
    renderPeople(allPersons,query,deptFilter);
  }catch(e){
    const g=document.getElementById('people-grid');
    if(g) g.innerHTML='<div class="panel" style="grid-column:1/-1;padding:2.5rem;text-align:center;"><div class="empty-msg">Could not load — is app.py running?</div></div>';
  }
}

function renderPeople(persons,query='',deptFilter=''){
  let filtered=persons;
  if(query) filtered=filtered.filter(p=>p.name.toLowerCase().includes(query)||p.employee_id.toLowerCase().includes(query));
  if(deptFilter) filtered=filtered.filter(p=>p.department===deptFilter);

  // stats
  const total=persons.length;
  const depts=[...new Set(persons.map(p=>p.department).filter(Boolean))].length;
  const el_t=document.getElementById('pstat-total'),el_d=document.getElementById('pstat-depts'),el_f=document.getElementById('pstat-filtered');
  if(el_t) el_t.textContent=total;
  if(el_d) el_d.textContent=depts;
  if(el_f) el_f.textContent=filtered.length;

  const grid=document.getElementById('people-grid');
  if(!grid) return;

  if(!filtered.length){
    grid.innerHTML=`<div class="panel" style="grid-column:1/-1;padding:3rem;text-align:center;">
      <div style="font-size:2.5rem;margin-bottom:12px;">👤</div>
      <div style="font-size:1.1rem;font-weight:800;color:var(--ink);margin-bottom:6px;">${persons.length?'No results found':'No one enrolled yet'}</div>
      <div style="color:var(--ink-g);font-size:.9rem;">${persons.length?'Try a different search or filter':'Go to Enroll tab to register someone'}</div>
    </div>`;
    return;
  }

  grid.innerHTML=filtered.map(p=>{
    const[bg,col]=getAv(p.name);
    const dept=p.department||'—';
    const role=p.role||'Staff';
    const email=p.email||'—';
    return `<div class="person-card" id="pcard-${p.employee_id}">
      <div class="person-status-dot"></div>
      <div class="person-card-top">
        <div class="person-avatar-lg" style="background:${bg};color:${col};">${ini(p.name)}</div>
        <div style="flex:1;min-width:0;">
          <div class="person-name">${p.name}</div>
          <div class="person-id">${p.employee_id}</div>
        </div>
      </div>
      <div class="person-divider"></div>
      <div class="person-meta">
        <div class="person-meta-row"><span class="person-meta-icon">🏢</span>${dept}</div>
        <div class="person-meta-row"><span class="person-meta-icon">💼</span>${role}</div>
        ${email!=='—'?`<div class="person-meta-row"><span class="person-meta-icon">✉️</span><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${email}</span></div>`:''}
      </div>
      <div class="person-actions">
        <button class="btn btn-teal btn-sm" onclick="viewPersonRecord('${p.employee_id}','${p.name}')">📊 Records</button>
        <button class="btn btn-danger btn-sm" onclick="confirmDelete('${p.employee_id}','${p.name}')">🗑 Remove</button>
      </div>
    </div>`;
  }).join('');
}

function filterPeople(){
  const q=document.getElementById('people-search').value.trim().toLowerCase();
  const d=document.getElementById('people-dept').value;
  renderPeople(allPersons,q,d);
}

function confirmDelete(id,name){
  deleteTarget={id,name};
  document.getElementById('delete-name').textContent=name;
  document.getElementById('delete-id').textContent=id;
  document.getElementById('delete-modal').classList.add('show');
}
function closeModal(){
  document.getElementById('delete-modal').classList.remove('show');
  deleteTarget=null;
}
async function deletePerson(){
  if(!deleteTarget) return;
  try{
    const res=await fetch(`${API}/persons/${deleteTarget.id}`,{method:'DELETE'});
    const data=await res.json();
    if(data.success||res.ok){
      showToast(`${deleteTarget.name} removed from system`,'red');
      closeModal();
      await loadPeople(
        document.getElementById('people-search').value.trim().toLowerCase(),
        document.getElementById('people-dept').value
      );
      loadDashboard();
    } else {
      showToast(data.error||'Could not remove person','red');
      closeModal();
    }
  }catch{
    // fallback: remove from local list if API doesn't have DELETE yet
    allPersons=allPersons.filter(p=>p.employee_id!==deleteTarget.id);
    renderPeople(allPersons);
    showToast(`${deleteTarget.name} removed (local only — add DELETE route to app.py for permanent removal)`,'amber');
    closeModal();
    loadDashboard();
  }
}

function viewPersonRecord(id,name){
  showPage('records',null);
  document.querySelectorAll('.nav-tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t=>{ if(t.textContent.trim()==='Records') t.classList.add('active'); });
  setTimeout(()=>{
    const s=document.getElementById('search-input');
    if(s){s.value=id;filterRecords();}
  },200);
  showToast('Showing records for '+name,'purple');
}

/* ===== CAMERA ===== */
async function startCamera(){
  try{
    cameraStream=await navigator.mediaDevices.getUserMedia({video:{width:1280,height:720}});
    const v=document.getElementById('cam-video');
    v.srcObject=cameraStream;v.style.display='block';
    document.getElementById('cam-placeholder').style.display='none';
    document.getElementById('scan-overlay').classList.add('active');
    document.getElementById('btn-start-cam').disabled=true;
    document.getElementById('btn-scan').disabled=false;
    document.getElementById('btn-stop-cam').disabled=false;
    const st=document.getElementById('cam-status');st.textContent='● Live';st.style.color='var(--green)';
    showToast('Camera started','green');
  }catch{showToast('Camera access denied','red');}
}
function stopCamera(){
  if(cameraStream){cameraStream.getTracks().forEach(t=>t.stop());cameraStream=null;}
  document.getElementById('cam-video').style.display='none';
  document.getElementById('cam-placeholder').style.display='flex';
  document.getElementById('scan-overlay').classList.remove('active');
  document.getElementById('face-box').classList.remove('show');
  document.getElementById('btn-start-cam').disabled=false;
  document.getElementById('btn-scan').disabled=true;
  document.getElementById('btn-stop-cam').disabled=true;
  const st=document.getElementById('cam-status');st.textContent='Camera off';st.style.color='var(--ink-g)';
}
async function scanFace(){
  const btn=document.getElementById('btn-scan');
  btn.disabled=true;btn.textContent='Scanning…';
  const fb=document.getElementById('face-box');
  fb.style.borderColor='var(--amber)';fb.classList.add('show');
  document.getElementById('face-label').textContent='Detecting…';
  document.getElementById('face-label').style.background='var(--amber)';
  try{
    const video=document.getElementById('cam-video'),canvas=document.getElementById('cam-canvas');
    canvas.width=video.videoWidth;canvas.height=video.videoHeight;
    canvas.getContext('2d').drawImage(video,0,0);
    const img64=canvas.toDataURL('image/jpeg',.8);
    const cls=getCurrent(),info=getStatus(cls);
    const status=info.status==='late'?'Late':'Present';
    const res=await fetch(`${API}/recognize`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image:img64,status})});
    const data=await res.json();
    const card=document.getElementById('result-card');
    if(data.recognized){
      fb.style.borderColor='var(--green)';
      document.getElementById('face-label').textContent=data.name;
      document.getElementById('face-label').style.background='var(--green)';
      const pill=document.getElementById('result-pill');
      pill.className='result-pill '+(data.status==='Late'?'fail':'success');
      pill.innerHTML=data.status==='Late'?`⏰ Late — ${info.label}`:`✓ Present — On time`;
      document.getElementById('result-name').textContent=data.name;
      document.getElementById('result-detail').textContent=
        `${data.employee_id}  ·  ${cls?cls.subject:'No active class'}\nConfidence ${data.confidence}%  ·  ${data.attendance_logged?'Attendance marked':'Already marked today'}`;
      document.getElementById('conf-fill').style.width=data.confidence+'%';
      document.getElementById('conf-pct').textContent=data.confidence+'%';
      card.classList.add('show');
      scanLog.unshift({name:data.name,employee_id:data.employee_id,status:data.status,
        time:new Date().toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit'})});
      updateRecLog();
      showToast(`${data.name} — ${data.attendance_logged?data.status+' marked':'already marked'}`,data.status==='Late'?'amber':'green');
    }else{
      fb.style.borderColor='var(--red)';
      document.getElementById('face-label').textContent='Not recognized';
      document.getElementById('face-label').style.background='var(--red)';
      document.getElementById('result-pill').className='result-pill fail';
      document.getElementById('result-pill').innerHTML='✕ Not recognized';
      document.getElementById('result-name').textContent='Unknown face';
      document.getElementById('result-detail').textContent='No match in database.\nEnroll this person first.';
      document.getElementById('conf-fill').style.width='0%';
      document.getElementById('conf-pct').textContent='0%';
      card.classList.add('show');
      showToast('Face not recognized','red');
    }
  }catch(e){showToast('API error — is app.py running?','red');console.error(e);}
  btn.disabled=false;btn.innerHTML='⚡ Scan Face';
  setTimeout(()=>document.getElementById('face-box').classList.remove('show'),3000);
}
function updateRecLog(){
  const list=document.getElementById('rec-log-list'),cnt=document.getElementById('log-count');
  if(cnt) cnt.textContent=scanLog.length+' entries';
  if(!list) return;
  if(!scanLog.length){list.innerHTML='<div class="empty-msg">No scans yet this session</div>';return;}
  list.innerHTML=scanLog.map(s=>`
    <div class="log-entry">
      ${avEl(s.name,28)}
      <div class="log-name">${s.name}</div>
      <div class="log-time">${s.time}</div>
      <span class="badge ${s.status.toLowerCase()}" style="font-size:.72rem;padding:3px 9px;">${s.status}</span>
    </div>`).join('');
}

/* ===== ENROLL CAMERA ===== */
async function startEnrollCamera(){
  try{
    enrollStream=await navigator.mediaDevices.getUserMedia({video:true});
    const v=document.getElementById('enroll-video');
    v.srcObject=enrollStream;v.style.display='block';
    const btn=document.getElementById('btn-enroll-cam');
    btn.textContent='■ Stop Camera';btn.onclick=stopEnrollCamera;
    showToast('Camera ready — tap slots to capture','green');
  }catch{showToast('Camera access denied','red');}
}
function stopEnrollCamera(){
  if(enrollStream){enrollStream.getTracks().forEach(t=>t.stop());enrollStream=null;}
  document.getElementById('enroll-video').style.display='none';
  const btn=document.getElementById('btn-enroll-cam');
  btn.innerHTML='📷 Open Camera for Photos';btn.onclick=startEnrollCamera;
}
function captureEnrollPhoto(idx){
  const video=document.getElementById('enroll-video');
  if(!video.srcObject){showToast('Open camera first','red');return;}
  const canvas=document.getElementById('enroll-canvas');
  canvas.width=video.videoWidth||640;canvas.height=video.videoHeight||480;
  canvas.getContext('2d').drawImage(video,0,0);
  const b64=canvas.toDataURL('image/jpeg',.8);
  capturedPhotos[idx]=b64;
  const labels=['Front','Left','Right','Up'];
  const slot=document.getElementById(`slot-${idx}`);
  slot.classList.add('filled');
  slot.innerHTML=`<img src="${b64}"><div class="photo-num">✓ ${labels[idx]}</div>`;
  showToast(`Photo ${idx+1} captured!`,'green');
}
async function enrollPerson(){
  const name=document.getElementById('enroll-name').value.trim();
  const id=document.getElementById('enroll-id').value.trim();
  const dept=document.getElementById('enroll-dept').value;
  const role=document.getElementById('enroll-role').value.trim();
  const photos=capturedPhotos.filter(Boolean);
  if(!name||!id||!dept){showToast('Fill Name, ID and Department','red');return;}
  if(!photos.length){showToast('Capture at least 1 photo first','red');return;}
  const btn=document.querySelector('[onclick="enrollPerson()"]');
  if(btn){btn.disabled=true;btn.textContent='Enrolling…';}
  try{
    const res=await fetch(`${API}/enroll`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,employee_id:id,department:dept,role:role||'Staff',photos})});
    const data=await res.json();
    if(data.success){
      showToast(data.message,'green');
      ['enroll-name','enroll-id','enroll-role','enroll-email'].forEach(i=>{const el=document.getElementById(i);if(el)el.value='';});
      document.getElementById('enroll-dept').value='';
      capturedPhotos=[];
      [0,1,2,3].forEach(i=>{const s=document.getElementById(`slot-${i}`);s.classList.remove('filled');s.innerHTML='<span>+</span><span class="photo-slot-label">'+['Front','Left','Right','Up'][i]+'</span>';});
      stopEnrollCamera();loadEnrolled();loadDashboard();
    }else{showToast(data.error||'Enroll failed','red');}
  }catch{showToast('API error — is app.py running?','red');}
  if(btn){btn.disabled=false;btn.textContent='✓ Register Person';}
}
async function loadEnrolled(){
  try{
    const persons=await(await fetch(`${API}/persons`)).json();
    const tag=document.getElementById('enrolled-count-tag');if(tag) tag.textContent=persons.length+' total';
    const tbody=document.getElementById('enrolled-tbody');if(!tbody)return;
    tbody.innerHTML=!persons.length?'<tr><td colspan="4" class="empty-msg">No one enrolled yet</td></tr>'
      :persons.map(p=>`<tr>
        <td><div style="display:flex;align-items:center;gap:10px;">${avEl(p.name,32)}<span class="tbl-name">${p.name}</span></div></td>
        <td style="color:var(--ink-s);">${p.employee_id}</td>
        <td style="color:var(--ink-s);">${p.department||'—'}</td>
        <td style="color:var(--ink-s);">${p.role||'—'}</td>
      </tr>`).join('');
  }catch(e){console.error(e);}
}

/* ===== SCHEDULE ===== */
function renderSchedules(){
  const wrap=document.getElementById('schedule-cards'); if(!wrap)return;
  const DAYS=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  const today=getDay(),now=getNow();
  if(!schedules.length){
    wrap.innerHTML=`<div class="panel" style="grid-column:1/-1;padding:3rem;text-align:center;">
      <div style="font-size:2.5rem;margin-bottom:12px;">📅</div>
      <div style="font-size:1.2rem;font-weight:800;color:var(--ink);margin-bottom:6px;">No classes set up yet</div>
      <div style="color:var(--ink-g);font-size:.92rem;">Add your first class below</div>
    </div>`;
    return;
  }
  wrap.innerHTML=schedules.map((s,i)=>{
    const start=toMin(s.startTime),end=toMin(s.endTime);
    const isToday=s.days&&s.days.includes(today);
    const isActive=isToday&&now>=start-5&&now<=end;
    const grace=parseInt(s.graceMinutes)||10;
    return `<div class="schedule-card ${isActive?'active-class':''}">
      <div class="sch-subject">${s.subject||'Unnamed'}</div>
      <div class="sch-meta">${s.teacher?'👤 '+s.teacher:''}${s.room?' · 🚪 Room '+s.room:''}</div>
      <div class="sch-time"><span>${s.startTime}</span><span class="sch-sep">→</span><span>${s.endTime}</span></div>
      <div class="sch-window">⏱ On-time window: ${s.startTime} – ${toTime(start+grace)} (${grace} min grace)</div>
      <div class="sch-days">${DAYS.map(d=>`<span class="sch-day ${s.days&&s.days.includes(d)?'active':''}">${d}</span>`).join('')}</div>
      <div class="sch-actions">
        <button class="btn btn-secondary btn-sm" onclick="editSchedule(${i})">✏️ Edit</button>
        <button class="btn btn-danger btn-sm" onclick="deleteSchedule(${i})">🗑 Delete</button>
      </div>
    </div>`;
  }).join('');
}
function addSchedule(){
  const subject=document.getElementById('sch-subject').value.trim();
  const start=document.getElementById('sch-start').value;
  const end=document.getElementById('sch-end').value;
  const grace=document.getElementById('sch-grace').value||'10';
  const teacher=document.getElementById('sch-teacher').value.trim();
  const room=document.getElementById('sch-room').value.trim();
  const days=[...document.querySelectorAll('.day-cb:checked')].map(cb=>cb.value);
  if(!subject){showToast('Enter a subject name','red');return;}
  if(!start||!end){showToast('Set start and end time','red');return;}
  if(!days.length){showToast('Select at least one day','red');return;}
  if(toMin(start)>=toMin(end)){showToast('End time must be after start time','red');return;}
  const editIdx=document.getElementById('sch-edit-idx').value;
  if(editIdx!==''){
    schedules[parseInt(editIdx)]={subject,startTime:start,endTime:end,graceMinutes:grace,teacher,room,days};
    document.getElementById('sch-edit-idx').value='';
    document.getElementById('add-sch-btn').textContent='+ Add Class';
    showToast('Class updated!','green');
  }else{
    schedules.push({subject,startTime:start,endTime:end,graceMinutes:grace,teacher,room,days});
    showToast(`${subject} added!`,'green');
  }
  saveSchedules();renderSchedules();updateClassDisplay();
  document.getElementById('sch-subject').value='';
  document.getElementById('sch-start').value='';
  document.getElementById('sch-end').value='';
  document.getElementById('sch-grace').value='10';
  document.getElementById('sch-teacher').value='';
  document.getElementById('sch-room').value='';
  document.querySelectorAll('.day-cb').forEach(cb=>cb.checked=false);
  document.querySelectorAll('[id^="day-lbl-"]').forEach(lbl=>{lbl.style.background='var(--s1)';lbl.style.borderColor='var(--border)';lbl.style.color='var(--ink)';});
}
function editSchedule(i){
  const s=schedules[i];
  document.getElementById('sch-subject').value=s.subject||'';
  document.getElementById('sch-start').value=s.startTime||'';
  document.getElementById('sch-end').value=s.endTime||'';
  document.getElementById('sch-grace').value=s.graceMinutes||'10';
  document.getElementById('sch-teacher').value=s.teacher||'';
  document.getElementById('sch-room').value=s.room||'';
  document.querySelectorAll('.day-cb').forEach(cb=>{
    cb.checked=s.days&&s.days.includes(cb.value);
    updateDayLabel(cb);
  });
  document.getElementById('sch-edit-idx').value=i;
  document.getElementById('add-sch-btn').textContent='✓ Update Class';
  document.getElementById('schedule-form').scrollIntoView({behavior:'smooth'});
  showToast('Editing: '+s.subject,'purple');
}
function deleteSchedule(i){
  const name=schedules[i].subject;
  schedules.splice(i,1);saveSchedules();renderSchedules();updateClassDisplay();
  showToast(name+' deleted','red');
}
function cancelEdit(){
  document.getElementById('sch-edit-idx').value='';
  document.getElementById('add-sch-btn').textContent='+ Add Class';
  ['sch-subject','sch-start','sch-end','sch-teacher','sch-room'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});
  const g=document.getElementById('sch-grace'); if(g) g.value='10';
  document.querySelectorAll('.day-cb').forEach(cb=>{cb.checked=false;updateDayLabel(cb);});
}
function updateDayLabel(cb){
  const lbl=document.getElementById('day-lbl-'+cb.value); if(!lbl)return;
  if(cb.checked){lbl.style.background='var(--p100)';lbl.style.borderColor='var(--p400)';lbl.style.color='var(--p700)';}
  else{lbl.style.background='var(--s1)';lbl.style.borderColor='var(--border)';lbl.style.color='var(--ink)';}
}

/* ===== RECORDS ===== */
async function loadRecords(){
  const dateVal = document.getElementById('date-filter')?.value || '';
  const url = dateVal ? `${API}/attendance?date=${dateVal}` : `${API}/attendance`;
  const lbl = document.getElementById('records-date-label');

  // update label
  if(lbl){
    if(dateVal){
      const d = new Date(dateVal+'T00:00:00');
      const today = new Date().toISOString().split('T')[0];
      lbl.textContent = dateVal===today
        ? 'Today — '+d.toLocaleDateString('en-IN',{weekday:'long',day:'numeric',month:'long',year:'numeric'})
        : d.toLocaleDateString('en-IN',{weekday:'long',day:'numeric',month:'long',year:'numeric'});
    } else {
      lbl.textContent = 'Today — '+new Date().toLocaleDateString('en-IN',{weekday:'long',day:'numeric',month:'long',year:'numeric'});
    }
  }

  try{
    allRecords = await(await fetch(url)).json();
    renderRecords(allRecords);
    updateRecordsSummary(allRecords);
  }catch{
    const tb=document.getElementById('records-tbody');
    if(tb) tb.innerHTML='<tr><td colspan="7" class="empty-msg">Could not load — is app.py running?</td></tr>';
  }
}

function updateRecordsSummary(data){
  const present = data.filter(r=>r.status==='Present').length;
  const late    = data.filter(r=>r.status==='Late').length;
  const absent  = data.filter(r=>r.status==='Absent').length;
  const el_p=document.getElementById('rec-stat-present');
  const el_l=document.getElementById('rec-stat-late');
  const el_a=document.getElementById('rec-stat-absent');
  const el_t=document.getElementById('rec-stat-total');
  if(el_p) el_p.textContent=present;
  if(el_l) el_l.textContent=late;
  if(el_a) el_a.textContent=absent;
  if(el_t) el_t.textContent=data.length;
}

function setToday(){
  const df=document.getElementById('date-filter');
  if(df){ df.value=new Date().toISOString().split('T')[0]; loadRecords(); }
}

function setYesterday(){
  const df=document.getElementById('date-filter');
  if(!df) return;
  const y=new Date(); y.setDate(y.getDate()-1);
  df.value=y.toISOString().split('T')[0]; loadRecords();
}

function clearDateFilter(){
  const df=document.getElementById('date-filter');
  if(df){ df.value=''; loadRecords(); }
}

function renderRecords(data){
  const tbody=document.getElementById('records-tbody'); if(!tbody)return;
  const dateVal=document.getElementById('date-filter')?.value||'';
  const label=dateVal?'on this date':'today';
  if(!data.length){
    tbody.innerHTML=`<tr><td colspan="7" style="padding:3rem;text-align:center;">
      <div style="font-size:2rem;margin-bottom:10px;">📋</div>
      <div style="font-size:1rem;font-weight:700;color:var(--ink-s);">No attendance records ${label}</div>
      <div style="font-size:.85rem;color:var(--ink-g);margin-top:4px;">Try a different date or check if scanning has been done</div>
    </td></tr>`;
    return;
  }
  tbody.innerHTML=data.map((r,i)=>`
    <tr>
      <td style="color:var(--ink-g);font-size:.85rem;font-weight:700;">${i+1}</td>
      <td><div style="display:flex;align-items:center;gap:11px;">${avEl(r.name,30)}<span class="tbl-name">${r.name}</span></div></td>
      <td style="color:var(--ink-s);">${r.employee_id}</td>
      <td style="color:var(--ink-s);font-size:.82rem;">${r.date||'—'}</td>
      <td>${r.check_in||'—'}</td>
      <td>${r.confidence?r.confidence+'%':'—'}</td>
      <td><span class="badge ${(r.status||'present').toLowerCase()}">${r.status||'Present'}</span></td>
    </tr>`).join('');
}

function filterRecords(){
  const q  = document.getElementById('search-input').value.toLowerCase();
  const st = document.getElementById('filter-status').value;
  const filtered = allRecords.filter(r=>
    (r.name.toLowerCase().includes(q)||r.employee_id.toLowerCase().includes(q)) &&
    (!st||r.status===st)
  );
  renderRecords(filtered);
  updateRecordsSummary(filtered);
}

function exportCSV(){
  if(!allRecords.length){showToast('No records to export','red');return;}
  const dateVal=document.getElementById('date-filter')?.value||new Date().toISOString().split('T')[0];
  const csv=[
    ['Name','ID','Date','Check-in','Confidence','Status'],
    ...allRecords.map(r=>[r.name,r.employee_id,r.date||'—',r.check_in||'—',r.confidence?r.confidence+'%':'—',r.status])
  ].map(r=>r.join(',')).join('\n');
  const a=document.createElement('a');
  a.href='data:text/csv;charset=utf-8,'+encodeURIComponent(csv);
  a.download=`attendance_${dateVal}.csv`;
  a.click();
  showToast('CSV exported for '+dateVal,'green');
}

/* ===== NAV ===== */
function showPage(id,btn){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t=>t.classList.remove('active'));
  document.getElementById('page-'+id).classList.add('active');
  if(btn) btn.classList.add('active');
  if(id==='records')    loadRecords();
  if(id==='enroll')     loadEnrolled();
  if(id==='dashboard')  loadDashboard();
  if(id==='schedule')   renderSchedules();
  if(id==='recognition')updateClassDisplay();
  if(id==='people')     loadPeople();
}

/* ===== TOAST ===== */
function showToast(msg,type='green'){
  const t=document.getElementById('toast'),dot=document.getElementById('toast-dot'),txt=document.getElementById('toast-msg');
  if(!t)return;
  txt.textContent=msg;
  const cols={green:'var(--green)',red:'var(--red)',purple:'var(--p500)',amber:'var(--amber)',teal:'var(--teal)'};
  dot.style.background=cols[type]||cols.green;
  const bords={green:'var(--green-b)',red:'var(--red-b)',purple:'var(--p300)',amber:'var(--amber-b)',teal:'var(--teal-b)'};
  t.style.borderColor=bords[type]||bords.green;
  t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'),3500);
}

/* ===== INIT ===== */
loadSchedules();
loadDashboard();
setInterval(checkAPI,30000);