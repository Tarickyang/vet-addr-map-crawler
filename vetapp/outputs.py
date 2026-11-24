"""One map image supplies both workbook and PDF; native XLSX hyperlinks, no formulas."""
import io,json,math,re,zipfile
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.backends.backend_pdf import PdfPages
from adjustText import adjust_text
from PIL import Image as PILImage
from openpyxl import Workbook,load_workbook
from openpyxl.styles import Font,PatternFill,Alignment
from openpyxl.drawing.image import Image
from openpyxl.utils import get_column_letter
from .engine import color,maps_url,nav_url,now
from .sources import download

HEADERS=['行程總覽/天','地圖編號','醫院名稱','電話','地址','Google Maps','醫院負責人名稱','生日','備注']
FONT=next((str(p) for p in Path('/usr/share/fonts').rglob('*CJK*') if p.suffix in ('.ttc','.otf','.ttf')),None)
if FONT:
 font_manager.fontManager.addfont(FONT)
 plt.rcParams['font.family']=font_manager.FontProperties(fname=FONT).get_name()
plt.rcParams['axes.unicode_minus']=False

def mercator(lon,lat):
 return lon*20037508.34/180,math.log(math.tan((90+lat)*math.pi/360))*20037508.34/math.pi

def basemap(ax,bounds,cache):
 xmin,xmax,ymin,ymax=bounds
 # Slippy-map XYZ, at most 24 tiles per district. Never bulk-prefetch.
 world=40075016.68
 for z in range(16,7,-1):
  n=2**z;unit=world/n
  xa=int((xmin+world/2)/unit);xb=int((xmax+world/2)/unit)
  ya=int((world/2-ymax)/unit);yb=int((world/2-ymin)/unit)
  if (xb-xa+1)*(yb-ya+1)<=24:break
 canvas=PILImage.new('RGB',((xb-xa+1)*256,(yb-ya+1)*256),'white')
 for x in range(xa,xb+1):
  for y in range(ya,yb+1):
   file=cache/f'osm-{z}-{x}-{y}.png'
   if not file.exists():
    raw,_,_=download(f'https://tile.openstreetmap.org/{z}/{x}/{y}.png',limit=1_000_000)
    file.write_bytes(raw)
   tile=PILImage.open(file).convert('RGB');canvas.paste(tile,((x-xa)*256,(y-ya)*256))
 ax.imshow(canvas,extent=(xa*unit-world/2,(xb+1)*unit-world/2,world/2-(yb+1)*unit,world/2-ya*unit),alpha=.8)

def draw_boundaries(ax,geo):
 if not geo:return
 for f in geo.get('features',[]):
  geom=f.get('geometry') or {};typ=geom.get('type');coords=geom.get('coordinates',[])
  polygons=coords if typ=='MultiPolygon' else [coords] if typ=='Polygon' else []
  for polygon in polygons:
   for ring in polygon:
    points=[mercator(*p[:2]) for p in ring];ax.plot(*zip(*points),color='#344054',lw=1,zorder=2)

def make_maps(rows,out,config,cache,boundaries,log):
 images={};warnings=[]
 with PdfPages(out/'district-maps.pdf') as pdf:
  for district in sorted({r['district'] for r in rows}):
   group=[r for r in rows if r['district']==district and r.get('geo_status')=='confirmed']
   fig,ax=plt.subplots(figsize=(14.8,7.2),dpi=110);fig.subplots_adjust(left=.02,right=.98,top=.90,bottom=.18)
   status=[]
   if group:
    points=[mercator(r['lon'],r['lat']) for r in group]
    xs,ys=zip(*points);width=max(max(xs)-min(xs),700)*1.25;height=max(max(ys)-min(ys),700)*1.25
    width=max(width,height*1.9);height=max(height,width/1.9)
    cx=(max(xs)+min(xs))/2;cy=(max(ys)+min(ys))/2;bounds=(cx-width/2,cx+width/2,cy-height/2,cy+height/2)
    if config.get('street_tiles',True):
     try:basemap(ax,bounds,cache);status.append('© OpenStreetMap contributors')
     except Exception as e:status.append('街道底圖取得失敗；僅顯示座標點');warnings.append(f'{district}：底圖取得失敗 ({type(e).__name__})')
    else:status.append('座標示意圖（未使用街道底圖）')
    draw_boundaries(ax,boundaries)
    ax.set_xlim(*bounds[:2]);ax.set_ylim(*bounds[2:]);ax.set_aspect('equal')
    texts=[]
    for r,(x,y) in zip(group,points):
     ax.plot(x,y,'.',color='#344054',ms=4,zorder=4)
     texts.append(ax.text(x,y,str(r['map_no']),fontsize=10,ha='center',va='center',zorder=6,
       color='#C00000' if r['exclude'] or r.get('policy') else '#101828',
       bbox={'boxstyle':'round,pad=.26','fc':'#'+color(r['day']),'ec':'#667085','lw':.6}))
    adjust_text(texts,x=list(xs),y=list(ys),ax=ax,iter_lim=180,arrowprops={'arrowstyle':'-','color':'#667085','lw':.6})
   else:ax.text(.5,.5,'本區尚無確認座標',ha='center',va='center',transform=ax.transAxes)
   status.append('區界來源：'+config.get('boundary_source','未提供官方區界') if boundaries else '未提供官方行政區界')
   ax.annotate('N',xy=(.975,.98),xytext=(.975,.86),xycoords='axes fraction',ha='center',fontsize=12,fontweight='bold',arrowprops={'arrowstyle':'-|>','color':'#183153'},color='#183153',zorder=10)
   ax.set_axis_off();ax.set_title(f"{config['city']} {district}｜數字＝地圖編號；底色＝拜訪天數",fontsize=17,pad=12)
   days=sorted({r['day'] for r in group if r.get('day')})
   from matplotlib.patches import Patch
   handles=[Patch(facecolor='#'+color(d),edgecolor='#667085',label=f'第 {d} 天') for d in days]
   if any(r['exclude'] for r in group):handles.append(Patch(facecolor='#E4E7EC',label='不用去'))
   if handles:fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.055),ncol=min(12,len(handles)),fontsize=9)
   fig.text(.02,.025,' · '.join(status),fontsize=8,color='#475467')
   fig.text(.02,.005,'同色為同一天（最多8家，可能跨區）；行程先分組，再求組內道路矩陣最短順序。',fontsize=8)
   filename=f'map-{len(images)+1:02d}.png';fig.savefig(out/filename);pdf.savefig(fig);plt.close(fig);images[district]=filename
   log('地圖完成：'+district)
 return images,warnings

