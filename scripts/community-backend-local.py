#!/usr/bin/env python3.13
"""Start/status/stop the isolated Mac backend used by iOS device tests.

Requires community-backend/.venv and local PostgreSQL/Redis binaries.
Data stays under artifacts/community/local-backend; API listens on port 8000.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'community-backend'
STATE = ROOT / 'artifacts/community/local-backend'
PG = STATE / 'postgres'
SOCKETS = STATE / 'sockets'
API_PID = STATE / 'api.pid'
REDIS_PID = STATE / 'redis.pid'
PYTHON = BACKEND / '.venv/bin/python'


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def tool(name):
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f'Missing {name}; install PostgreSQL and Redis first')
    return path


def alive(pidfile):
    if not pidfile.exists():
        return False
    try:
        os.kill(int(pidfile.read_text().splitlines()[0]), 0)
        return True
    except (ProcessLookupError, ValueError):
        return False


def free_port(port):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', port))


def api_is_ours():
    if not alive(API_PID):
        return False
    cmd = subprocess.check_output(['ps', '-p', API_PID.read_text().strip(), '-o', 'command='], text=True)
    cwd = subprocess.check_output(['lsof', '-a', '-p', API_PID.read_text().strip(), '-d', 'cwd', '-Fn'], text=True)
    if ('-m uvicorn community_backend.app:create_app' not in cmd
            or f'n{BACKEND}\n' not in cwd):
        raise RuntimeError('API PID belongs to another process; refusing to signal it')
    return True


def readiness():
    with urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2) as response:
        return json.load(response)


def start():
    STATE.mkdir(parents=True, exist_ok=True)
    SOCKETS.mkdir(exist_ok=True)
    os.chmod(STATE, 0o700)
    envfile = BACKEND / '.env'
    if not envfile.exists():
        password = secrets.token_urlsafe(32)
        content = (f'COMMUNITY_SECRET={secrets.token_urlsafe(48)}\n'
                   f'COMMUNITY_DATABASE_URL=postgresql+psycopg://community:{password}@127.0.0.1:55432/community_dev\n'
                   'COMMUNITY_REDIS_URL=redis://127.0.0.1:56379/0\n')
        fd = os.open(envfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as out:
            out.write(content)
    os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))
    from community_backend.config import Settings
    from sqlalchemy.engine import make_url
    cfg = Settings()
    db = make_url(cfg.database_url)
    if db.host != '127.0.0.1' or db.port != 55432 or db.database != 'community_dev' or db.username != 'community':
        raise RuntimeError('Existing .env uses another database; refusing to change it')
    if cfg.redis_url != 'redis://127.0.0.1:56379/0':
        raise RuntimeError('Existing .env uses another Redis; refusing to change it')
    if not (PG / 'PG_VERSION').exists():
        free_port(55432)
        with tempfile.NamedTemporaryFile(mode='w', dir=STATE) as pw:
            pw.write(db.password + '\n')
            pw.flush()
            run(tool('initdb'), '-D', PG, '-U', 'community', '--encoding=UTF8',
                '--locale=C', '--auth-local=trust', '--auth-host=scram-sha-256', '--pwfile', pw.name,
                stdout=(STATE / 'initdb.log').open('w'), stderr=subprocess.STDOUT)
    pg_status = subprocess.run([tool('pg_ctl'), '-D', str(PG), 'status'], capture_output=True)
    if pg_status.returncode != 0:
        free_port(55432)
        run(tool('pg_ctl'), '-D', PG, '-l', STATE / 'postgres.log', '-w',
            '-o', f'-h 127.0.0.1 -p 55432 -k {SOCKETS}', 'start')
    query = subprocess.check_output([tool('psql'), '-h', str(SOCKETS), '-p', '55432', '-U', 'community',
        '-d', 'postgres', '-tAc', "SELECT 1 FROM pg_database WHERE datname='community_dev'"], text=True)
    if query.strip() != '1':
        run(tool('createdb'), '-h', SOCKETS, '-p', '55432', '-U', 'community', 'community_dev')
    if not alive(REDIS_PID):
        free_port(56379)
        run(tool('redis-server'), '--bind', '127.0.0.1', '--port', '56379',
            '--dir', STATE, '--appendonly', 'yes', '--daemonize', 'yes',
            '--pidfile', REDIS_PID, '--logfile', STATE / 'redis.log')
    run(BACKEND / '.venv/bin/alembic', 'upgrade', 'head', cwd=BACKEND)
    if not api_is_ours():
        free_port(8000)
        with (STATE / 'api.log').open('a') as log:
            proc = subprocess.Popen([str(PYTHON), '-m', 'uvicorn', 'community_backend.app:create_app',
                '--factory', '--host', '0.0.0.0', '--port', '8000', '--workers', '1'], cwd=BACKEND,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        API_PID.write_text(str(proc.pid) + '\n')
    for _ in range(40):
        try:
            print('Backend:', readiness(), 'http://0.0.0.0:8000')
            return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError(f'Backend did not become ready; inspect {STATE / "api.log"}')


def stop():
    if api_is_ours():
        os.kill(int(API_PID.read_text()), signal.SIGTERM)
    if alive(REDIS_PID):
        server_info = subprocess.check_output([tool('redis-cli'), '-p', '56379', 'INFO', 'server'], text=True)
        if f'process_id:{REDIS_PID.read_text().strip()}\n' not in server_info:
            raise RuntimeError('Redis PID mismatch; refusing to stop it')
        run(tool('redis-cli'), '-p', '56379', 'SHUTDOWN', 'SAVE')
    if (PG / 'PG_VERSION').exists():
        status = subprocess.run([tool('pg_ctl'), '-D', str(PG), 'status'], capture_output=True)
        if status.returncode == 0:
            run(tool('pg_ctl'), '-D', PG, '-m', 'fast', '-w', 'stop')
    print('Stopped local backend; data retained.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'status', 'stop'), default='status', nargs='?')
    action = parser.parse_args().action
    if action == 'start':
        start()
    elif action == 'stop':
        stop()
    else:
        print(readiness())
