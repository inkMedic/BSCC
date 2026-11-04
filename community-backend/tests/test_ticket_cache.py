"""Shared Headless cache, without importing engine-native modules."""
import importlib.util
from pathlib import Path
import time
from community_backend.security import digest, token

spec = importlib.util.spec_from_file_location('ticket_cache', Path(__file__).resolve().parents[2] / 'src/assets/ba_data/python/baplus/_community_auth.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_ticket_claim_and_scope():
    cache = module.TicketCache()
    cache.reset('instance', 'control')
    ticket = token()
    payload = dict(ticket_index=digest(ticket), uid='trusted_uid', account_tag='c_safe', nickname='中文', profiles={}, expires_at=time.time() + 30, join_attempt_id='attempt')
    assert not cache.prepare('wrong', 'control', payload)
    assert not cache.prepare('instance', 'old_control', payload)
    assert cache.prepare('instance', 'control', payload)
    assert cache.prepare('instance', 'control', payload)
    assert cache.claim('invalid', 1) is None
    assert cache.claim(ticket, None) is None
    assert cache.claim(ticket, 1)[0] == 'trusted_uid'
    assert cache.claim(ticket, 1)[0] == 'trusted_uid'
    assert cache.claim(ticket, 2) is None
    assert cache.prepare('instance', 'control', payload)  # Duplicate preserves owner.
    assert cache.claim(ticket, 2) is None
    cache.entries[digest(ticket)]['expires_at'] = time.time() - 1
    assert cache.claim(ticket, 1) is None
    cache.reset('new_instance', 'new_control')
    assert cache.claim(ticket, 1) is None
    cache.reset()
    assert not cache.prepare('instance', 'control', payload)
