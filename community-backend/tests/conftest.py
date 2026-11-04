"""Real TCP service, PostgreSQL and Redis. Never uses production databases."""
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='session')
def service():
    env = dict(os.environ,
        COMMUNITY_DATABASE_URL=os.environ.get('COMMUNITY_TEST_DATABASE_URL', 'postgresql+psycopg://community:community@127.0.0.1:5432/community_test'),
        COMMUNITY_REDIS_URL=os.environ.get('COMMUNITY_TEST_REDIS_URL', 'redis://127.0.0.1:6379/15'),
        COMMUNITY_SECRET=secrets.token_urlsafe(32), COMMUNITY_PREPARE_SECONDS='0.4', COMMUNITY_LEASE_SECONDS='3', COMMUNITY_TEST_PURCHASES_ENABLED='1')
    if not env['COMMUNITY_DATABASE_URL'].endswith('/community_test') or not env['COMMUNITY_REDIS_URL'].endswith('/15'):
        pytest.fail('Tests require community_test and Redis database 15')
    from redis import Redis
    with Redis.from_url(env['COMMUNITY_REDIS_URL']) as cache:
        keys = list(cache.scan_iter('rate:*'))
        if keys:
            cache.delete(*keys)
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT, env=env, check=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'community_backend.app:create_app', '--factory', '--port', str(port), '--workers', '1', '--log-level', 'warning'], cwd=ROOT, env=env)
    url = f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            if process.poll() is not None:
                pytest.fail('Backend exited during startup')
            try:
                if httpx.get(url + '/health/ready').status_code == 200:
                    break
            except httpx.ConnectError:
                pass
            time.sleep(.1)
        else:
            pytest.fail('Backend dependencies not ready')
        yield url, env
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.fixture
def client(service):
    with httpx.Client(base_url=service[0], timeout=8) as client:
        yield client
