import argparse,json,sys
from . import service

def main():
 p=argparse.ArgumentParser(description='動物醫院本機工作簿 CLI');sub=p.add_subparsers(dest='command',required=True)
 sub.add_parser('list')
 create=sub.add_parser('create');create.add_argument('config',help='設定 JSON 路徑')
 for name in ('collect','generate','update'):
  s=sub.add_parser(name);s.add_argument('project')
 args=p.parse_args()
 try:
  if args.command=='list':
   for f in service.DATA.glob('*/project.json'):
    obj=json.loads(f.read_text());print(obj['id'],obj['config']['city'],len(obj['records']))
  elif args.command=='create':print(service.create(json.load(open(args.config,encoding='utf-8')))['id'])
  else:
   if args.command in ('collect','update'):service.collect(args.project,lambda s:print(s,flush=True))
   if args.command in ('generate','update'):service.generate(args.project,lambda s:print(s,flush=True))
 except Exception as e:print('停止：'+str(e),file=sys.stderr);return 1
 return 0
if __name__=='__main__':sys.exit(main())
