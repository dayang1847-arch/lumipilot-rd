import hashlib,json,re,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
m=json.loads((R/'release-manifest.json').read_text())
assert m['raw_sources_included'] is False and m['auth_config_included'] is False
for f in m['files']:
    p=R/f['path'];assert p.is_file(),f['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==f['sha256'],f['path']
    if p.suffix in ['.html','.js','.json','.css']:
        s=p.read_text();assert '/Users/' not in s, f['path']
assert not (R/'web/资料快照').exists()
assert not (R/'web/auth.json').exists()
assert not (R/'web/index_v3.html').exists()
assert not (R/'web/bootstrap.json').exists()
assert m['private_research_payload_included'] is False
markup=(R/'web/index.html').read_text()
for id in ['library-data','case-data']:
    content=re.search(r'<script[^>]*id="'+id+r'"[^>]*>(.*?)</script>',markup,re.S)[1]
    data=json.loads(content)
    assert data in [{},{'products':[],'sources':[]}]
for p in (R/'web').rglob('*'):
    assert p.suffix not in ['.pdf','.xlsx','.xlsm','.pptx'],p

print(f'Release verified: {len(m["files"])} resources, no runtime credentials or raw source tree.')
