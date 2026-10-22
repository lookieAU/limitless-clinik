import hashlib
import secrets


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def idempotency_key(user_id: str, action: str, target: str, intent_id: str) -> str:
    material = "|".join((user_id, action, target, intent_id))
    return hashlib.sha256(material.encode()).hexdigest()
