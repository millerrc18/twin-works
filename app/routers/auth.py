"""IFS OAuth connect/callback routes (browser-login, PKCE, localhost callback)."""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.data.ifs_mcp_client import IfsMcpClient
from app.data import token_store

router = APIRouter()

# pending client survives the browser redirect (holds PKCE verifier + state)
_pending: dict = {"client": None}


@router.get("/connect")
async def connect(db: AsyncSession = Depends(get_db)):
    """Start the IFS OAuth flow — redirect the user's browser to Azure login.
    Always register a FRESH client (dynamic registration is cheap and stateless-safe);
    reusing a stale/expired client_id causes 'Unknown client_id' at authorize."""
    client = IfsMcpClient(client_id=None)
    url = client.build_authorize_url()
    _pending["client"] = client
    return RedirectResponse(url)


@router.get("/disconnect")
async def disconnect(db: AsyncSession = Depends(get_db)):
    """Clear stored IFS tokens (recover from a poisoned/stale credential)."""
    from sqlalchemy import delete
    from app.models import OAuthToken
    await db.execute(delete(OAuthToken).where(OAuthToken.service == "ifs"))
    await db.commit()
    _pending["client"] = None
    return HTMLResponse("<h3>IFS tokens cleared.</h3><p><a href='/connect'>Reconnect</a></p>")


@router.get("/callback")
async def callback(request: Request, db: AsyncSession = Depends(get_db)):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    err = request.query_params.get("error")
    client: IfsMcpClient = _pending.get("client")
    if err:
        return HTMLResponse(f"<h3>IFS auth error: {err}</h3><a href='/'>back</a>", status_code=400)
    if not client or state != client._state:
        return HTMLResponse("<h3>Auth state mismatch — retry /connect</h3>", status_code=400)
    import traceback
    try:
        client.exchange_code(code)
    except Exception as e:
        tb = traceback.format_exc()
        return HTMLResponse(f"<h3>Token exchange failed</h3><pre>{e}\n\n{tb}</pre>", status_code=500)
    try:
        d = client.to_dict()
        await token_store.save_tokens(db, "ifs", d["client_id"], d["access_token"],
                                      d["refresh_token"] or "", d["expires_at"])
    except Exception as e:
        tb = traceback.format_exc()
        return HTMLResponse(f"<h3>Saving tokens failed</h3><pre>{e}\n\n{tb}</pre>", status_code=500)
    _pending["client"] = None
    return HTMLResponse(
        "<h3>Connected to IFS ✓</h3><p>Live data is now available. "
        "<a href='/'>Go to dashboard</a></p>")
