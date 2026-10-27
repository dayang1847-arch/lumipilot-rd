"""LumiPilot-R&D: authenticated read-only research workbench, Python stdlib."""
from __future__ import annotations
import argparse, base64, hashlib, hmac, html, json, mimetypes, os, secrets, shutil, sqlite3, threading, time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT=Path(__file__).resolve().parent
ITERATIONS=600_000
CSP="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'"

def make_auth(username, password):
    if not username or not password: raise ValueError('Username and password are required')
    salt=secrets.token_bytes(24)
    return {'username':username,'algorithm':'pbkdf2-sha256','iterations':ITERATIONS,'salt':salt.hex(),'password_hash':hashlib.pbkdf2_hmac('sha256',password.encode(),salt,ITERATIONS).hex()}

def write_auth(path, username, password):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(make_auth(username,password),f)

class State:
    def __init__(self,auth_file,web_root,session_file,origin,sources_root=None,local=False):
        self.web=Path(web_root).resolve();self.sources=Path(sources_root).resolve() if sources_root else None
        self.origin=origin.rstrip('/');u=urlsplit(self.origin)
        if u.path or u.query or u.fragment or u.username or u.password or not u.hostname:raise ValueError('Origin must be scheme://host[:port]')
        if not local and u.scheme!='https':raise ValueError('Production PUBLIC_ORIGIN must use HTTPS')
        if local and u.hostname not in ['127.0.0.1','localhost','::1']:raise ValueError('Local mode is loopback-only')
        self.secure=u.scheme=='https';self.cookie='__Host-rd_session' if self.secure else 'rd_session';self.auth=json.loads(Path(auth_file).read_text())
        a=self.auth
        if a.get('algorithm')!='pbkdf2-sha256' or not 310_000<=a.get('iterations',0)<=2_000_000:raise ValueError('Invalid auth configuration')
        bytes.fromhex(a['salt']);bytes.fromhex(a['password_hash'])
        self.private_web=Path(auth_file).resolve().parent/'private-web'
        self.dbpath=Path(session_file);self.dbpath.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with self.db() as c:
            c.execute('CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires REAL NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS attempts (ip_hash TEXT NOT NULL, at REAL NOT NULL)')
        os.chmod(self.dbpath,0o600)
    def db(self):return sqlite3.connect(self.dbpath,timeout=10)
    def verify(self,user,password):
        a=self.auth;actual=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(a['salt']),a['iterations']).hex()
        return hmac.compare_digest(actual,a['password_hash']) & hmac.compare_digest(user.encode(),a['username'].encode())
    def session(self,token):
        if not token or len(token)>100:return None
        key=hashlib.sha256(token.encode()).hexdigest()
        with self.db() as c:
            c.execute('DELETE FROM sessions WHERE expires<=?',(time.time(),))
            return c.execute('SELECT csrf,expires FROM sessions WHERE token_hash=?',(key,)).fetchone()
    def new_session(self):
        token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
        with self.db() as c:c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),csrf,time.time()+8*3600))
        return token
    def revoke(self,token):
        with self.db() as c:c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))
    def attempt(self,ip):
        key=hashlib.sha256(ip.encode()).hexdigest();now=time.time()
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('DELETE FROM attempts WHERE at<?',(now-900,))
            count=c.execute('SELECT COUNT(*) FROM attempts WHERE ip_hash=?',(key,)).fetchone()[0]
            if count>=8:return False
            c.execute('INSERT INTO attempts VALUES(?,?)',(key,now))
        return True
    def clear_attempts(self,ip):
        with self.db() as c:c.execute('DELETE FROM attempts WHERE ip_hash=?',(hashlib.sha256(ip.encode()).hexdigest(),))

