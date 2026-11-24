import colorsys, hashlib, json, math, re, uuid
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlencode
import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.cluster.vq import kmeans2
from .sources import norm,download

FIELDS=('name','phone','address','owner','district')
def now():return datetime.now(timezone.utc).isoformat()
def write_json(path,obj):
 path=Path(path);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)
def maps_url(r):return 'https://www.google.com/maps/search/?'+urlencode({'api':1,'query':r['name']+' '+r['address']})
def color(day):
 if not day:return 'E4E7EC'
 return ''.join(f'{round(c*255):02X}' for c in colorsys.hsv_to_rgb((day*.61803398875)%1,.27,.98))
def identity(a,b):
 # Same name alone cannot prove branch identity. Exact name+address, or address+phone.
 addr=norm(a.get('address'))==norm(b.get('address'))
 phone=re.sub(r'\D','',a.get('phone',''))
 return addr and (norm(a['name'])==norm(b['name']) or (phone and phone==re.sub(r'\D','',b.get('phone',''))))
def merge(primary,secondary,previous=()):
 records=[];pending=[];conflicts=[];used=set();used_old=set();seen=set()
 maxno={}
 for old in previous:maxno[old['district']]=max(maxno.get(old['district'],0),old.get('map_no',0))
 for p in primary:
  key=(norm(p['name']),norm(p['address']))
  if key in seen:
   pending.append({**p,'reason':'主來源重複名稱與地址，保留第一筆，待確認差異'});continue
  seen.add(key);x={**p};candidates=[(i,s) for i,s in enumerate(secondary) if identity(p,s)]
  # Require a one-to-one match on both sides.
  if len(candidates)==1:
   i,s=candidates[0]
   if i not in used and sum(bool(identity(q,s)) for q in primary)==1:
    used.add(i);x['secondary_source']=s['source']
    for field in FIELDS:
     if p.get(field) and s.get(field) and norm(p[field])!=norm(s[field]):
      conflicts.append({'name':p['name'],'field':field,'primary':p[field],'secondary':s[field]})
     if not x.get(field):x[field]=s.get(field,'')
    if x.get('lat') is None and s.get('lat') is not None and norm(p['address'])==norm(s['address']):
     for k in ('lat','lon','geo_status','geo_source','geo_method'):x[k]=s.get(k)
  old=[r for r in previous if identity(x,r)]
  if len(old)==1 and old[0]['id'] not in used_old:
   prior=old[0];used_old.add(prior['id'])
   for k in ('id','birthday','note','policy','exclude','map_no'):x[k]=prior.get(k,'' if k!='exclude' else False)
   if prior.get('geo_status')=='confirmed' and norm(prior['address'])==norm(x['address']):
    for k in ('lat','lon','geo_status','geo_source','geo_method'):x[k]=prior.get(k)
   if prior['district']!=x['district']:
    maxno[x['district']]=maxno.get(x['district'],0)+1;x['map_no']=maxno[x['district']]
  else:
   maxno[x['district']]=maxno.get(x['district'],0)+1
   x.update(id=uuid.uuid4().hex,map_no=maxno[x['district']],birthday='',note='',policy='',exclude=False)
  x.update(day=None,stop=None);records.append(x)
 for i,s in enumerate(secondary):
  if i not in used:pending.append({**s,'reason':'次來源獨有或無法唯一對應；不排入行程'})
 for old in previous:
  if old['id'] not in used_old:pending.append({**old,'reason':'前次院所本次未可靠對應；保留人工資料，不判定歇業'})
 return records,pending,conflicts

