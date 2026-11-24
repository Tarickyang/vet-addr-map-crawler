import contextlib,fcntl,json,os,re,uuid,threading
from pathlib import Path
from .engine import write_json,merge,now,Router,validate
from .sources import Collector,normalize,parse,norm
from .outputs import build
ROOT=Path(__file__).resolve().parent.parent
DATA=Path(os.environ.get('VET_DATA_DIR',str(ROOT/'data'))).resolve()
DATA.mkdir(parents=True,exist_ok=True)
PLOT_LOCK=threading.Lock() # Matplotlib global state is not thread-safe across projects.

def folder(pid):
 if not re.fullmatch('[a-f0-9]{32}',pid):raise ValueError('專案 ID 無效。')
 path=DATA/pid
 if not (path/'project.json').exists():raise ValueError('找不到專案。')
 return path

def load(pid):return json.loads((folder(pid)/'project.json').read_text())
def save(p):write_json(folder(p['id'])/'project.json',p)
@contextlib.contextmanager
def lock(pid):
 with (folder(pid)/'.lock').open('w') as f:
  try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise ValueError('此專案正在處理，請稍後再試。')
  try:yield
  finally:fcntl.flock(f,fcntl.LOCK_UN)

def config_check(c):
 for field in ('city','start_address','primary_url','secondary_url'):
  if not isinstance(c.get(field),str) or not c[field].strip():raise ValueError('請填寫 '+field)
 if not re.fullmatch(r'[\u4e00-\u9fff]{2,6}[市縣]',c['city']):raise ValueError('縣市請用完整名稱，例如臺北市、新竹縣。')
 if c.get('transport') not in ('scooter','car','bicycle','walk'):raise ValueError('交通方式無效。')
 for role in ('primary','secondary'):
  if not isinstance(c.get(role+'_options',{}),dict):raise ValueError('來源進階設定必須是 JSON 物件。')
 start=c.get('start_coordinate')
 if start:
  if not (20<=float(start['lat'])<=27 and 118<=float(start['lon'])<=123):raise ValueError('起點經緯度不在臺灣範圍。')
  if not c.get('start_geo_source'):raise ValueError('請記錄起點座標來源。')
 return c

def create(config):
 config_check(config);pid=uuid.uuid4().hex;path=DATA/pid;path.mkdir()
 for sub in ('cache','runs','imports','snapshots'): (path/sub).mkdir()
 p={'id':pid,'config':config,'records':[],'pending':[],'conflicts':[],'created_at':now(),'stale':True,'routes':[]}
 write_json(path/'project.json',p);return p

def collect(pid,log):
 with lock(pid):
  p=load(pid);config=p['config'];snapshot=folder(pid)/'snapshots'/uuid.uuid4().hex;snapshot.mkdir()
  collector=Collector(snapshot,log);found={};rejected=[]
  for role in ('primary','secondary'):
   local=folder(pid)/'imports'/(role+'.json')
   if local.exists():
    blob=json.loads(local.read_text());rawrows=blob['rows'];source=blob['source']
    found[role],bad=normalize(rawrows,source,config['city'],config.get(role+'_options',{}).get('mapping'));log(f'{role} 使用已匯入快照；不會自動重新下載')
    write_json(snapshot/(role+'-import.json'),blob)
   else:found[role],bad=collector.collect(config[role+'_url'],config['city'],config.get(role+'_options',{}))
   rejected+=bad
  old=p['records'];new,pending,conflicts=merge(found['primary'],found['secondary'],old+[r for r in p.get('pending',[]) if r.get('id') and r['id'] not in {x['id'] for x in old}])
  # Never publish a sudden loss automatically; raw snapshots remain reviewable.
  if old and len(new)<len(old)*.8:raise ValueError(f'主名單由 {len(old)} 降至 {len(new)}，超過 20% 減少；已停止，保留舊資料。請檢查完整性或另建專案。')
  p.update(records=new,pending=pending+rejected,conflicts=conflicts,collected_at=now(),stale=True,routes=[])
  save(p);log(f'完成：{len(new)} 家；待確認 {len(pending)+len(rejected)} 筆；欄位衝突 {len(conflicts)} 筆')
 return {'hospitals':len(new),'pending':len(pending)+len(rejected)}

def generate(pid,log):
 with lock(pid):
  p=load(pid)
  if not p['records']:raise ValueError('請先擷取或匯入來源。')
  for r in p['records']:r.update(day=None,stop=None)
  cache=folder(pid)/'cache';p['routes']=Router(cache,p['config'],log).plan(p['records']);p['validation']=validate(p['records'],p['routes'])
  run=uuid.uuid4().hex;out=folder(pid)/'runs'/run;out.mkdir()
  boundary_file=folder(pid)/'boundaries.json';boundaries=json.loads(boundary_file.read_text()) if boundary_file.exists() else None
  if boundaries and not p['config'].get('boundary_source'):raise ValueError('已匯入區界但未填來源網址。')
  with PLOT_LOCK:result=build(p,out,cache,boundaries,log)
  p.update(latest_run=run,stale=False,generated_at=now(),result=result);save(p)
  log('Excel 讀回驗證通過，PDF 與內嵌地圖已完成。');return result
