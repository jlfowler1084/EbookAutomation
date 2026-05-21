"""Shared slowapi limiter + trusted-proxy-gated key extractor (EB-324 Unit 8).

All production traffic flows Cloudflare → nginx → uvicorn(127.0.0.1). The
real client IP arrives in the ``CF-Connecting-IP`` header, but that header is
ONLY trustworthy when the immediate peer (``request.client.host``) is the
local nginx proxy. An attacker who discovers the Hetzner VM's raw IP and hits
it directly has a non-loopback peer and a forgeable ``CF-Connecting-IP`` — so
``trusted_client_key`` ignores the header in that case and keys on the real
peer address. Without this gate, an attacker rotates the header per request to
get a fresh rate-limit bucket each time, bypassing all per-IP limiting (plan
review P1-1).

Origin lockdown (nginx allowlisting Cloudflare's published IP ranges) is the
deploy-side half of this defense — see deploy/nginx.conf + CLOUDFLARE.md. The
two layers are paired: the key extractor trusts CF-Connecting-IP from the
local proxy, and nginx ensures only Cloudflare can reach that proxy.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

# Hosts that are the LOCAL reverse proxy. Cloudflare → nginx → uvicorn means
# uvicorn's peer is always loopback in production. Anything else is a direct
# hit on the origin and its CF-Connecting-IP header is untrusted.
_TRUSTED_PROXY_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "::1"})


def trusted_client_key(request: Request) -> str:
    """Rate-limit key: the real client IP, resolved safely behind Cloudflare.

    Honors CF-Connecting-IP only when the request's immediate peer is the
    local nginx proxy. Otherwise falls back to the peer address itself so a
    forged header from a direct origin hit can't mint fresh buckets.
    """
    client_host = request.client.host if request.client else ""
    if client_host in _TRUSTED_PROXY_HOSTS:
        cf_ip = request.headers.get("cf-connecting-ip")
        if cf_ip:
            return cf_ip
    return get_remote_address(request)


def parent_job_id_key(request: Request) -> str:
    """Per-parent rate-limit key for /reconvert/{parent_job_id}.

    Falls back to the trusted client key if the path param is somehow
    absent (shouldn't happen for a matched route) so the limiter never
    crashes on a missing key.
    """
    parent_job_id = request.path_params.get("parent_job_id")
    return f"reconvert_parent:{parent_job_id}" if parent_job_id else trusted_client_key(request)


def kindle_job_id_key(request: Request) -> str:
    """Per-job rate-limit key for /send-to-kindle/{job_id}.

    Caps total outbound sends per job (anti-spam-relay) independent of the
    per-IP limit.
    """
    job_id = request.path_params.get("job_id")
    return f"kindle_job:{job_id}" if job_id else trusted_client_key(request)


# Module-level limiter shared by route decorators. key_func is the per-IP
# (Cloudflare-aware) extractor by default; per-resource decorators pass their
# own key_func explicitly.
limiter = Limiter(key_func=trusted_client_key)
