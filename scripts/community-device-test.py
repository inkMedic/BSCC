"""Small ADB evidence helper; test credentials never go to command output."""
import argparse
import json
from pathlib import Path
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[1]
record = ROOT / 'artifacts/community/lan'
record.mkdir(parents=True, exist_ok=True)
parser = argparse.ArgumentParser()
parser.add_argument('--enter', choices=['login', 'password', 'nickname'])
parser.add_argument('--screenshot')
args = parser.parse_args()
credentials_file = record / '.device-account.json'
if not credentials_file.exists():
    credentials_file.write_text(json.dumps(dict(login='lan_' + secrets.token_hex(4), password=secrets.token_hex(12), nickname='LANPlayer')))
if args.enter:
    credentials = json.loads(credentials_file.read_text())
    subprocess.run(['adb', 'shell', 'input', 'text', credentials[args.enter]], check=True, capture_output=True)
    print('Entered test ' + args.enter)
if args.screenshot:
    output = record / (Path(args.screenshot).name + '.png')
    result = subprocess.run(['adb', 'exec-out', 'screencap', '-p'], check=True, capture_output=True)
    output.write_bytes(result.stdout)
    print(output)
