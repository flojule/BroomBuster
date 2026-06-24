"""
Password hashing — bcrypt directly (passlib 1.7.x breaks on bcrypt >= 4.1).

Split out from auth.py so tools that only need to hash a password (e.g.
scripts/seed_account.py) can import it without triggering auth.py's import-time
JWT_SECRET guard.
"""

import hashlib
import secrets

# bcrypt ignores bytes past position 72; truncate so long passwords hash
# instead of raising.
_BCRYPT_MAX_BYTES = 72

try:
    import bcrypt

    def _hash_pw(pw: str) -> str:
        return bcrypt.hashpw(
            pw.encode("utf-8")[:_BCRYPT_MAX_BYTES], bcrypt.gensalt()
        ).decode("ascii")

    def _verify_pw(pw: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(
                pw.encode("utf-8")[:_BCRYPT_MAX_BYTES], hashed.encode("ascii")
            )
        except (ValueError, TypeError):
            return False

except ImportError:
    # Dev-only fallback when bcrypt isn't installed.
    def _hash_pw(pw: str) -> str:
        salt = secrets.token_hex(16)
        h = hashlib.sha256((salt + pw).encode()).hexdigest()
        return f"sha256:{salt}:{h}"

    def _verify_pw(pw: str, hashed: str) -> bool:
        if hashed.startswith("sha256:"):
            _, salt, h = hashed.split(":", 2)
            return hashlib.sha256((salt + pw).encode()).hexdigest() == h
        return False


# Constant-time decoy for unknown-email logins (blocks user enumeration by
# timing). A real hash of a random secret, so _verify_pw never rejects it as
# malformed the way a hand-written placeholder string does.
_DUMMY_PW_HASH = _hash_pw(secrets.token_hex(16))
