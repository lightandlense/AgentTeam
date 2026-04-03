import hashlib
import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import get_settings

EXEMPT_PATHS = {"/health"}


class RetellAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        signature = request.headers.get("X-Retell-Signature")
        if not signature:
            return JSONResponse({"detail": "Missing signature"}, status_code=401)

        body = await request.body()
        secret = get_settings().retell_webhook_secret.encode()
        expected = hmac.new(secret, body, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected, signature):
            return JSONResponse({"detail": "Invalid signature"}, status_code=401)

        return await call_next(request)
