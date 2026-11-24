'use strict';
const $=id=>document.getElementById(id);
let project=null,geoTarget=null,busy=false;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function notice(message,error=false){$('notice').hidden=false;$('notice').textContent=message;$('notice').className=error?'error':'';}
async function api(url,{method='GET',body}={}){
 const headers={'X-Vet-Local':'1'};let payload=body;
 if(body!==undefined&&!(body instanceof FormData)){headers['Content-Type']='application/json';payload=JSON.stringify(body);}
 const response=await fetch(url,{method,headers,body:payload});
 let data;try{data=await response.json();}catch{throw Error(`伺服器回應異常 (${response.status})，請查看 WSL 終端。`);}
 if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail||data));return data;
}
function safe(fn){return async(...args)=>{try{await fn(...args);}catch(e){notice(e.message,true);}};}
async function listProjects(){
 const rows=await api('/api/projects');$('projects').innerHTML='<option value="">建立新專案</option>'+rows.map(p=>`<option value="${p.id}">${esc(p.city)} · ${p.count} 家 · ${p.id.slice(0,6)}</option>`).join('');
 if(project)$('projects').value=project.id;
}
function readConfig(){
 const config={...(project?.config||{})};
 for(const key of ['city','start_address','transport','primary_url','secondary_url','boundary_source'])config[key]=$(key).value.trim();
 for(const key of ['primary_options','secondary_options','exclude_locations']){try{config[key]=JSON.parse($(key).value);}catch{throw Error(`${key} 的 JSON 格式不正確。`);}}
 config.street_tiles=$('street_tiles').checked;return config;
}
function fillConfig(){
 const c=project?.config||{};
 for(const key of ['city','start_address','primary_url','secondary_url','boundary_source'])$(key).value=c[key]||'';
 $('transport').value=c.transport||'scooter';$('street_tiles').checked=c.street_tiles!==false;
 for(const key of ['primary_options','secondary_options'])$(key).value=JSON.stringify(c[key]||{complete_confirmed:false},null,2);
 $('exclude_locations').value=JSON.stringify(c.exclude_locations||[],null,2);
 $('save-config').textContent=project?'儲存設定':'建立專案';
}
function render(){
 for(const id of ['projects','new','demo','save-config'])$(id).disabled=busy;
 const rows=project?.records||[];const missing=rows.filter(r=>!r.exclude&&r.geo_status!=='confirmed').length;
 $('project-tag').textContent=project?`${project.config.city} / ${project.id.slice(0,6)}`:'尚未建立';
 $('collect').disabled=!project||busy;$('start-geo').disabled=!project||busy;
 $('generate').disabled=!project||!rows.length||busy||missing>0||!project.config.start_coordinate;
 $('count').textContent=rows.length;$('missing').textContent=missing;$('excluded').textContent=rows.filter(r=>r.exclude).length;$('pending-count').textContent=project?.pending?.length||0;
 const start=project?.config.start_coordinate;
 $('start-status').textContent=start?`已確認 ${start.lat.toFixed(6)}, ${start.lon.toFixed(6)}`:'尚未確認座標；可查詢候選位置或手動輸入。';
 $('downloads').innerHTML=project?.latest_run?`${project.stale?'<p>設定或資料已變更：以下為上次成果，請重新產出。</p>':''}<a href="/api/projects/${project.id}/files/workbook.xlsx">↓ Excel 工作簿</a><a href="/api/projects/${project.id}/files/district-maps.pdf">↓ 地圖 PDF</a><a href="/api/projects/${project.id}/files/deliverables.zip">↓ 完整成果 ZIP</a><a href="/api/projects/${project.id}/files/validation.json">驗證紀錄</a>`:'';
 $('audit').innerHTML=[...(project?.pending||[]).map(p=>`<p><b>${esc(p.name)}</b> ${esc(p.address)}<br>${esc(p.reason)}</p>`),...(project?.conflicts||[]).map(c=>`<p><b>${esc(c.name)}</b> · ${esc(c.field)}<br>採用主來源：${esc(c.primary)}<br>次來源：${esc(c.secondary)}</p>`)].join('')||'<p>尚無待確認紀錄。</p>';
 renderRows();
}
function renderRows(){
 const q=$('search').value.toLowerCase();const rows=(project?.records||[]).filter(r=>(r.name+r.address+r.district).toLowerCase().includes(q)&&(!$('only-missing').checked||(!r.exclude&&r.geo_status!=='confirmed')));
 $('records').innerHTML=rows.length?rows.map(r=>`<tr data-id="${r.id}"><td>${esc(r.district)}<br>#${r.map_no}</td><td><b class="${r.exclude||r.policy?'red':''}">${esc(r.name)}</b><small>${esc(r.address)}</small><a target="_blank" rel="noopener" href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(r.name+' '+r.address)}">Google Maps ↗</a></td><td>${r.day?`${r.day} / ${r.stop}`:'—'}</td><td><button data-geo="${r.id}" class="secondary">${r.geo_status==='confirmed'?'已定位 · 查看':'待定位'}</button></td><td><input data-field="birthday" aria-label="${esc(r.name)}生日" value="${esc(r.birthday)}" placeholder="留白"></td><td><input class="note" data-field="note" aria-label="${esc(r.name)}備注" placeholder="備注" value="${esc(r.note)}"><input class="note" data-field="policy" aria-label="${esc(r.name)}產品限制" placeholder="產品限制（例如僅推心臟產品）" value="${esc(r.policy)}"></td><td><input type="checkbox" data-field="exclude" aria-label="${esc(r.name)}不用去" ${r.exclude?'checked':''}></td><td><button data-save="${r.id}" class="secondary">儲存</button></td></tr>`).join(''):'<tr><td colspan="8" class="empty">沒有符合條件的醫院。</td></tr>';
}
async function reload(){project=await api(`/api/projects/${project.id}`);render();await listProjects();}
$('config-form').onsubmit=safe(async e=>{e.preventDefault();const c=readConfig();project=await api(project?`/api/projects/${project.id}/config`:'/api/projects',{method:project?'PUT':'POST',body:c});fillConfig();render();await listProjects();notice('設定已儲存。');});
$('projects').onchange=safe(async()=>{if($('projects').value)project=await api(`/api/projects/${$('projects').value}`);else project=null;fillConfig();render();});
$('new').onclick=()=>{project=null;$('projects').value='';fillConfig();render();};
$('demo').onclick=safe(async()=>{project=await api('/api/demo',{method:'POST'});fillConfig();render();await listProjects();notice('臺北範例已建立：16 家公開來源快照。產出仍需連線查詢道路服務；不會修改原始 Google 檔案。');});
async function job(action){
 if(!project)return;
 project=await api(`/api/projects/${project.id}/config`,{method:'PUT',body:readConfig()});
 busy=true;render();$('log').textContent='正在處理…';
 try{
  const started=await api(`/api/projects/${project.id}/jobs/${action}`,{method:'POST'});
  while(true){
   await new Promise(r=>setTimeout(r,1200));const j=await api(`/api/jobs/${started.job}`);$('log').textContent=j.log.join('\n')||'正在處理…';$('log').scrollTop=$('log').scrollHeight;
   if(j.state==='error')throw Error(j.error);
   if(j.state==='done'){await reload();notice(action==='collect'?'名單已彙整。請確認待定位及業務規則。':'工作簿與 PDF 已完成，讀回驗證通過。');break;}
  }
 }finally{busy=false;render();}
}
$('collect').onclick=safe(()=>job('collect'));$('generate').onclick=safe(()=>job('generate'));
$('search').oninput=renderRows;$('only-missing').onchange=renderRows;
$('records').onclick=safe(async e=>{
 const geo=e.target.closest('[data-geo]');if(geo){openGeo(geo.dataset.geo);return;}
 const save=e.target.closest('[data-save]');if(!save)return;
 const row=save.closest('tr');const edit={id:save.dataset.save};for(const el of row.querySelectorAll('[data-field]'))edit[el.dataset.field]=el.type==='checkbox'?el.checked:el.value;
 project=await api(`/api/projects/${project.id}/records`,{method:'POST',body:{records:[edit]}});render();notice('這家醫院的人工資料已儲存。');
});
function openGeo(id){
 geoTarget=id;const r=id==='start'?{...project.config.start_coordinate,name:'出發點',address:project.config.start_address,geo_source:project.config.start_geo_source}:project.records.find(r=>r.id===id);
 $('geo-title').textContent=r.name;$('geo-address').textContent=r.address;$('lat').value=r.lat??'';$('lon').value=r.lon??'';$('geo-source').value=r.geo_source||'';$('geo-confirm').checked=false;$('candidates').innerHTML='';$('geo-dialog').showModal();
}
$('start-geo').onclick=()=>openGeo('start');
$('lookup').onclick=safe(async()=>{
 $('lookup').disabled=true;$('candidates').textContent='搜尋中…';
 try{const candidates=await api('/api/geocode?q='+encodeURIComponent($('geo-address').textContent));$('candidates').innerHTML='';
 if(!candidates.length)$('candidates').textContent='沒有找到候選。請改用官方門牌座標或可靠院所定位資料。';
 for(const c of candidates){const b=document.createElement('button');b.type='button';b.textContent=c.label;b.onclick=()=>{$('lat').value=c.lat;$('lon').value=c.lon;$('geo-source').value=c.source;$('geo-confirm').checked=false;};$('candidates').appendChild(b);}
 }finally{$('lookup').disabled=false;}
});
$('geo-form').onsubmit=safe(async e=>{
 e.preventDefault();const lat=Number($('lat').value),lon=Number($('lon').value),source=$('geo-source').value;
 if(geoTarget==='start'){const c={...project.config,start_coordinate:{lat,lon},start_geo_source:source};project=await api(`/api/projects/${project.id}/config`,{method:'PUT',body:c});}
 else project=await api(`/api/projects/${project.id}/records`,{method:'POST',body:{records:[{id:geoTarget,lat,lon,geo_source:source}]}});
 $('geo-dialog').close();render();notice('位置已確認並儲存。');
});
async function upload(input,path){
 if(!project)throw Error('請先建立專案。');const f=$(input).files[0];if(!f)throw Error('請先選擇檔案。');const form=new FormData();form.append('file',f);
 const result=await api(`/api/projects/${project.id}/${path}`,{method:'POST',body:form});await reload();notice('匯入完成。'+(result.rows?'請按擷取 / 更新名單套用資料。':''));
}
for(const b of document.querySelectorAll('[data-upload]'))b.onclick=safe(()=>upload(b.dataset.upload+'-file','import/'+b.dataset.upload));
for(const b of document.querySelectorAll('[data-clear]'))b.onclick=safe(async()=>{if(!project)throw Error('請先建立專案');await api(`/api/projects/${project.id}/import/${b.dataset.clear}`,{method:'DELETE'});notice('已改回網址；下次擷取會重新下載。');});
$('upload-boundary').onclick=safe(()=>upload('boundary-file','boundaries'));$('upload-manual').onclick=safe(()=>upload('manual-file','import-manual'));
safe(listProjects)();render();
