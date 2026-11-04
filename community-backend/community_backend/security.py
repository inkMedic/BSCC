import hashlib
import secrets
from argon2 import PasswordHasher, Type

passwords = PasswordHasher(type=Type.ID)


def token():
    return secrets.token_urlsafe(32)


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()
