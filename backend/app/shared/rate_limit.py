"""API rate limiting via slowapi.

Behind Cloudflare + nginx the socket peer is the proxy, so we key on the real client
IP from Cloudflare's CF-Connecting-IP (falling back to X-Forwarded-For, then peer).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def client_ip(request: Request) -> str:
    cf = request.headers.get("CF-Connecting-IP")
    if cf:
        return cf.strip()
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        # first hop is the original client
        return xff.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=client_ip, default_limits=[])

# Reusable limit strings (tune via these constants).
LIMIT_LOGIN = "10/minute"
LIMIT_OTP = "10/minute"
LIMIT_PASSWORD = "10/minute"
LIMIT_INVITE = "20/hour"
LIMIT_AI = "30/minute"
LIMIT_SEARCH = "60/minute"     # global search is cheap but fan-out; cap abusive polling
LIMIT_EXPORT = "20/hour"       # exports are heavier; tighter cap