def literal(cell,value):
 cell.value='' if value is None else str(value)
 cell.data_type='s' # prevent formula injection in names, phones, notes and scraped cells

def sheet_table(wb,title,headers,rows):
 ws=wb.create_sheet(title);ws.append(headers)
 for row in rows:
  for col,value in enumerate(row,1):literal(ws.cell(ws.max_row+1 if col==1 else ws.max_row,col),value)
 ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
 for cell in ws[1]:cell.fill=PatternFill('solid',fgColor='183153');cell.font=Font(color='FFFFFF',bold=True)
 for i in range(1,len(headers)+1):ws.column_dimensions[get_column_letter(i)].width=23 if i<5 else 45
 return ws

def make_workbook(project,out,images,warnings):
 rows=project['records'];routes=project['routes'];config=project['config'];byid={r['id']:r for r in rows}
 wb=Workbook();wb.remove(wb.active)
 info=[['產生時間',now()],['縣市',config['city']],['出發點',config['start_address']],['交通',config['transport']],
  ['規劃方式','先容量分組，再求每組最多8家的有向道路矩陣最短順序；可跨區、不返程，非全市全域最優。'],
  ['白牌機車','道路服務不能保證白牌通行合法性；請查看行程總覽路段警示，出發前核對現場交通標誌。'],
  ['估計時間','不含拜訪、停車、休息及即時交通。'],['地圖','表格與地圖數字底色一致；數字是院所編號，不是拜訪站序。'],
  ['人工資料','在本機介面編輯生日/備注/不用去可於更新保留；Excel 修改須先匯回本機再更新。'],
  ['Google Sheets','此為本機 Excel。可手動匯入 Google Sheets；圖片轉換須檢查，不宣稱已同步或永久嵌圖。'],
  ['待確認',str(len(project.get('pending',[])))],['地圖提醒','；'.join(warnings) or '無底圖下載錯誤'],
  ['官方區界',config.get('boundary_source','未提供')],['來源完整性','通用來源的完整性由使用者確認；已知臺北 adapter 會檢查分頁。']]
 sheet_table(wb,'使用說明',['項目','說明'],info)
 for district in sorted(images):
  ws=wb.create_sheet(district[:31]);ws.merge_cells('A1:I1');ws['A1']=config['city']+' '+district+'｜同色＝同一天，最多8家（可跨區）'
  ws['A1'].font=Font(size=16,bold=True,color='183153');ws.row_dimensions[1].height=30
  img=Image(str(out/images[district]));img.width=1280;img.height=623;ws.add_image(img,'A3')
  for ri in range(3,35):ws.row_dimensions[ri].height=15
  header=36
  for i,value in enumerate(HEADERS,1):ws.cell(header,i,value);ws.cell(header,i).fill=PatternFill('solid',fgColor='183153');ws.cell(header,i).font=Font(color='FFFFFF',bold=True)
  ordered=sorted((r for r in rows if r['district']==district),key=lambda r:(r.get('day') or 999999,r.get('stop') or 999999,r['map_no']))
  for ri,r in enumerate(ordered,header+1):
   note='；'.join(filter(None,[r.get('policy'),r.get('note')]))
   if r['exclude'] and '不用去' not in note:note='不用去'+('；'+note if note else '')
   values=[r['day'] or '不用去',r['map_no'],r['name'],r.get('phone',''),r['address'],'開啟 Google Maps',r.get('owner',''),r.get('birthday',''),note]
   for ci,value in enumerate(values,1):
    cell=ws.cell(ri,ci);literal(cell,value);cell.fill=PatternFill('solid',fgColor=color(r['day']));cell.alignment=Alignment(vertical='center',wrap_text=True)
    if ci in (3,9) and (r['exclude'] or r.get('policy')):cell.font=Font(color='C00000')
   ws.cell(ri,6).hyperlink=maps_url(r);ws.cell(ri,6).font=Font(color='0563C1',underline='single')
   ws.row_dimensions[ri].height=40
  for i,width in enumerate([16,12,30,19,55,24,20,18,48],1):ws.column_dimensions[get_column_letter(i)].width=width
  ws.freeze_panes=f'C{header+1}';ws.auto_filter.ref=f'A{header}:I{ws.max_row}';ws.sheet_view.zoomScale=75
 overview=[];detail=[]
 for route in routes:
  stops=[byid[x] for x in route['stops']];first=nav_url(config['start_coordinate'],stops[:4],config['transport'])
  second=nav_url(stops[3],stops[4:],config['transport']) if len(stops)>4 else ''
  overview.append([route['day'],len(stops),'、'.join(sorted({r['district'] for r in stops})),round(route['distance_km'],2),round(route['minutes'],1),
   ' → '.join(r['name'] for r in stops),first,second,route['status']])
  for i,(r,leg) in enumerate(zip(stops,route['legs']),1):
   detail.append([route['day'],i,r['district'],r['map_no'],r['name'],r['phone'],r['address'],round(leg['summary']['length'],2),round(leg['summary']['time']/60,1),
    nav_url(config['start_coordinate'] if i==1 else stops[i-2],[r],config['transport']),r['id']])
 for title,headers,values,linkcols in [
  ('行程總覽',['天','家數','行政區','公里','騎乘分鐘','拜訪順序','前4站導航','後4站導航','道路核對'],overview,[7,8]),
  ('拜訪明細',['天','站序','行政區','地圖編號','醫院名稱','電話','地址','路段公里','分鐘','逐站導航','穩定ID'],detail,[10])]:
  ws=sheet_table(wb,title,headers,values)
  for ri,v in enumerate(values,2):
   for c in ws[ri]:c.fill=PatternFill('solid',fgColor=color(int(v[0])))
   for ci in linkcols:
    if v[ci-1]:ws.cell(ri,ci).hyperlink=v[ci-1];ws.cell(ri,ci).value='開啟導航';ws.cell(ri,ci).font=Font(color='0563C1',underline='single')
 sheet_table(wb,'待確認',['名稱','地址','原因','生日','備注','來源'],[[p.get(k,'') for k in ('name','address','reason','birthday','note','source')] for p in project.get('pending',[])])
 sheet_table(wb,'資料核對',['名稱','欄位','主來源值','次來源值'],[[p[k] for k in ('name','field','primary','secondary')] for p in project.get('conflicts',[])])
 sheet_table(wb,'更新與來源',['名稱','穩定ID','主來源','次來源','擷取時間'],[[r['name'],r['id'],r.get('source',''),r.get('secondary_source',''),project.get('collected_at','')] for r in rows])
 sheet_table(wb,'業務規則',['穩定ID','名稱','不用去','產品限制','人工備注'],[[r['id'],r['name'],r['exclude'],r.get('policy',''),r.get('note','')] for r in rows])
 sheet_table(wb,'定位資料',['穩定ID','名稱','地址','緯度','經度','定位來源','定位方法'],[[r['id'],r['name'],r['address'],r.get('lat'),r.get('lon'),r.get('geo_source',''),r.get('geo_method','')] for r in rows])
 path=out/'workbook.xlsx';wb.save(path)
 # Read back actual serialized workbook, images, native hyperlinks and colors.
 check=load_workbook(path);count=0
 for district in images:
  ws=check[district[:31]];assert len(ws._images)==1,'地圖未嵌入'
  ordered=sorted((r for r in rows if r['district']==district),key=lambda r:(r.get('day') or 999999,r.get('stop') or 999999,r['map_no']))
  for ri,r in enumerate(ordered,37):
   assert ws.cell(ri,6).hyperlink.target==maps_url(r)
   assert ws.cell(ri,1).fill.fgColor.rgb[-6:]==color(r['day'])
   assert (ws.cell(ri,8).value or '')==r.get('birthday','')
   assert not any(c.data_type=='f' for c in ws[ri]);count+=1
 assert count==len(rows)
 return {'xlsx_readback_rows':count,'embedded_maps':len(images),'mobile_url_format':'Google Maps api=1 + native hyperlink'}

def build(project,out,cache,boundaries,log):
 images,warnings=make_maps(project['records'],out,project['config'],cache,boundaries,log)
 check=make_workbook(project,out,images,warnings)
 from .engine import write_json
 write_json(out/'project-snapshot.json',project);write_json(out/'validation.json',{**project['validation'],**check,'map_warnings':warnings})
 with zipfile.ZipFile(out/'deliverables.zip','w',zipfile.ZIP_DEFLATED) as z:
  for file in out.iterdir():
   if file.name!='deliverables.zip':z.write(file,file.name)
 return {'files':['workbook.xlsx','district-maps.pdf','deliverables.zip','validation.json'],'warnings':warnings,**check}
