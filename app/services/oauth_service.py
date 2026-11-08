"""OAuth 2.0 for the Claude connector: Dynamic Client Registration, an
authorization-code flow with mandatory PKCE (S256), and long-lived access
tokens that the MCP server forwards to this API as a Bearer token.

Codes live 5 minutes and are single use. Access tokens live 90 days and are
stored only as a sha256 hash. Revoking a token (Profile > Connected apps)
makes the next request with it fail with 401.
"""

import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.tables import oauth_clients, oauth_codes, oauth_tokens, users

CODE_TTL = timedelta(minutes=5)
TOKEN_TTL = timedelta(days=90)


class OAuthError(ValueError):
    """Invalid OAuth request; the message is safe to show to the caller."""


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _allowed_hosts() -> list[str]:
    return [h.strip().lower() for h in settings.OAUTH_ALLOWED_REDIRECT_HOSTS.split(",") if h.strip()]


def redirect_uri_allowed(uri: str) -> bool:
    """Only send the user (and their auth code) back to Claude or localhost.

    Dynamic registration is open, so without this anyone could register a
    client whose redirect_uri is their own site and phish an approval."""
    parsed = urlparse(uri)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("https", "http") or not host:
        return False
    if parsed.scheme == "http" and host not in ("localhost", "127.0.0.1"):
        return False
    return any(host == h or host.endswith("." + h) for h in _allowed_hosts())