class Handler(BaseHTTPRequestHandler):
    server_version='LumiPilot-RD';sys_version=''
    def log_message(self,fmt,*args):pass  # Never log form fields, cookies or source paths.
    @property
    def state(self):return self.server.state
    def token(self):
        jar=cookies.SimpleCookie()
        try:jar.load(self.headers.get('Cookie',''))
        except cookies.CookieError:return ''
        return jar[self.state.cookie].value if self.state.cookie in jar else ''
    def headers_out(self,status,ctype='text/html; charset=utf-8',length=0,extra=None):
        self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(length))
        for k,v in {'Cache-Control':'no-store, private','Pragma':'no-cache','X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin','Content-Security-Policy':CSP,'Permissions-Policy':'camera=(), microphone=(), geolocation=()'}.items():self.send_header(k,v)
        if self.state.secure:self.send_header('Strict-Transport-Security','max-age=31536000')
        for k,v in (extra or {}).items():self.send_header(k,v)
        self.end_headers()
    def send(self,status,body,ctype='text/html; charset=utf-8',extra=None):
        b=body.encode() if isinstance(body,str) else body;self.headers_out(status,ctype,len(b),extra)
        if self.command!='HEAD':self.wfile.write(b)
    def redirect(self,url,extra=None):self.send(303,b'',extra={'Location':url,**(extra or {})})
    def session_cookie(self,token,age=28800):return f'{self.state.cookie}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}'+('; Secure' if self.state.secure else '')
    def login_page(self,message='',status=200):
        self.send(status,(ROOT/'templates/login.html').read_text().replace('<!--MESSAGE-->',html.escape(message)))
    def host_ok(self):
        return self.headers.get('Host','').lower()==urlsplit(self.state.origin).netloc.lower()
    def do_HEAD(self):self.do_GET()
    def do_GET(self):
        if not self.host_ok():self.send(400,'请求地址无效');return
        path=unquote(urlsplit(self.path).path)
        if '\x00' in path:self.send(400,'请求路径无效');return
        if path=='/healthz':self.send(200,'{"ok":true,"app":"LumiPilot-R&D"}','application/json');return
        if path=='/login.css':self.send(200,(ROOT/'templates/login.css').read_bytes(),'text/css; charset=utf-8');return
        session=self.state.session(self.token())
        if path=='/login':
            if session:self.redirect('/')
            else:self.login_page()
            return
        if not session:
            if path.startswith('/api/'):self.send(401,'{"error":"authentication_required"}','application/json')
            else:self.redirect('/login')
            return
        if path=='/api/session':self.send(200,json.dumps({'username':self.state.auth['username']}),'application/json');return
        if path.startswith('/资料快照/'):
            root=self.state.sources;relative=path[len('/资料快照/'):]
            if not root:self.send(404,'此原始资料尚未导入，请联系管理员。');return
        else:root=self.state.web;relative=path.lstrip('/') or 'index.html'
        if any(p.startswith('.') for p in Path(relative).parts):self.send(404,'未找到');return
        try:
            candidate=(root/relative).resolve();candidate.relative_to(root);exists=candidate.is_file()
        except (ValueError,OSError):self.send(404,'未找到');return
        if not exists and root==self.state.web:
            root=self.state.private_web.resolve()
            try:
                candidate=(root/relative).resolve();candidate.relative_to(root);exists=candidate.is_file()
            except (ValueError,OSError):self.send(404,'未找到');return
        if not exists:self.send(404,'未找到');return
        ctype=mimetypes.guess_type(candidate.name)[0] or 'application/octet-stream'
        if ctype.startswith('text/') or candidate.suffix=='.js':ctype+='; charset=utf-8'
        if root==self.state.web and relative in ['index.html']:
            markup=candidate.read_text()
            bootstrap=self.state.private_web/'bootstrap.json'
            if bootstrap.is_file():
                payload=json.loads(bootstrap.read_text())
                import re
                for id,value in [('library-data',payload.get('library',{'products':[],'sources':[]})),('case-data',payload.get('cases',{}))]:
                    encoded=json.dumps(value,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
                    markup=re.sub(r'(<script[^>]*id="'+id+r'"[^>]*>).*?(</script>)',lambda m:m[1]+encoded+m[2],markup,flags=re.S)
            csrf=html.escape(session[0],quote=True)
            logout=f'<form method="post" action="/logout" class="rd-logout"><input type="hidden" name="csrf" value="{csrf}"><button type="submit">退出登录</button></form>'
            markup=markup.replace('<time class="date"',logout+'<time class="date"')
            self.send(200,markup,ctype);return
        self.headers_out(200,ctype,candidate.stat().st_size)
        if self.command!='HEAD':
            with candidate.open('rb') as f:shutil.copyfileobj(f,self.wfile,1024*1024)
    def do_POST(self):
        if not self.host_ok() or self.headers.get('Origin','').rstrip('/')!=self.state.origin:self.send(403,'请求来源无效');return
        if self.headers.get('Content-Type','').split(';')[0]!='application/x-www-form-urlencoded':self.send(415,'表单格式无效');return
        try:length=int(self.headers.get('Content-Length','-1'))
        except ValueError:length=-1
        if length<0 or length>4096:self.send(413,'请求过大');return
        try:data=parse_qs(self.rfile.read(length).decode('utf-8'),max_num_fields=10)
        except (ValueError,UnicodeError):self.send(400,'表单无效');return
        path=urlsplit(self.path).path
        if path=='/login':
            if not self.state.attempt(self.client_address[0]):self.login_page('尝试次数过多，请15分钟后重试。',429);return
            user=data.get('username',[''])[0];password=data.get('password',[''])[0]
            if not self.state.verify(user,password):self.login_page('用户名或密码不正确。',401);return
            self.state.clear_attempts(self.client_address[0]);token=self.state.new_session();self.redirect('/',{'Set-Cookie':self.session_cookie(token)});return
        if path=='/logout':
            token=self.token();session=self.state.session(token);csrf=data.get('csrf',[''])[0]
            if not session or not hmac.compare_digest(csrf,session[0]):self.send(403,'会话无效，请重新登录');return
            self.state.revoke(token);self.redirect('/login',{'Set-Cookie':self.session_cookie('',0)});return
        self.send(404,'未找到')

def build_server(state,host='127.0.0.1',port=8988):
    server=ThreadingHTTPServer((host,port),Handler);server.daemon_threads=True;server.state=state;return server

def main():
    p=argparse.ArgumentParser();p.add_argument('--local',action='store_true');p.add_argument('--host');p.add_argument('--port',type=int,default=int(os.environ.get('PORT','8988')));a=p.parse_args()
    host=a.host or ('127.0.0.1' if a.local else '0.0.0.0')
    if a.local and host not in ['127.0.0.1','::1','localhost']:p.error('--local binds loopback only')
    runtime=Path(os.environ.get('RD_RUNTIME_DIR',ROOT/'.runtime'))
    origin=os.environ.get('RD_PUBLIC_ORIGIN',f'http://127.0.0.1:{a.port}' if a.local else '')
    s=State(os.environ.get('RD_AUTH_FILE',runtime/'auth.json'),ROOT/'web',runtime/'sessions.sqlite3',origin,os.environ.get('RD_SOURCES_DIR'),a.local)
    server=build_server(s,host,a.port);print(f'LumiPilot-R&D ready on {host}:{a.port}; authentication required',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=='__main__':main()
