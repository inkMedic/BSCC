"""Dependency-free ticket cache; all methods run on the engine logic thread."""
import hashlib
import time


class TicketCache:
    def __init__(self):
        self.instance_id = None
        self.control_session_id = None
        self.connected = False
        self.entries = {}

    def reset(self, instance_id=None, control_session_id=None):
        self.entries.clear()
        self.instance_id = instance_id
        self.control_session_id = control_session_id
        self.connected = instance_id is not None

    def prepare(self, instance_id, control_session_id, payload):
        now = time.time()
        self.entries = {k: v for k, v in self.entries.items() if v['expires_at'] > now}
        if (not self.connected or instance_id != self.instance_id
                or control_session_id != self.control_session_id
                or not now < payload['expires_at'] <= now + 61
                or len(self.entries) >= 4096):
            return False
        index = payload['ticket_index']
        previous = self.entries.get(index)
        if previous:
            return all(previous.get(k) == v for k, v in payload.items())
        self.entries[index] = dict(payload, connection_id=None)
        return True

    def claim(self, ticket, connection_id):
        if not self.connected or connection_id is None:
            return None
        entry = self.entries.get(hashlib.sha256(ticket.encode()).hexdigest())
        if entry is None or entry['expires_at'] <= time.time():
            return None
        if entry['connection_id'] not in (None, connection_id):
            return None
        entry['connection_id'] = connection_id
        return (entry['uid'], entry['account_tag'], entry['profiles'], entry.get('purchases'), None, entry['nickname'])
