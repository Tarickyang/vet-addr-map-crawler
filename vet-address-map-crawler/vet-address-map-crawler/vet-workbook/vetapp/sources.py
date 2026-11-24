"""Explicit, auditable source adapters. Never interpret a portal as an empty dataset."""
import csv, io, ipaddress, json, re, socket, time, unicodedata
from urllib.parse import urlparse, urljoin, parse_qs, urlencode, urlunparse
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup

UA = 'VetWorkbookLocal/1.0 (user-initiated public veterinary directory research)'
ALIASES = {
 'name':['name','醫院名稱','機構名稱','動物醫院名稱','動物診療機構名稱','診療機構名稱','動物醫療機構名稱'],
 'phone':['phone','電話','電話號碼','聯絡電話','機構電話'],
 'address':['address','地址','聯絡地址','機構地址','開業地址','診療機構地址'],
 'city':['city','縣市','縣市名稱'],
 'owner':['owner','負責人','負責人姓名','負責獸醫師','醫院負責人名稱','負責人名稱'],
 'district':['district','行政區','鄉鎮市區','鄉鎮區'],
 'lat':['lat','latitude','緯度'], 'lon':['lon','lng','longitude','經度'],
}
def norm(value):
 return re.sub(r'\s+', '', unicodedata.normalize('NFKC',str(value or ''))).replace('臺','台')

def public_url(url):
 p=urlparse(url)
 if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:
  raise ValueError('來源必須是公開 HTTP/HTTPS 網址，不可含帳號密碼。')
 if p.hostname.lower() in ('localhost','metadata.google.internal') or p.hostname.lower().endswith(('.localhost','.local','.internal')):
  raise ValueError('不接受內網主機名稱。')
 try:
  literal=ipaddress.ip_address(p.hostname)
 except ValueError:literal=None
 if literal is not None and not literal.is_global:raise ValueError('不接受本機、內網或保留位址。')
 try:resolved=socket.getaddrinfo(p.hostname,p.port or (443 if p.scheme=='https' else 80),type=socket.SOCK_STREAM)
 except socket.gaierror:
  # Managed HTTP proxies resolve public DNS remotely; keep inherited proxy intact.
  if not requests.utils.get_environ_proxies(url).get(p.scheme):raise ValueError('無法解析來源主機名稱，請檢查網址及網路。')
  resolved=[]
 for info in resolved:
  if not ipaddress.ip_address(info[4][0]).is_global:
   raise ValueError('不接受本機、內網或保留位址；本機資料請用匯入。')
 return url

def download(url, *, payload=None, limit=25_000_000):
 # Validate every redirect. Bounded response and timeout; no shell execution.
 for _ in range(6):
  public_url(url)
  with requests.request('POST' if payload is not None else 'GET',url,json=payload,
                        headers={'User-Agent':UA},timeout=(10,70),allow_redirects=False,stream=True) as r:
   if r.is_redirect:
    url=urljoin(url,r.headers['Location']);continue
   r.raise_for_status(); chunks=[];size=0
   for chunk in r.iter_content(65536):
    size+=len(chunk)
    if size>limit:raise ValueError('來源超過 25 MB；請下載後整理為 CSV/JSON 匯入。')
    chunks.append(chunk)
   return b''.join(chunks),r.headers.get('Content-Type',''),url
 raise ValueError('來源重新導向過多。')

def records_from_json(obj,path=''):
 if path:
  for key in path.split('.'):
   obj=obj[int(key)] if isinstance(obj,list) else obj[key]
 if isinstance(obj,list) and all(isinstance(x,dict) for x in obj):return obj
 if isinstance(obj,dict):
  for key in ('results','records','data','result'):
   if key in obj:
    try:return records_from_json(obj[key])
    except ValueError:pass
 raise ValueError('找不到 JSON 紀錄陣列；請指定 record_path，例如 result.results。')

def parse(raw,content_type='',path=''):
 text=raw.decode('utf-8-sig',errors='strict')
 if text.lstrip().startswith(('[','{')):
  return records_from_json(json.loads(text),path)
 if '<html' not in text[:2000].lower() and '<table' not in text.lower():
  try:dialect=csv.Sniffer().sniff(text[:8192],delimiters=',\t;')
  except csv.Error:dialect=csv.excel
  rows=list(csv.DictReader(io.StringIO(text),dialect=dialect))
  if rows:return rows
 s=BeautifulSoup(text,'html.parser');tables=[]
 for table in s.select('table'):
  trs=table.select('tr');headers=[];rows=[]
  for tr in trs:
   cells=tr.find_all(['td','th'],recursive=False)
   if not cells:continue
   vals=[c.get_text(' ',strip=True) for c in cells]
   if not headers:headers=vals;continue
   if len(vals)==len(headers):rows.append(dict(zip(headers,vals)))
  if rows:tables.append(rows)
 if tables:return max(tables,key=len)
 raise ValueError('此網址不是可辨識的 CSV、JSON 或 HTML 表格。請使用實際 API/下載網址，或匯入資料；JavaScript 網頁需要專用 adapter。')

