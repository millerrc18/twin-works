"""IFS MCP OAuth client — browser-login (auth-code + PKCE) against the Azure endpoint,
token storage (encrypted), refresh, and JSON-RPC tools/call.

Endpoint discovery (verified): dynamic registration at /register, PKCE S256 required,
public client (token_endpoint_auth_methods=none), grants authorization_code + refresh_token,
scope offline_access + api://.../access_as_user. Mirrors the SharePoint plugin's
authenticate/complete_authentication localhost-callback dance.

Flow:
  1. register_client()  -> dynamic client_id (cached in DB oauth_token.scope-adjacent meta)
  2. build_authorize_url() -> user opens in browser, logs in, Azure redirects to
     http://localhost:<port>/callback?code=...&state=...
  3. exchange_code(code) -> access+refresh tokens (PKCE verifier)
  4. query(sql) -> JSON-RPC tools/call execute_query; auto-refresh on 401
Only usable running locally (localhost callback). SnapshotDataSource is the fallback.
"""
import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from app.config import settings

WELL_KNOWN = settings.ifs_mcp_url.rsplit("/mcp", 1)[0] + "/.well-known/oauth-authorization-server"
SCOPE = "openid profile email offline_access api://24625c69-bbec-4e25-a39f-ca79a3068822/access_as_user"
# the callback is a FastAPI route on the APP's own port (not a separate server)
REDIRECT_URI = f"http://localhost:{settings.app_port}/callback"


def _get_json(url):
    return json.loads(urllib.request.urlopen(url, timeout=15).read())


def _post_form(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


def _pkce_pair():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(40)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


@dataclass
class OAuthMeta:
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str


def discover() -> OAuthMeta:
    d = _get_json(WELL_KNOWN)
    return OAuthMeta(d["authorization_endpoint"], d["token_endpoint"], d["registration_endpoint"])


def register_client(meta: OAuthMeta) -> str:
    """Dynamic client registration -> client_id (public client, PKCE)."""
    body = json.dumps({
        "client_name": "RTG Forecast App",
        "redirect_uris": [REDIRECT_URI],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": SCOPE,
    }).encode()
    req = urllib.request.Request(meta.registration_endpoint, data=body,
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())["client_id"]


class IfsMcpClient:
    """Holds tokens + client_id; performs the auth-code flow and JSON-RPC calls.
    Token persistence is handled by the caller (auth router) via to_dict/from_dict."""

    def __init__(self, client_id=None, access_token=None, refresh_token=None,
                 expires_at=0, pkce_verifier=None, state=None):
        self.meta = discover()
        self.client_id = client_id
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self._pkce_verifier = pkce_verifier
        self._state = state
        self._rpc_id = 0

    # ---- auth-code flow ----
    def ensure_client(self):
        if not self.client_id:
            self.client_id = register_client(self.meta)
        return self.client_id

    def build_authorize_url(self) -> str:
        self.ensure_client()
        self._pkce_verifier, challenge = _pkce_pair()
        self._state = secrets.token_urlsafe(16)
        params = dict(response_type="code", client_id=self.client_id,
                      redirect_uri=REDIRECT_URI, scope=SCOPE, state=self._state,
                      code_challenge=challenge, code_challenge_method="S256")
        return f"{self.meta.authorization_endpoint}?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str):
        tok = _post_form(self.meta.token_endpoint, dict(
            grant_type="authorization_code", code=code, redirect_uri=REDIRECT_URI,
            client_id=self.client_id, code_verifier=self._pkce_verifier))
        self._store_tokens(tok)

    def refresh(self):
        tok = _post_form(self.meta.token_endpoint, dict(
            grant_type="refresh_token", refresh_token=self.refresh_token,
            client_id=self.client_id, scope=SCOPE))
        self._store_tokens(tok)

    def _store_tokens(self, tok: dict):
        self.access_token = tok["access_token"]
        self.refresh_token = tok.get("refresh_token", self.refresh_token)
        self.expires_at = time.time() + int(tok.get("expires_in", 3600)) - 60

    def _valid(self) -> bool:
        return bool(self.access_token) and time.time() < self.expires_at

    # ---- MCP Streamable-HTTP transport ----
    _session_id = None
    PROTOCOL_VERSION = "2025-06-18"

    def _headers(self, extra=None):
        h = {"Content-Type": "application/json",
             "Accept": "application/json, text/event-stream",
             "Authorization": f"Bearer {self.access_token}",
             "MCP-Protocol-Version": self.PROTOCOL_VERSION}
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        if extra:
            h.update(extra)
        return h

    def _send(self, payload: dict, expect_response=True):
        """POST a JSON-RPC message. Captures Mcp-Session-Id from the initialize response.
        Parses either plain JSON or SSE-framed (event:/data:) responses."""
        req = urllib.request.Request(settings.ifs_mcp_url,
                                     data=json.dumps(payload).encode(),
                                     headers=self._headers())
        try:
            resp = urllib.request.urlopen(req, timeout=60)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:500]
            raise RuntimeError(f"MCP HTTP {e.code} on {payload.get('method')}: {detail}") from None
        sid = resp.headers.get("Mcp-Session-Id")
        if sid:
            self._session_id = sid
        if not expect_response:
            return None
        raw = resp.read().decode()
        if "data:" in raw:  # SSE framing
            for line in raw.splitlines():
                if line.startswith("data:"):
                    raw = line[5:].strip()
                    break
        return json.loads(raw)

    def _ensure_session(self):
        if self._session_id:
            return
        self._rpc_id += 1
        init = self._send({
            "jsonrpc": "2.0", "id": self._rpc_id, "method": "initialize",
            "params": {"protocolVersion": self.PROTOCOL_VERSION,
                       "capabilities": {},
                       "clientInfo": {"name": "RTG Forecast", "version": "1.0"}}})
        if init and "error" in init:
            raise RuntimeError(init["error"])
        # notify server we're initialized (no response expected)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"},
                   expect_response=False)

    def _rpc(self, method, params):
        self._ensure_session()
        self._rpc_id += 1
        return self._send({"jsonrpc": "2.0", "id": self._rpc_id,
                           "method": method, "params": params})

    def call_tool(self, name: str, arguments: dict):
        if not self._valid():
            if self.refresh_token:
                self.refresh()
        resp = self._rpc("tools/call", {"name": name, "arguments": arguments})
        if "error" in resp:
            raise RuntimeError(resp["error"])
        content = resp.get("result", {}).get("content", [])
        if content and content[0].get("type") == "text":
            try:
                return json.loads(content[0]["text"])
            except Exception:
                return content[0]["text"]
        return resp.get("result")

    def execute_query(self, sql: str):
        return self.call_tool("execute_query", {"query": sql})

    # ---- persistence helpers ----
    def to_dict(self):
        return dict(client_id=self.client_id, access_token=self.access_token,
                    refresh_token=self.refresh_token, expires_at=self.expires_at)

    def is_authenticated(self):
        return bool(self.access_token) and (self._valid() or bool(self.refresh_token))
