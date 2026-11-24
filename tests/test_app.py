import copy,itertools,json,os,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
os.environ['VET_DATA_DIR']=tempfile.mkdtemp(prefix='vet-tests-')
import numpy as np
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from vetapp import service
from vetapp.engine import merge,best_path,balanced_groups,validate,color,maps_url,Router
from vetapp.sources import parse,normalize,public_url
from vetapp.outputs import build
from vetapp.web import app

CONFIG={'city':'臺北市','start_address':'新北市土城區延吉街','primary_url':'https://example.com/main','secondary_url':'https://example.com/second','transport':'scooter','start_coordinate':{'lat':24.98,'lon':121.46},'start_geo_source':'已核對起點','street_tiles':False}
def source(name='測試醫院',address='臺北市大安區信義路1號',**kw):
 return dict(name=name,address=address,phone='02-01234567',owner='',district='大安區',source='https://example.com',lat=25.03,lon=121.53,geo_status='confirmed',**kw)
def rows(n=8):
 items=[source(name=f'測試{i}動物醫院',address=f'臺北市大安區信義路{i+1}號') for i in range(n)]
 for i,r in enumerate(items):r.update(lat=25.03+i*.002,lon=121.53+i*.001)
 return merge(items,[])[0]
def fake_api(self,action,payload):
 if action=='sources_to_targets':
  n=len(payload['sources']);return {'sources_to_targets':[[{'distance':abs(i-j)+(.1 if i<j else .3),'time':10*abs(i-j)+2} for j in range(n)] for i in range(n)]}
 n=len(payload['locations'])-1
 return {'trip':{'summary':{'length':n,'time':60*n},'legs':[{'summary':{'length':1,'time':60},'maneuvers':[{'street_names':['一般道路']}]} for _ in range(n)]}}

class CoreTests(unittest.TestCase):
 def test_merge_priority_missing_and_ambiguous(self):
  p=source();s=source();s.update(phone='999',owner='來源明列負責人');out,pending,conf=merge([p],[s]);self.assertEqual(out[0]['phone'],p['phone']);self.assertEqual(out[0]['owner'],s['owner']);self.assertEqual(len(conf),1)
  out,pending,_=merge([p],[s,copy.deepcopy(s)]);self.assertEqual(out[0]['owner'],'');self.assertEqual(len(pending),2)
 def test_rename_evidence_and_branch_not_fuzzy(self):
  p=source();s=source(name='舊院名');s['owner']='王先生';out,_,_=merge([p],[s]);self.assertEqual(out[0]['owner'],'王先生')
  s['address']='臺北市大安區其他路2號';out,pending,_=merge([p],[s]);self.assertEqual(out[0]['owner'],'');self.assertEqual(len(pending),1)
 def test_manual_preservation_and_removed_record(self):
  old=rows(2);old[0].update(note='已拜訪',birthday='05-18',exclude=True,policy='只推心臟')
  out,pending,_=merge([source(name=old[0]['name'],address=old[0]['address'])],[],old)
  for key in ('id','map_no','note','birthday','exclude','policy'):self.assertEqual(out[0][key],old[0][key])
  self.assertEqual(pending[0]['id'],old[1]['id'])
 def test_directed_path_matches_all_40320_permutations(self):
  rng=np.random.default_rng(12);d=rng.integers(1,99,(9,9));t=rng.integers(1,99,(9,9))
  expected=min((sum(d[a,b] for a,b in zip((0,)+p,p)),sum(t[a,b] for a,b in zip((0,)+p,p)),tuple(i-1 for i in p)) for p in itertools.permutations(range(1,9)))
  self.assertEqual(best_path(d,t),expected)
 def test_balanced_capacities_and_coverage(self):
  for n in (1,8,9,16,17,25):
   a=rows(n);g=balanced_groups(a);self.assertEqual(sum(map(len,g)),n);self.assertLessEqual(max(map(len,g)),8);self.assertLessEqual(max(map(len,g))-min(map(len,g)),1)
 def test_unknown_route_is_not_zero(self):
  with self.assertRaises(ValueError):best_path(np.array([[0,np.nan],[1,0]]),np.ones((2,2)))
 def test_explicit_city_column_not_inference(self):
  a,b=normalize([{'縣市':'臺北市','醫院名稱':'例院','地址':'大安區信義路1號','電話':'02-00001111'}],'test','臺北市')
  self.assertEqual(a[0]['phone'],'02-00001111');self.assertEqual(a[0]['address'],'臺北市大安區信義路1號')
  with self.assertRaises(ValueError):normalize([{'醫院名稱':'例院','地址':'大安區信義路1號'}],'test','臺北市')
 def test_source_formats(self):
  self.assertEqual(len(parse(b'name,address\nVet,Taipei\n')),1)
  self.assertEqual(parse(b'{"result":{"records":[{"name":"x"}]}}')[0]['name'],'x')
  with self.assertRaises(ValueError):parse(b'<html><body>JavaScript app</body></html>')
 def test_block_private_urls(self):
  for u in ('http://127.0.0.1/','http://169.254.169.254/','file:///etc/passwd'):
   with self.assertRaises(ValueError):public_url(u)
 def test_workbook_end_to_end_and_formula_safety(self):
  a=rows(9);a[-1]['exclude']=True;a[0].update(name='=DANGEROUS()',note='=1+2',birthday='05-18')
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp);router=Router(out,CONFIG,lambda s:None)
   with patch.object(Router,'api',fake_api):routes=router.plan(a)
   p={'config':CONFIG,'records':a,'routes':routes,'validation':validate(a,routes),'pending':[],'conflicts':[]}
   result=build(p,out,out,None,lambda s:None)
   self.assertEqual(result['embedded_maps'],1);self.assertEqual(result['xlsx_readback_rows'],9)
   wb=load_workbook(out/'workbook.xlsx');ws=wb['大安區'];self.assertEqual(len(ws._images),1)
   self.assertTrue(all(ws.cell(i,3).data_type=='s' for i in range(37,46)))
   self.assertEqual(ws.cell(45,1).value,'不用去');self.assertEqual(ws.cell(45,3).font.color.rgb,'00C00000')
   with zipfile.ZipFile(out/'deliverables.zip') as z:self.assertIn('district-maps.pdf',z.namelist())