def _verify_pkce(verifier: str, challenge: str) -> bool:
    digest = hashlib.sha256(verifier.encode("ascii", "ignore")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return secrets.compare_digest(computed, challenge)


class OAuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── clients ─────────────────────────────────────────────────────────
    async def register_client(self, client_name: str, redirect_uris: list[str], client_uri: str | None) -> dict:
        if not redirect_uris or not all(redirect_uri_allowed(u) for u in redirect_uris):
            raise OAuthError("redirect_uris must point to Claude (claude.ai / claude.com)")
        client_id = client_uri or client_name.lower().replace(" ", "-")
        stmt = pg_insert(oauth_clients).values(
            id=uuid.uuid4(), client_id=client_id[:255], client_name=client_name[:255], redirect_uris=redirect_uris
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[oauth_clients.c.client_id],
            set_={"client_name": client_name[:255], "redirect_uris": redirect_uris},
        )
        await self.db.execute(stmt)
        await self.db.commit()
        return {"client_id": client_id[:255], "client_name": client_name[:255], "redirect_uris": redirect_uris}

    async def _client(self, client_id: str):
        row = (await self.db.execute(select(oauth_clients).where(oauth_clients.c.client_id == client_id))).mappings().first()
        if row is None:
            raise OAuthError("Unknown client_id")
        return row

    async def authorize_info(self, client_id: str, redirect_uri: str, code_challenge: str | None, method: str | None):
        """Validate an authorization request. Raises OAuthError (shown as a
        400, never redirected) if the client or redirect URI is not trusted."""
        client = await self._client(client_id)
        if redirect_uri not in client["redirect_uris"] or not redirect_uri_allowed(redirect_uri):
            raise OAuthError("redirect_uri is not registered for this client")
        if not code_challenge:
            raise OAuthError("PKCE is required (code_challenge)")
        if method and method != "S256":
            raise OAuthError("Only code_challenge_method=S256 is supported")
        return {"client_name": client["client_name"], "redirect_host": urlparse(redirect_uri).hostname or ""}

    # ── authorize ───────────────────────────────────────────────────────
    async def approve(self, user_id: str, client_id: str, redirect_uri: str, state: str, code_challenge: str) -> str:
        """The signed-in user approved: issue a code, return where to send the browser."""
        client = await self._client(client_id)
        raw = secrets.token_urlsafe(32)
        await self.db.execute(
            oauth_codes.insert().values(
                id=uuid.uuid4(),
                code=raw,
                client_id=client["id"],
                user_id=uuid.UUID(user_id),
                redirect_uri=redirect_uri,
                code_challenge=code_challenge,
                expires_at=datetime.now(timezone.utc) + CODE_TTL,
            )
        )
        await self.db.commit()
        return f"{redirect_uri}?{urlencode({'code': raw, 'state': state})}"

    @staticmethod
    def deny_url(redirect_uri: str, state: str) -> str:
        return f"{redirect_uri}?{urlencode({'error': 'access_denied', 'state': state})}"

    # ── token ───────────────────────────────────────────────────────────
    async def exchange_code(
        self, client_id: str, raw_code: str, redirect_uri: str, code_verifier: str | None
    ) -> tuple[str, int]:
        client = await self._client(client_id)
        # Mark the code used atomically first: two concurrent exchanges of the
        # same code cannot both succeed.
        row = (
            await self.db.execute(
                update(oauth_codes)
                .where(oauth_codes.c.code == raw_code, oauth_codes.c.used.is_(False))
                .values(used=True)
                .returning(oauth_codes)
            )
        ).mappings().first()
        await self.db.commit()
        if row is None:
            raise OAuthError("Invalid or already used authorization code")
        if row["client_id"] != client["id"]:
            raise OAuthError("Authorization code was not issued to this client")
        if row["redirect_uri"] != redirect_uri:
            raise OAuthError("redirect_uri does not match the authorization request")
        if datetime.now(timezone.utc) > row["expires_at"]:
            raise OAuthError("Authorization code has expired")
        if row["code_challenge"]:
            if not code_verifier or not _verify_pkce(code_verifier, row["code_challenge"]):
                raise OAuthError("code_verifier does not match the code_challenge")

        raw_token = secrets.token_urlsafe(32)
        await self.db.execute(
            oauth_tokens.insert().values(
                id=uuid.uuid4(),
                token_hash=hash_token(raw_token),
                client_id=client["id"],
                user_id=row["user_id"],
                expires_at=datetime.now(timezone.utc) + TOKEN_TTL,
            )
        )
        await self.db.commit()
        return raw_token, int(TOKEN_TTL.total_seconds())

    # ── using a token ───────────────────────────────────────────────────
    async def user_for_token(self, raw: str) -> dict | None:
        """The owning user's {id, username, email} for a live token, else None.
        Bumps last_used_at so Connected apps shows real activity."""
        row = (
            await self.db.execute(
                select(oauth_tokens, users.c.username, users.c.email, users.c.is_disabled)
                .join(users, users.c.id == oauth_tokens.c.user_id)
                .where(oauth_tokens.c.token_hash == hash_token(raw))
            )
        ).mappings().first()
        if row is None or row["revoked"] or row["is_disabled"]:
            return None
        if datetime.now(timezone.utc) > row["expires_at"]:
            return None
        await self.db.execute(
            update(oauth_tokens).where(oauth_tokens.c.id == row["id"]).values(last_used_at=datetime.now(timezone.utc))
        )
        await self.db.commit()
        return {"id": str(row["user_id"]), "username": row["username"], "email": row["email"]}

    # ── Connected apps ──────────────────────────────────────────────────
    async def list_connections(self, user_id: str) -> list[dict]:
        rows = (
            await self.db.execute(
                select(oauth_tokens, oauth_clients.c.client_name)
                .join(oauth_clients, oauth_clients.c.id == oauth_tokens.c.client_id)
                .where(
                    oauth_tokens.c.user_id == uuid.UUID(user_id),
                    oauth_tokens.c.revoked.is_(False),
                    oauth_tokens.c.expires_at > datetime.now(timezone.utc),
                )
                .order_by(oauth_tokens.c.created_at.desc())
            )
        ).mappings().all()
        return [
            {
                "id": str(r["id"]),
                "client_name": r["client_name"],
                "created_at": r["created_at"].isoformat(),
                "last_used_at": r["last_used_at"].isoformat(),
                "expires_at": r["expires_at"].isoformat(),
            }
            for r in rows
        ]

    async def revoke(self, user_id: str, token_id: str) -> bool:
        try:
            tid = uuid.UUID(token_id)
        except ValueError:
            return False
        result = await self.db.execute(
            update(oauth_tokens)
            .where(oauth_tokens.c.id == tid, oauth_tokens.c.user_id == uuid.UUID(user_id), oauth_tokens.c.revoked.is_(False))
            .values(revoked=True)
        )
        await self.db.commit()
        return result.rowcount > 0