def normalize(rows,source,city,mapping=None):
 mapping=mapping or {}; result=[];rejected=[]
 if not rows:raise ValueError('來源沒有紀錄，已停止，保留上次成果。')
 headers=list(rows[0]);keys={norm(k):k for k in headers}
 fields={f:mapping.get(f) or next((keys[norm(a)] for a in aliases if norm(a) in keys),None) for f,aliases in ALIASES.items()}
 if not fields['name'] or not fields['address']:
  raise ValueError('找不到名稱/地址欄位。可用欄位：'+', '.join(headers[:40])+'；請在進階設定提供 mapping。')
 for index,row in enumerate(rows,1):
  x={f:str(row.get(k,'') if row.get(k) is not None else '').strip() if k else '' for f,k in fields.items()}
  x.update(source=source,source_row=index,raw=row)
  if not x['name'] or not x['address']:
   rejected.append({**x,'reason':'缺少名稱或地址'});continue
  # Address must explicitly contain selected city. No guessing cross-city records.
  if norm(city) not in norm(x['address']) and norm(x.get('city'))==norm(city):
   # Explicit separate city field, not an inferred county. Original row is retained.
   x['address']=x['city']+x['address']
  if norm(city) not in norm(x['address']):
   rejected.append({**x,'reason':'地址未明列所選縣市，請確認'});continue
  if not x['district']:
   after=norm(x['address']).split(norm(city),1)[1]
   m=re.match(r'(.{1,6}?[區鄉鎮市])',after)
   x['district']=m.group(1) if m else ''
  if not x['district'] or not re.fullmatch(r'[\u4e00-\u9fff]{1,8}[區鄉鎮市]',x['district']):
   rejected.append({**x,'reason':'無法辨識行政區，請提供 district 欄位'});continue
  try:
   x['lat'],x['lon']=float(x['lat']),float(x['lon'])
   if not (20<=x['lat']<=27 and 118<=x['lon']<=123):raise ValueError()
   x.update(geo_source=source,geo_status='confirmed',geo_method='來源明列 WGS84 經緯度')
  except (ValueError,TypeError):
   x['lat']=x['lon']=None;x['geo_status']='missing'
  result.append(x)
 if not result:raise ValueError('沒有可用的本縣市資料；請檢查縣市名稱、地址及欄位對應。')
 return result,rejected

class Collector:
 def __init__(self,snapshot,log):self.snapshot=snapshot;self.log=log;self.robots={}
 def get(self,url):
  p=urlparse(url);origin=f'{p.scheme}://{p.netloc}'
  if origin not in self.robots:
   try:
    body,_,_=download(origin+'/robots.txt',limit=1_000_000)
    rp=RobotFileParser();rp.parse(body.decode('utf-8',errors='replace').splitlines());self.robots[origin]=rp
   except requests.HTTPError as e:
    if e.response.status_code in (401,403):raise ValueError('robots.txt 拒絕讀取，請使用網站正式下載或本機匯入。') from e
    self.robots[origin]=None
   except requests.RequestException:self.robots[origin]=None
  rp=self.robots[origin]
  if rp and not rp.can_fetch(UA,url):raise ValueError('來源 robots.txt 不允許爬取此路徑；請使用正式下載或匯入。')
  time.sleep(max(.3,min(10,(rp.crawl_delay(UA) or rp.crawl_delay('*') or 0))) if rp else .3)
  raw,ct,final=download(url)
  import hashlib
  key=hashlib.sha256(url.encode()).hexdigest()[:16]
  (self.snapshot/(key+'.bin')).write_bytes(raw)
  (self.snapshot/(key+'.json')).write_text(json.dumps({'url':url,'final_url':final,'content_type':ct},ensure_ascii=False))
  return raw,ct
 def collect(self,url,city,options):
  self.log('讀取來源：'+url)
  # Known Taipei portal: resolve exact resource API, not arbitrary guessed links.
  if 'data.taipei/dataset/detail' in url and '01bcb5ee-7c18-41fa-86d4-4e75daee1f94' in url:
   url='https://data.taipei/api/v1/dataset/40d79051-1839-4d00-855f-be88f1e06caf?scope=resourceAquire&limit=1000&offset=0'
  raw,ct=self.get(url);rows=parse(raw,ct,options.get('record_path',''))
  if 'tpvma.org.tw/client' in url:
   soup=BeautifulSoup(raw,'html.parser');pages=max([1]+[int(o.get('value')) for o in soup.select('option') if str(o.get('value','')).isdigit()])
   if pages>200:raise ValueError('來源頁數異常。')
   for p in range(2,pages+1):
    b,c=self.get('https://www.tpvma.org.tw/client/?p='+str(p));rows+=parse(b,c)
  elif 'data.taipei/api/v1/dataset/' in url:
   obj=json.loads(raw);count=int(obj['result']['count']);offset=len(rows)
   while offset<count:
    p=urlparse(url);q=parse_qs(p.query);q.update(offset=[str(offset)],limit=['1000'])
    b,c=self.get(urlunparse(p._replace(query=urlencode(q,doseq=True))));extra=parse(b,c)
    if not extra:raise ValueError('API 分頁提早結束。')
    rows+=extra;offset+=len(extra)
   if len(rows)!=count:raise ValueError('API count 與實際筆數不符。')
  elif options.get('page_url'):
   template=options['page_url'];pages=int(options.get('pages',0))
   if not 1<=pages<=200 or '{page}' not in template:raise ValueError('page_url 必須含 {page}，pages 為 1–200。第一頁使用來源網址。')
   for p in range(2,pages+1):
    b,c=self.get(template.replace('{page}',str(p)));rows+=parse(b,c,options.get('record_path',''))
  else:
   # Generic paginated data must never quietly become a one-page "complete" result.
   try:
    obj=json.loads(raw);meta=obj.get('result',obj) if isinstance(obj,dict) else {}
    count=meta.get('count',meta.get('total',meta.get('totalCount'))) if isinstance(meta,dict) else None
    if count is not None and int(count)>len(rows):raise ValueError('此 API 有分頁，請在進階設定指定 page_url 與 pages，或匯入完整下載檔。')
   except (json.JSONDecodeError,UnicodeDecodeError):pass
   if not options.get('complete_confirmed'):
    raise ValueError('通用來源需確認是完整名單：進階設定 complete_confirmed: true。若有分頁請先設定 page_url/pages，不要只匯入第一頁。')
  return normalize(rows,url,city,options.get('mapping'))
