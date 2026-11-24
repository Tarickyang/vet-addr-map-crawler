import io,json,os,re,secrets,threading,time,traceback,uuid
from pathlib import Path
from fastapi import FastAPI,Request,HTTPException,UploadFile,File
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from . import service
from .engine import write_json,now
from .sources import download,parse,norm

app=FastAPI(title='動物醫院業務工作簿',docs_url=None,redoc_url=None)
app.mount('/static',StaticFiles(directory=service.ROOT/'static'),name='static')
JOBS={};JOBS_LOCK=threading.Lock();GEO_LOCK=threading.Lock();LAST_GEO=0
@app.middleware('http')
async def local_only(request,call_next):
 host=request.headers.get('host','').split(':')[0]
 if host not in ('127.0.0.1','localhost','testserver'):return JSONResponse({'detail':'僅接受 localhost 連線'},status_code=403)
 origin=request.headers.get('origin')
 if origin and origin not in (f'http://{request.headers.get("host")}',f'https://{request.headers.get("host")}'):
  return JSONResponse({'detail':'拒絕跨來源請求'},status_code=403)
 if request.method not in ('GET','HEAD') and request.headers.get('x-vet-local')!='1':return JSONResponse({'detail':'缺少本機介面標頭'},status_code=403)
 return await call_next(request)
@app.exception_handler(ValueError)
async def value_error(request,exc):return JSONResponse({'detail':str(exc)},status_code=400)
@app.get('/')
def index():return FileResponse(service.ROOT/'static/index.html')
@app.get('/api/projects')
def projects():
 return [{'id':p['id'],'city':p['config']['city'],'count':len(p['records']),'stale':p.get('stale',True)} for f in service.DATA.glob('*/project.json') for p in [json.loads(f.read_text())]]
@app.post('/api/projects')
def create(c:dict):return service.create(c)
@app.get('/api/projects/{pid}')
def get_project(pid:str):return service.load(pid)
@app.put('/api/projects/{pid}/config')
def config(pid:str,c:dict):
 with service.lock(pid):
  p=service.load(pid);service.config_check(c)
  if c['city']!=p['config']['city'] and p['records']:raise ValueError('已有資料後更換縣市請另建專案，避免混入人工資料。')
  if c['start_address']!=p['config']['start_address'] and c.get('start_coordinate')==p['config'].get('start_coordinate'):
   c.pop('start_coordinate',None);c.pop('start_geo_source',None)
  p.update(config=c,stale=True);service.save(p)
 return p
@app.post('/api/projects/{pid}/records')
def edit_records(pid:str,body:dict):
 with service.lock(pid):
  p=service.load(pid);byid={r['id']:r for r in p['records']}
  for edit in body.get('records',[]):
   r=byid[edit['id']]
   for field in ('birthday','note','policy'):
    if field in edit:r[field]=str(edit[field])[:4000]
   if 'exclude' in edit:r['exclude']=bool(edit['exclude'])
   if 'lat' in edit:
    if edit['lat'] is None:r.update(lat=None,lon=None,geo_status='missing')
    else:
     lat,lon=float(edit['lat']),float(edit['lon'])
     if not (20<=lat<=27 and 118<=lon<=123):raise ValueError('經緯度超出臺灣範圍。')
     source=str(edit.get('geo_source','')).strip()
     if not source:raise ValueError('確認座標必須提供來源或佐證網址。')
     r.update(lat=lat,lon=lon,geo_source=source,geo_status='confirmed',geo_method='使用者核對完整地址後確認')
  p['stale']=True;service.save(p)
 return p
@app.post('/api/projects/{pid}/import/{role}')
def source_import(pid:str,role:str,file:UploadFile=File(...)):
 if role not in ('primary','secondary'):raise ValueError('角色無效')
 raw=file.file.read(25_000_001)
 if len(raw)>25_000_000:raise ValueError('檔案不可超過25 MB')
 with service.lock(pid):
  p=service.load(pid);rows=parse(raw,path=p['config'].get(role+'_options',{}).get('record_path',''))
  write_json(service.folder(pid)/'imports'/(role+'.json'),{'rows':rows,'source':p['config'][role+'_url']+' [本機匯入 '+Path(file.filename).name+']','imported_at':now()})
  p['stale']=True;service.save(p)
 return {'rows':len(rows)}
@app.delete('/api/projects/{pid}/import/{role}')
def remove_import(pid:str,role:str):
 if role not in ('primary','secondary'):raise ValueError('角色無效')
 with service.lock(pid):
  (service.folder(pid)/'imports'/(role+'.json')).unlink(missing_ok=True)
 return {'ok':True}
