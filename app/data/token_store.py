"""Encrypted OAuth token persistence (Fernet). One row per service in oauth_token."""
import json
from datetime import datetime, timezone
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import OAuthToken

# derive a stable Fernet key from the configured secret (or a dev default)
_SECRET = settings.token_encryption_key or "rtg-dev-token-key-change-me-please-01234567"
_KEY = Fernet(__import__("base64").urlsafe_b64encode(
    __import__("hashlib").sha256(_SECRET.encode()).digest()))


def _enc(s: str | None) -> bytes | None:
    return _KEY.encrypt(s.encode()) if s else None


def _dec(b: bytes | None) -> str | None:
    return _KEY.decrypt(b).decode() if b else None


async def save_tokens(db: AsyncSession, service: str, client_id: str, access: str,
                      refresh: str, expires_at: float, scope: str = ""):
    row = (await db.execute(select(OAuthToken).where(OAuthToken.service == service))).scalar_one_or_none()
    if row is None:
        row = OAuthToken(service=service)
        db.add(row)
    row.access_token_enc = _enc(access)
    row.refresh_token_enc = _enc(refresh)
    row.expires_at = datetime.fromtimestamp(expires_at, tz=timezone.utc)
    row.scope = json.dumps({"client_id": client_id, "scope": scope})
    await db.commit()


async def load_tokens(db: AsyncSession, service: str = "ifs") -> dict | None:
    row = (await db.execute(select(OAuthToken).where(OAuthToken.service == service))).scalar_one_or_none()
    if not row or not row.access_token_enc:
        return None
    meta = json.loads(row.scope) if row.scope else {}
    return dict(client_id=meta.get("client_id"),
                access_token=_dec(row.access_token_enc),
                refresh_token=_dec(row.refresh_token_enc),
                expires_at=row.expires_at.timestamp() if row.expires_at else 0)
