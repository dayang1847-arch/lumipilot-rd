import http.client,json,re,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode,quote
from server import State,Handler,build_server,write_auth

class AuthBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name);web=cls.root/'web';web.mkdir();src=cls.root/'sources';src.mkdir()
        (web/'index.html').write_text('<html><time class="date">date</time><p>PRIVATE-RESEARCH</p><script type="application/json" id="library-data">{}</script><script type="application/json" id="case-data">{}</script></html>')
        (web/'knowledge.json').write_text('{"private":"BOM-SECRET"}')
        (web/'app.js').write_text('const confidential = "INTERNAL";')
        (web/'nested').mkdir();(web/'.env').write_text('not-public')
        (cls.root/'outside.txt').write_text('OUTSIDE-SECRET');(web/'escape.txt').symlink_to(cls.root/'outside.txt')
        (src/'evidence.txt').write_text('PRIVATE-SOURCE')
        private=cls.root/'private-web';private.mkdir();(private/'bootstrap.json').write_text(json.dumps({'library':{'private':'PRIVATE-BOOTSTRAP'},'cases':{'case':'PRIVATE-CASE'}}));(private/'analysis.json').write_text('{"private":"PRIVATE-ANALYSIS"}')
        write_auth(cls.root/'auth.json','admin','test-only-passphrase')
        cls.state=State(cls.root/'auth.json',web,cls.root/'sessions.sqlite3','http://127.0.0.1:1',src,local=True)
        cls.http=build_server(cls.state,port=0);cls.port=cls.http.server_address[1];cls.state.origin=f'http://127.0.0.1:{cls.port}'
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();cls.tmp.cleanup()
    def setUp(self):
        with self.state.db() as c:c.execute('DELETE FROM attempts');c.execute('DELETE FROM sessions')
    def req(self,path='/',method='GET',data=None,cookie=None,origin=True,headers=None):
        h=dict(headers or {})
        if origin:h['Origin']=self.state.origin if origin is True else origin
        if cookie:h['Cookie']=cookie
        body=urlencode(data).encode() if data is not None else None
        if body is not None:h.setdefault('Content-Type','application/x-www-form-urlencoded')
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=10);conn.request(method,quote(path,safe='/%?='),body,h)
        r=conn.getresponse();out=(r.status,dict(r.getheaders()),r.read());conn.close();return out
    def login(self):
        status,h,_=self.req('/login','POST',{'username':'admin','password':'test-only-passphrase'})
        self.assertEqual(status,303);return h['Set-Cookie'].split(';')[0]
    def test_all_data_and_direct_source_paths_require_login(self):
        for path in ['/','/index.html','/knowledge.json','/app.js','/资料快照/evidence.txt','/missing.pdf']:
            with self.subTest(path=path):
                status,h,body=self.req(path);self.assertEqual(status,303);self.assertEqual(h['Location'],'/login');self.assertNotIn(b'SECRET',body)
    def test_session_api_unauthenticated(self):self.assertEqual(self.req('/api/session')[0],401)
    def test_login_page_is_public_without_research_data(self):
        status,h,body=self.req('/login');self.assertEqual(status,200);self.assertNotIn(b'PRIVATE',body);self.assertNotIn(b'test-only-passphrase',body)
    def test_wrong_password_does_not_issue_session(self):
        status,h,_=self.req('/login','POST',{'username':'admin','password':'wrong'});self.assertEqual(status,401);self.assertNotIn('Set-Cookie',h)
    def test_wrong_username_does_not_issue_session(self):
        for name in ['other','管理员']:
            self.assertEqual(self.req('/login','POST',{'username':name,'password':'test-only-passphrase'})[0],401)
    def test_login_allows_authenticated_data_and_sources(self):
        cookie=self.login()
        self.assertIn(b'BOM-SECRET',self.req('/knowledge.json',cookie=cookie)[2])
        self.assertIn(b'PRIVATE-SOURCE',self.req('/资料快照/evidence.txt',cookie=cookie)[2])
        self.assertEqual(json.loads(self.req('/api/session',cookie=cookie)[2])['username'],'admin')
    def test_cookie_and_response_headers(self):
        _,h,_=self.req('/login','POST',{'username':'admin','password':'test-only-passphrase'})
        for flag in ['HttpOnly','SameSite=Strict','Path=/']:self.assertIn(flag,h['Set-Cookie'])
        self.assertIn('no-store',h['Cache-Control']);self.assertEqual(h['X-Content-Type-Options'],'nosniff');self.assertIn("script-src 'self'",h['Content-Security-Policy'])
        secure=SimpleNamespace(state=SimpleNamespace(cookie='__Host-rd_session',secure=True))
        self.assertIn('; Secure',Handler.session_cookie(secure,'token'))
    def test_cross_origin_login_rejected(self):
        for origin in [False,'https://unrelated.invalid']:
            self.assertEqual(self.req('/login','POST',{'username':'admin','password':'test-only-passphrase'},origin=origin)[0],403)
    def test_logout_requires_csrf_and_revokes_session(self):
        cookie=self.login();_,_,body=self.req('/',cookie=cookie);csrf=re.search(rb'name="csrf" value="([^"]+)"',body)[1].decode()
        self.assertEqual(self.req('/logout','POST',{'csrf':'wrong'},cookie=cookie)[0],403)
        self.assertEqual(self.req('/logout','POST',{'csrf':csrf},cookie=cookie)[0],303)
        self.assertEqual(self.req('/api/session',cookie=cookie)[0],401)
    def test_expired_and_tampered_sessions_rejected(self):
        cookie=self.login();self.assertEqual(self.req('/api/session',cookie=cookie+'tampered')[0],401)
        with self.state.db() as c:c.execute('UPDATE sessions SET expires=?',(time.time()-1,))
        self.assertEqual(self.req('/api/session',cookie=cookie)[0],401)
    def test_traversal_dotfiles_symlinks_and_directory_listing_rejected(self):
        cookie=self.login()
        for path in ['/../outside.txt','/%2e%2e/outside.txt','/.env','/escape.txt','/nested/']:
            with self.subTest(path=path):self.assertEqual(self.req(path,cookie=cookie)[0],404)
    def test_untrusted_host_rejected(self):self.assertEqual(self.req('/healthz',headers={'Host':'unexpected.invalid'})[0],400)
    def test_login_rate_limit(self):
        for _ in range(8):self.assertEqual(self.req('/login','POST',{'username':'admin','password':'wrong'})[0],401)
        self.assertEqual(self.req('/login','POST',{'username':'admin','password':'test-only-passphrase'})[0],429)
    def test_no_missing_auth_fallback_or_insecure_production_origin(self):
        with self.assertRaises(FileNotFoundError):State(self.root/'missing.json',self.root/'web',self.root/'x.sqlite3','https://example.invalid')
        with self.assertRaises(ValueError):State(self.root/'auth.json',self.root/'web',self.root/'x.sqlite3','http://example.invalid')
    def test_large_login_body_rejected(self):
        self.assertEqual(self.req('/login','POST',{'password':'x'*5000})[0],413)
    def test_private_case_payload_is_injected_only_after_login(self):
        self.assertNotIn(b'PRIVATE-BOOTSTRAP',(self.root/'web/index.html').read_bytes())
        self.assertNotIn(b'PRIVATE-BOOTSTRAP',self.req('/')[2])
        body=self.req('/',cookie=self.login())[2]
        self.assertIn(b'PRIVATE-BOOTSTRAP',body);self.assertIn(b'PRIVATE-CASE',body)
    def test_private_analysis_fallback_still_requires_login(self):
        self.assertEqual(self.req('/analysis.json')[0],303)
        self.assertIn(b'PRIVATE-ANALYSIS',self.req('/analysis.json',cookie=self.login())[2])
    def test_private_bootstrap_direct_url_requires_login(self):
        self.assertEqual(self.req('/bootstrap.json')[0],303)
    def test_auth_file_contains_verifier_only(self):
        text=(self.root/'auth.json').read_text();self.assertNotIn('test-only-passphrase',text);self.assertEqual((self.root/'auth.json').stat().st_mode & 0o777,0o600)

if __name__=='__main__':unittest.main()