class WebTests(unittest.TestCase):
 def setUp(self):self.client=TestClient(app);self.headers={'X-Vet-Local':'1'}
 def test_local_origin_and_create(self):
  r=self.client.post('/api/projects',json=CONFIG);self.assertEqual(r.status_code,403)
  r=self.client.post('/api/projects',json=CONFIG,headers={**self.headers,'Origin':'https://evil.example'});self.assertEqual(r.status_code,403)
  r=self.client.post('/api/projects',json=CONFIG,headers=self.headers);self.assertEqual(r.status_code,200);self.assertEqual(self.client.get('/api/projects/'+r.json()['id']).status_code,200)
 def test_import_collect_manual_update_and_failure_keeps_previous(self):
  p=service.create(copy.deepcopy(CONFIG));pid=p['id'];data=[{'name':'例院','address':'臺北市大安區信義路1號','phone':'021234','lat':'25.03','lon':'121.53'}]
  for role in ('primary','secondary'):
   r=self.client.post(f'/api/projects/{pid}/import/{role}',files={'file':('sample.json',json.dumps(data))},headers=self.headers);self.assertEqual(r.status_code,200)
  service.collect(pid,lambda s:None);p=service.load(pid);id=p['records'][0]['id']
  self.client.post(f'/api/projects/{pid}/records',json={'records':[{'id':id,'note':'保留','birthday':'01-02'}]},headers=self.headers)
  service.collect(pid,lambda s:None);self.assertEqual(service.load(pid)['records'][0]['note'],'保留')
  old=service.load(pid)
  with patch.object(Router,'api',side_effect=RuntimeError('network unavailable')):
   with self.assertRaises(RuntimeError):service.generate(pid,lambda s:None)
  self.assertEqual(service.load(pid),old)
 def test_start_address_change_invalidates_old_coordinate(self):
  p=service.create(copy.deepcopy(CONFIG));c=copy.deepcopy(CONFIG);c['start_address']='臺北市中山區別條路'
  r=self.client.put(f'/api/projects/{p["id"]}/config',json=c,headers=self.headers)
  self.assertEqual(r.status_code,200);self.assertNotIn('start_coordinate',r.json()['config'])
 def test_project_path_traversal(self):
  with self.assertRaises(ValueError):service.folder('../../etc')

if __name__=='__main__':unittest.main()
