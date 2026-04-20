"""pg_viewer package — startup guards for 013-postgres-viewer feature."""
import os

_INSECURE_JWT_SECRET = "aikm-secret-key-change-in-production"


def _assert_jwt_secret_safe() -> None:
    """If pg_viewer is enabled, require a real JWT_SECRET.

    The 012 fix in backend/app/auth.py already blocks production boot when
    JWT_SECRET is unset or equals the insecure default. This guard is an
    additional belt-and-suspenders: even in dev, if someone turns on
    PG_VIEWER_ENABLED they must configure a real secret.
    """
    from app.config import get_settings  # deferred import to avoid cycles

    settings = get_settings()
    if not settings.pg_viewer_enabled:
        return

    jwt_secret = os.getenv("JWT_SECRET", "")
    if not jwt_secret or jwt_secret == _INSECURE_JWT_SECRET:
        raise RuntimeError(
            "pg_viewer refuses to start: JWT_SECRET is unset or equals the "
            "insecure default. Generate a real secret: `openssl rand -hex 32` "
            "and set JWT_SECRET in production .env."
        )


_assert_jwt_secret_safe()

# Engine import MUST come after _assert_jwt_secret_safe() so the JWT guard
# runs before any connection pool is created.
from app.services.pg_viewer.engine import get_viewer_db  # noqa: E402

__all__ = ["get_viewer_db"]