def balanced_groups(rows):
 n=len(rows)
 if not n:return []
 k=math.ceil(n/8)
 if k==1:return [rows[:]]
 latitude=np.mean([r['lat'] for r in rows]);xy=np.array([[r['lon']*math.cos(math.radians(latitude))*111.32,r['lat']*110.57] for r in rows])
 slots=np.repeat(np.arange(k),[n//k+(i<n%k) for i in range(k)]);best=None
 for seed in range(12):
  centers,_=kmeans2(xy,k,minit='++',seed=seed);old=None
  for _ in range(35):
   _,cols=linear_sum_assignment(((xy[:,None,:]-centers[slots][None,:,:])**2).sum(2));labels=slots[cols]
   if old is not None and np.array_equal(old,labels):break
   old=labels.copy();centers=np.array([xy[labels==j].mean(0) for j in range(k)])
  score=sum(((xy[i]-centers[labels[i]])**2).sum() for i in range(n))
  if best is None or score<best[0]:best=score,labels.copy()
 groups=[[rows[i] for i in range(n) if best[1][i]==j] for j in range(k)]
 return sorted(groups,key=lambda g:(np.mean([r['lat'] for r in g]),np.mean([r['lon'] for r in g])))

def best_path(dist,times):
 n=len(dist)-1
 if not 1<=n<=8:raise ValueError('每組需為 1–8 家。')
 if not np.isfinite(dist).all() or not np.isfinite(times).all():raise ValueError('有無法通行的路段；請調整分組或交通方式。')
 dp={(1<<j,j):(float(dist[0,j+1]),float(times[0,j+1]),(j,)) for j in range(n)}
 for mask in range(1,1<<n):
  for j in range(n):
   if (mask,j) not in dp:continue
   d,t,order=dp[mask,j]
   for nxt in range(n):
    if mask>>nxt&1:continue
    key=(mask|1<<nxt,nxt);value=(d+dist[j+1,nxt+1],t+times[j+1,nxt+1],order+(nxt,))
    if key not in dp or value<dp[key]:dp[key]=value
 return min(dp[((1<<n)-1,j)] for j in range(n))

class Router:
 def __init__(self,cache,config,log):self.cache=cache;self.config=config;self.log=log
 def api(self,action,payload):
  url='https://valhalla1.openstreetmap.de/'+action
  key=hashlib.sha256((url+json.dumps(payload,sort_keys=True)).encode()).hexdigest()
  file=self.cache/(key+'.json')
  if file.exists():return json.loads(file.read_text())
  raw,_,_=download(url,payload=payload);obj=json.loads(raw)
  if 'error' in obj:raise ValueError('道路服務：'+str(obj['error']))
  write_json(file,obj);return obj
 def plan(self,rows):
  start=self.config.get('start_coordinate')
  if not start:raise ValueError('請先確認出發點座標。')
  if any(r.get('geo_status')!='confirmed' for r in rows if not r['exclude']):
   raise ValueError('尚有可拜訪院所未定位；請完成定位或明確設為不拜訪。')
  costing={'scooter':'motor_scooter','car':'auto','bicycle':'bicycle','walk':'pedestrian'}[self.config['transport']]
  opts={'use_ferry':0,'exclude_ferries':True}
  if costing=='motor_scooter':opts.update(use_highways=0,top_speed=50,exclude_highways=True)
  base={'costing':costing,'costing_options':{costing:opts},'units':'kilometers'}
  if self.config.get('exclude_locations'):base['exclude_locations']=self.config['exclude_locations']
  result=[]
  for day,group in enumerate(balanced_groups([r for r in rows if not r['exclude']]),1):
   self.log(f'規劃第 {day} 組，{len(group)} 家；查詢有方向道路矩陣')
   loc=[start]+[{'lat':r['lat'],'lon':r['lon']} for r in group]
   m=self.api('sources_to_targets',{**base,'sources':loc,'targets':loc})['sources_to_targets']
   dist=np.array([[v.get('distance') for v in row] for row in m],float);times=np.array([[v.get('time') for v in row] for row in m],float)
   d,t,order=best_path(dist,times);ordered=[group[i] for i in order]
   trip=self.api('route',{**base,'locations':[start]+[{'lat':r['lat'],'lon':r['lon']} for r in ordered]})['trip']
   if len(trip['legs'])!=len(ordered):raise ValueError('道路服務回傳站數不一致。')
   roads=sorted(set(name for leg in trip['legs'] for man in leg.get('maneuvers',[]) for name in man.get('street_names',[])))
   flagged=[name for name in roads if re.search(r'高速|快速|高架|國道|國[一二三四五六八十]|Freeway|Expressway',name,re.I)] if costing=='motor_scooter' else []
   # Review state remains explicit: street-name scanning is NOT legal access certification.
   status='需核對疑似禁行路段：'+ '、'.join(flagged) if flagged else ('待騎士核對白牌通行限制' if costing=='motor_scooter' else '依道路服務估計')
   result.append({'day':day,'stops':[r['id'] for r in ordered],'distance_km':trip['summary']['length'],
      'minutes':trip['summary']['time']/60,'matrix_km':float(d),'status':status,'flagged_roads':flagged,'legs':trip['legs']})
   for stop,r in enumerate(ordered,1):r.update(day=day,stop=stop)
  return result

def nav_url(origin,stops,transport):
 mode={'scooter':'two-wheeler','car':'driving','bicycle':'bicycling','walk':'walking'}[transport]
 def position(r):return f"{r['lat']},{r['lon']}"
 args={'api':1,'origin':position(origin),'destination':position(stops[-1]),'travelmode':mode}
 if len(stops)>1:args['waypoints']='|'.join(position(r) for r in stops[:-1])
 return 'https://www.google.com/maps/dir/?'+urlencode(args)

def validate(rows,routes):
 ids=[r['id'] for r in rows];visited=[id for route in routes for id in route['stops']]
 assert len(set(ids))==len(ids),'醫院 ID 重複'
 assert sorted(visited)==sorted(r['id'] for r in rows if not r['exclude']),'院所重複或遺漏'
 for route in routes:
  assert 1<=len(route['stops'])<=8,'容量錯誤'
  assert route['distance_km']>=0 and route['minutes']>=0
 for district in {r['district'] for r in rows}:
  nums=[r['map_no'] for r in rows if r['district']==district];assert len(nums)==len(set(nums)),'地圖編號重複'
 return {'hospitals':len(rows),'visits':len(visited),'days':len(routes),'excluded':sum(bool(r['exclude']) for r in rows),'checked_at':now()}
