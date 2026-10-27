"""Separate public application code from private R&D payloads."""
import argparse,hashlib,json,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REMOVED={'original_path','local_path','offline_path','source_root','local_root','cache_root','original_root'}
def sanitize(v):
    if isinstance(v,dict):return {k:sanitize(x) for k,x in v.items() if k not in REMOVED}
    if isinstance(v,list):return [sanitize(x) for x in v]
    if isinstance(v,str) and v.startswith('/Users/'):return '[本机路径已移除]'
    return v

def pack(src):
    src=Path(src);private=ROOT/'.runtime/private-web';private.mkdir(parents=True,exist_ok=True)
    dest=ROOT/'web'
    if dest.exists():shutil.rmtree(dest)  # Only the generated application output, never source originals.
    dest.mkdir()
    for name in ['ui-v4.css','ui-v4.js','页面使用说明_v4.md']:shutil.copy2(src/name,dest/name)
    shutil.copytree(src/'ui-assets',dest/'ui-assets',dirs_exist_ok=True)
    for name in ['系统工程方法与使用说明_v3.md','研发资料增量分析与方法提炼_v2.pdf']:shutil.copy2(src/name,private/name)
    for name in ['电子研发知识库_v3.json','电子研发知识网络_v3.json','文件完整性与读取记录.json']:
        (private/name).write_text(json.dumps(sanitize(json.loads((src/name).read_text())),ensure_ascii=False,separators=(',',':')))
    library=json.loads((private/'电子研发知识库_v3.json').read_text());cases=sanitize(json.loads((src/'ui-case-data.json').read_text()))
    (private/'bootstrap.json').write_text(json.dumps({'library':library,'cases':cases},ensure_ascii=False,separators=(',',':')))
    markup=(src/'index.html').read_text()
    for id,value in [('library-data',{'products':[],'sources':[]}),('case-data',{})]:
        markup=re.sub(r'(<script[^>]*id="'+id+r'"[^>]*>).*?(</script>)',lambda m:m[1]+json.dumps(value)+m[2],markup,flags=re.S)
    markup=markup.replace('<b>LumiPilot</b>','<b>LumiPilot-R&amp;D</b>').replace('LumiPilot · 电子方案助手','LumiPilot-R&amp;D · 电子研发方案台').replace('<span>电子方案助手</span>','<span>电子研发方案台</span>')
    (dest/'index.html').write_text(markup)
    legacy=(src/'index_v3.html').read_text()
    def clean(m):return m[1]+json.dumps(sanitize(json.loads(m[2])),ensure_ascii=False,separators=(',',':'))+m[3]
    legacy=re.sub(r'(<script[^>]*type="application/json"[^>]*>)(.*?)(</script>)',clean,legacy,flags=re.S)
    blocks=re.findall(r'<script>(.*?)</script>',legacy,re.S)
    if len(blocks)!=1:raise ValueError('Expected one legacy executable script')
    (private/'legacy-workbench.js').write_text(blocks[0]);legacy=re.sub(r'<script>.*?</script>','<script src="legacy-workbench.js"></script>',legacy,flags=re.S)
    (private/'index_v3.html').write_text(legacy)
    with (dest/'ui-v4.css').open('a') as f:f.write('\n.rd-logout{margin:0}.rd-logout button{font-size:12px;padding:6px 9px;color:var(--teal);white-space:nowrap}.top-right{gap:16px}@media(max-width:760px){.brand{flex-wrap:wrap;gap:3px 12px}.top-right{justify-content:flex-start;flex-wrap:wrap;gap:8px}}\n')
    m={'app':'LumiPilot-R&D','date':'2026-10-27','raw_sources_included':False,'auth_config_included':False,'private_research_payload_included':False,'files':[]}
    for p in sorted(dest.rglob('*')):
        if p.is_file():m['files'].append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    (ROOT/'release-manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2))
    print(f'Packaged {len(m["files"])} public code resources. R&D payload isolated in ignored runtime storage.')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--from',dest='source',required=True);pack(p.parse_args().source)
