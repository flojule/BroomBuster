import os

import httpx
import jwt
from fastapi import Header, HTTPException

_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")
_DEV_MODE = os.environ.get("DEV_MODE", "").lower() in ("1", "true", "yes")

_jwks_cache: dict | None = None


def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is None:
        url = f"{_SUPABASE_URL}/.well-known/jwks.json"
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
        _jwks_cache = resp.json()
    return _jwks_cache


def verify_jwt(authorization: str = Header(default="")) -> str:
    """
    Verify a Supabase-issued JWT and return the user_id (sub claim).
    - New Supabase projects: ES256 verified via JWKS endpoint.
    - Legacy projects: HS256 verified via SUPABASE_JWT_SECRET.
    - DEV_MODE=true: skips verification and returns "dev-user".
    """
    if _DEV_MODE:
        return "dev-user"

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = authorization.split(" ", 1)[1]

    try:
        header = jwt.get_unverified_header(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Malformed token: {exc}")

    alg = header.get("alg", "HS256")

    if alg == "ES256" and _SUPABASE_URL:
        # New Supabase projects sign with ES256; verify via JWKS.
        try:
            jwks = _get_jwks()
            kid = header.get("kid")
            key = None
            for k in jwks.get("keys", []):
                if k.get("kid") == kid:
                    key = jwt.algorithms.ECAlgorithm.from_jwk(k)
                    break
            if key is None:
                raise HTTPException(status_code=500, detail="Signing key not found in JWKS")
            payload = jwt.decode(token, key, algorithms=["ES256"], audience="authenticated")
            return payload["sub"]
        except HTTPException:
            raise
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")
    else:
        # Legacy HS256 path.
        if not _SUPABASE_JWT_SECRET:
            raise HTTPException(status_code=500, detail="SUPABASE_JWT_SECRET not configured")
        try:
            payload = jwt.decode(
                token, _SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated"
            )
            return payload["sub"]
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")