@app.post('/api/projects/{pid}/boundaries')
def boundaries(pid:str,file:UploadFile=File(...)):
 raw=file.file.read(25_000_001)
 if len(raw)>25_000_000:raise ValueError('區界不可超過25 MB')
 obj=json.loads(raw)
 if obj.get('type')!='FeatureCollection':raise ValueError('需要 WGS84 GeoJSON FeatureCollection')
 if obj.get('crs') and '4326' not in str(obj['crs']) and 'CRS84' not in str(obj['crs']):raise ValueError('請先轉成 WGS84 EPSG:4326')
 def coordinates(v):
  if isinstance(v,list) and len(v)>=2 and all(isinstance(x,(int,float)) for x in v[:2]):
   if not (118<=v[0]<=123 and 20<=v[1]<=27):raise ValueError('區界座標不在臺灣 WGS84 範圍')
  elif isinstance(v,list):
   for x in v:coordinates(x)
 for f in obj.get('features',[]):
  g=f.get('geometry') or {}
  if g.get('type') not in ('Polygon','MultiPolygon'):raise ValueError('區界必須是 Polygon/MultiPolygon')
  coordinates(g['coordinates'])
 with service.lock(pid):
  write_json(service.folder(pid)/'boundaries.json',obj);p=service.load(pid);p['stale']=True;service.save(p)
 return {'features':len(obj['features'])}
@app.post('/api/projects/{pid}/import-manual')
def manual_import(pid:str,file:UploadFile=File(...)):
 from openpyxl import load_workbook
 raw=file.file.read(25_000_001)
 if len(raw)>25_000_000:raise ValueError('Excel 不可超過25 MB')
 wb=load_workbook(io.BytesIO(raw),read_only=True,data_only=False)
 with service.lock(pid):
  p=service.load(pid);lookup={(r['district'],str(r['map_no']),r['name'],r['address']):r for r in p['records']};count=0
  for ws in wb:
   if ws.title not in {r['district'] for r in p['records']}:continue
   header=None
   for values in ws.iter_rows(values_only=True):
    if values and values[0]=='行程總覽/天':header=True;continue
    if not header or len(values)<9:continue
    r=lookup.get((ws.title,str(values[1]),values[2],values[4]))
    if r:
     birthday=str(values[7] or '');note=str(values[8] or '')
     for prefix in [r.get('policy',''),'不用去' if r['exclude'] else '']:
      if prefix and note.startswith(prefix):note=note[len(prefix):].lstrip('；')
     r.update(birthday=birthday,note=note);count+=1
  if count!=len(p['records']):raise ValueError(f'Excel 只對應到 {count}/{len(p["records"])} 筆，未套用；請使用此專案匯出的完整檔案。')
  p['stale']=True;service.save(p)
 return {'updated':count}
@app.get('/api/geocode')
def geocode(q:str):
 global LAST_GEO
 if not 3<=len(q)<=250:raise ValueError('請提供完整地址。')
 from urllib.parse import urlencode
 with GEO_LOCK:
  time.sleep(max(0,1.1-(time.monotonic()-LAST_GEO)))
  try:
   raw,_,_=download('https://nominatim.openstreetmap.org/search?'+urlencode({'q':q,'format':'jsonv2','countrycodes':'tw','limit':5,'addressdetails':1}))
   rows=json.loads(raw)
  finally:LAST_GEO=time.monotonic()
 return [{'lat':float(r['lat']),'lon':float(r['lon']),'label':r['display_name'],'source':f"https://www.openstreetmap.org/{r['osm_type']}/{r['osm_id']}"} for r in rows]

def start_job(pid,action):
 service.folder(pid)
 with JOBS_LOCK:
  if any(j['pid']==pid and j['state']=='running' for j in JOBS.values()):raise ValueError('此專案正在處理。')
  jid=uuid.uuid4().hex;j={'id':jid,'pid':pid,'state':'running','log':[]};JOBS[jid]=j
 def run():
  try:
   j['result']={'collect':service.collect,'generate':service.generate}[action](pid,lambda line:j['log'].append(line));j['state']='done'
  except Exception as e:
   j['state']='error';j['error']=str(e);j['log'].append('停止：'+str(e))
   (service.folder(pid)/'last-error.log').write_text(traceback.format_exc())
 threading.Thread(target=run,daemon=True).start();return {'job':jid}
@app.post('/api/projects/{pid}/jobs/{action}')
def job(pid:str,action:str):
 if action not in ('collect','generate'):raise ValueError('操作無效')
 return start_job(pid,action)
@app.get('/api/jobs/{jid}')
def job_status(jid:str):
 if jid not in JOBS:raise HTTPException(404,'任務不存在，可能已重新啟動；請重整專案。')
 return JOBS[jid]
@app.get('/api/projects/{pid}/files/{name}')
def file(pid:str,name:str):
 p=service.load(pid)
 if name not in ('workbook.xlsx','district-maps.pdf','deliverables.zip','validation.json'):raise HTTPException(404)
 if not p.get('latest_run'):raise HTTPException(404,'尚未產出')
 return FileResponse(service.folder(pid)/'runs'/p['latest_run']/name,filename=name)
@app.post('/api/demo')
def demo():
 sample=json.loads((service.ROOT/'examples/demo.json').read_text());p=service.create(sample['config'])
 p.update(records=sample['records'],collected_at=sample['collected_at']);service.save(p)
 return p
