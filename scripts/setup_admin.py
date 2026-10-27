"""Create auth configuration outside Git. Never accepts a password argument."""
import argparse,getpass,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import write_auth
p=argparse.ArgumentParser();p.add_argument('--username',default='admin');p.add_argument('--file',type=Path,default=Path('.runtime/auth.json'));a=p.parse_args()
password=getpass.getpass('Password (not stored in plaintext): ')
write_auth(a.file,a.username,password)
print('Administrator verifier created. Keep this file outside the repository.')
