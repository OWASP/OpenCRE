"""Google sign-in for the remote MCP server (OAuth 2.1 for MCP clients).

The MCP SDK serves the OAuth endpoints (metadata, dynamic client registration, /authorize, /token,
/revoke); this module is the provider behind them. MCP clients talk OAuth to this server, and this
server signs the user in with Google, so a tester sees the same Google sign-in as the chatbot.

Access tokens are ordinary short-lived API keys (``api_keys`` rows), so every existing check keeps
working unchanged: role gating (``application.utils.roles``), per-account rate limits, and
revocation. Only these live in process memory, for a few minutes mid sign-in: the pending Google
redirect and the authorization code. Run a single MCP worker (the remote app already does).

Config:
  OPENCRE_MCP_OAUTH=1                        turn this on (otherwise remote MCP keeps Bearer API keys only)
  OPENCRE_MCP_PUBLIC_URL                     public origin, default https://staging.opencre.org
  OPENCRE_MCP_ALLOWED_DOMAINS                comma list of email domains that may sign in ("*" = any);
                                             defaults to LOGIN_ALLOWED_DOMAINS. Roles still decide access.
  OPENCRE_MCP_GOOGLE_CLIENT_ID / _SECRET     default to GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET
  OPENCRE_MCP_ACCESS_TOKEN_MINUTES (60), OPENCRE_MCP_REFRESH_DAYS (30)
The Google client needs ``<public url>/oauth/google/callback`` as an authorized redirect URI.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import anyio
import requests
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.server.auth.settings import (
    AuthSettings,
    ClientRegistrationOptions,
    RevocationOptions,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response
from starlette.routing import Route

from cre_logging import get_logger

logger = get_logger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
CALLBACK_PATH = "/oauth/google/callback"
KEY_NAME_PREFIX = (
    "mcp-oauth:"  # api_keys.name of tokens issued here, followed by the client id
)
DEFAULT_PUBLIC_URL = "https://staging.opencre.org"
PENDING_TTL_SECONDS = 600
CODE_TTL_SECONDS = 300
REQUEST_TIMEOUT_SECONDS = 15


def oauth_enabled() -> bool:
    return (os.environ.get("OPENCRE_MCP_OAUTH") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def public_url() -> str:
    return (os.environ.get("OPENCRE_MCP_PUBLIC_URL") or DEFAULT_PUBLIC_URL).rstrip("/")


def allowed_domains() -> List[str]:
    """Domains that may sign in. Empty means nobody (fail closed)."""
    raw = os.environ.get("OPENCRE_MCP_ALLOWED_DOMAINS")
    if raw is None or not raw.strip():
        raw = os.environ.get("LOGIN_ALLOWED_DOMAINS") or ""
    return [d.strip().lower().lstrip("@") for d in raw.split(",") if d.strip()]


def account_may_sign_in(email: str) -> bool:
    """Same rule as the web callback: a named admin may come from any domain,
    everyone else needs an allowed domain and a role."""
    from application.utils import roles

    role = roles.role_for(email)
    if role is None:
        return False
    return role == roles.ADMIN or domain_allowed(email)


def domain_allowed(email: str) -> bool:
    domains = allowed_domains()
    if not domains:
        return False
    if domains == ["*"]:
        return True
    host = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
    return any(host == d or host.endswith("." + d) for d in domains)


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, "") or default))
    except ValueError:
        return default


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _google_credentials() -> Tuple[str, str]:
    client_id = os.environ.get("OPENCRE_MCP_GOOGLE_CLIENT_ID") or os.environ.get(
        "GOOGLE_CLIENT_ID"
    )
    secret = os.environ.get("OPENCRE_MCP_GOOGLE_CLIENT_SECRET") or os.environ.get(
        "GOOGLE_CLIENT_SECRET"
    )
    if not client_id or not secret:
        raise RuntimeError(
            "MCP OAuth needs GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET "
            "(or OPENCRE_MCP_GOOGLE_CLIENT_ID / _SECRET)"
        )
    return client_id, secret


class OpenCREOAuthProvider:
    """``OAuthAuthorizationServerProvider`` that signs users in with Google."""

    def __init__(self) -> None:
        # state -> (client_id, authorization params, expires_at)
        self._pending: Dict[str, Tuple[str, AuthorizationParams, float]] = {}
        self._codes: Dict[str, AuthorizationCode] = {}

    # --- clients (dynamic registration) -------------------------------------------------

    async def get_client(self, client_id: str) -> Optional[OAuthClientInformationFull]:
        from application import sqla
        from application.database import db

        row = sqla.session.get(db.McpOAuthClient, client_id)
        if row is None:
            return None
        return OAuthClientInformationFull.model_validate_json(row.info_json)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        from application import sqla
        from application.database import db

        if not client_info.client_id:
            raise ValueError("client_id is required")
        sqla.session.merge(
            db.McpOAuthClient(
                client_id=client_info.client_id,
                info_json=client_info.model_dump_json(),
                created_at=_utcnow(),
            )
        )
        sqla.session.commit()

    # --- authorization: redirect to Google, come back on the callback -----------------

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        if not allowed_domains():
            raise AuthorizeError(
                "server_error", "Sign-in is not configured: no allowed domains"
            )
        self._sweep()
        state = secrets.token_urlsafe(32)
        self._pending[state] = (
            str(client.client_id),
            params,
            time.time() + PENDING_TTL_SECONDS,
        )
        google_client_id, _ = _google_credentials()
        query = {
            "client_id": google_client_id,
            "redirect_uri": public_url() + CALLBACK_PATH,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
        domains = allowed_domains()
        if len(domains) == 1 and domains != ["*"]:
            query["hd"] = domains[
                0
            ]  # a hint only; the email is checked again on return
        return GOOGLE_AUTH_URL + "?" + urlencode(query)

    async def callback(self, request: Request) -> Response:
        """Google redirects the browser here after sign-in."""
        pending = self._pending.pop(request.query_params.get("state", ""), None)
        if pending is None or pending[2] < time.time():
            return PlainTextResponse(
                "This sign-in link expired. Go back to your MCP client and try again.",
                status_code=400,
            )
        client_id, params, _ = pending
        redirect = str(params.redirect_uri)

        def refuse(description: str) -> Response:
            return RedirectResponse(
                construct_redirect_uri(
                    redirect,
                    error="access_denied",
                    error_description=description,
                    state=params.state,
                ),
                status_code=302,
            )

        google_code = request.query_params.get("code")
        if request.query_params.get("error") or not google_code:
            return refuse("Google sign-in was cancelled")
        try:
            claims = await anyio.to_thread.run_sync(self._google_claims, google_code)
        except Exception as exc:  # the message can carry tokens; log the class only
            logger.error("MCP Google sign-in failed: %s", type(exc).__name__)
            return refuse("Google sign-in failed")

        email = str(claims.get("email") or "").strip().lower()
        if not claims.get("email_verified") or not email:
            return refuse("Your Google account has no verified email")
        from application.utils import roles

        if not account_may_sign_in(email):
            logger.info("MCP sign-in refused for a non-allowed account")
            return refuse("This account is not allowed to use OpenCRE")

        user = await anyio.to_thread.run_sync(self._upsert_user, claims)
        code = AuthorizationCode(
            code=secrets.token_urlsafe(32),
            scopes=params.scopes or [],
            expires_at=time.time() + CODE_TTL_SECONDS,
            client_id=client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
            subject=user.id,
        )
        self._codes[code.code] = code
        return RedirectResponse(
            construct_redirect_uri(redirect, code=code.code, state=params.state),
            status_code=302,
        )

    @staticmethod
    def _google_claims(google_code: str) -> Dict[str, Any]:
        client_id, secret = _google_credentials()
        resp = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": google_code,
                "client_id": client_id,
                "client_secret": secret,
                "redirect_uri": public_url() + CALLBACK_PATH,
                "grant_type": "authorization_code",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        raw_id_token = resp.json()["id_token"]
        return google_id_token.verify_oauth2_token(
            raw_id_token, google_requests.Request(), client_id
        )

    @staticmethod
    def _upsert_user(claims: Dict[str, Any]) -> Any:
        from application.database import db

        return db.Node_collection().upsert_user(
            google_sub=claims["sub"],
            email=str(claims.get("email") or ""),
            display_name=claims.get("name"),
        )

    def _sweep(self) -> None:
        now = time.time()
        self._pending = {k: v for k, v in self._pending.items() if v[2] > now}
        self._codes = {k: v for k, v in self._codes.items() if v.expires_at > now}

    # --- codes and tokens -------------------------------------------------------------------

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> Optional[AuthorizationCode]:
        code = self._codes.get(authorization_code)
        if code is None or code.client_id != client.client_id:
            return None
        if code.expires_at < time.time():
            self._codes.pop(authorization_code, None)
            return None
        return code

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        self._codes.pop(authorization_code.code, None)  # single use
        return await anyio.to_thread.run_sync(
            self._issue,
            str(client.client_id),
            authorization_code.subject or "",
            authorization_code.scopes,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> Optional[RefreshToken]:
        from application import sqla
        from application.database import db

        row = sqla.session.get(db.McpOAuthRefreshToken, _hash(refresh_token))
        if (
            row is None
            or row.client_id != client.client_id
            or row.revoked_at is not None
            or row.expires_at < _utcnow()
        ):
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=row.client_id,
            scopes=[],
            expires_at=int(row.expires_at.replace(tzinfo=timezone.utc).timestamp()),
            subject=row.user_id,
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: List[str],
    ) -> OAuthToken:
        await self.revoke_token(refresh_token)  # rotate: the old one stops working
        return await anyio.to_thread.run_sync(
            self._issue, str(client.client_id), refresh_token.subject or "", scopes
        )

    def _issue(self, client_id: str, user_id: str, scopes: List[str]) -> OAuthToken:
        from application import sqla
        from application.database import db
        from application.utils import roles
        from application.utils.api_tokens.mint import mint_api_token

        user = sqla.session.get(db.User, user_id)
        # Roles are re-read on every sign-in and refresh, so removing someone takes effect.
        if user is None or roles.role_for(user.email) is None:
            raise TokenError("invalid_grant", "This account is no longer allowed")
        minutes = _int_env("OPENCRE_MCP_ACCESS_TOKEN_MINUTES", 60)
        minted = mint_api_token(
            user=user,
            name=f"{KEY_NAME_PREFIX}{client_id}",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=minutes),
        )
        refresh = secrets.token_urlsafe(48)
        sqla.session.add(
            db.McpOAuthRefreshToken(
                token_hash=_hash(refresh),
                client_id=client_id,
                user_id=user.id,
                expires_at=_utcnow()
                + timedelta(days=_int_env("OPENCRE_MCP_REFRESH_DAYS", 30)),
                revoked_at=None,
                created_at=_utcnow(),
            )
        )
        sqla.session.commit()
        return OAuthToken(
            access_token=minted.token,
            expires_in=minutes * 60,
            refresh_token=refresh,
            scope=" ".join(scopes) or None,
        )

    async def load_access_token(self, token: str) -> Optional[AccessToken]:
        """Accepts OAuth access tokens and personal API keys alike (both are API-key JWTs)."""
        from application import sqla
        from application.database import db
        from application.utils import roles
        from application.utils.api_tokens.verify import verify_api_token

        identity = verify_api_token(token)
        if identity is None or not roles.has_role(identity.email, roles.USER):
            return None
        # Tokens issued here carry their client id so /revoke from that client can find them;
        # personal API keys belong to no OAuth client.
        key = sqla.session.get(db.ApiKey, identity.jti)
        name = key.name if key is not None else ""
        client_id = (
            name[len(KEY_NAME_PREFIX) :]
            if name.startswith(KEY_NAME_PREFIX)
            else "opencre"
        )
        return AccessToken(
            token=token, client_id=client_id, scopes=[], subject=identity.user_id
        )

    async def revoke_token(self, token: Any) -> None:
        from application import sqla
        from application.database import db

        now = _utcnow()
        if isinstance(token, RefreshToken):
            row = sqla.session.get(db.McpOAuthRefreshToken, _hash(token.token))
            if row is not None and row.revoked_at is None:
                row.revoked_at = now
                sqla.session.commit()
            return
        from application.utils.api_tokens.verify import verify_api_token

        identity = verify_api_token(getattr(token, "token", ""))
        if identity is not None:
            key = sqla.session.get(db.ApiKey, identity.jti)
            if key is not None and key.revoked_at is None:
                key.revoked_at = now
                sqla.session.commit()


def oauth_app_kwargs(provider: Optional[OpenCREOAuthProvider] = None) -> Dict[str, Any]:
    """Keyword arguments for ``Server.streamable_http_app`` that switch on Google sign-in."""
    from mcp.server.auth.provider import ProviderTokenVerifier

    _google_credentials()  # fail at startup, not at the first sign-in
    if not allowed_domains():
        raise RuntimeError(
            "MCP OAuth needs OPENCRE_MCP_ALLOWED_DOMAINS (or LOGIN_ALLOWED_DOMAINS)"
        )
    provider = provider or OpenCREOAuthProvider()
    base = public_url()
    return {
        "auth": AuthSettings(
            issuer_url=base,  # type: ignore[arg-type]
            resource_server_url=base + "/mcp",  # type: ignore[arg-type]
            client_registration_options=ClientRegistrationOptions(enabled=True),
            revocation_options=RevocationOptions(enabled=True),
        ),
        "auth_server_provider": provider,
        "token_verifier": ProviderTokenVerifier(provider),  # type: ignore[arg-type]
        "custom_starlette_routes": [
            Route(CALLBACK_PATH, endpoint=provider.callback, methods=["GET"])
        ],
    }
