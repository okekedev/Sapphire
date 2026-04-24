"""
Async SQLAlchemy engine + session factory.

For Azure PostgreSQL (*.postgres.database.azure.com), Entra-only token auth is
used via DefaultAzureCredential — no password in the connection URL.
asyncpg supports an async callable as the `password` argument; the token is
fetched (and refreshed from cache) for every new physical connection.

Usage in routes:
    from app.database import get_db

    @router.get("/items")
    async def list_items(db: AsyncSession = Depends(get_db)):
        ...
"""

import ssl

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


def _build_connect_args() -> dict:
    url = settings.database_url

    if "postgres.database.azure.com" in url:
        # Azure PostgreSQL Flexible Server — Entra-only auth (no password).
        # asyncpg calls the async `password` callable for each new connection,
        # so the token is always fresh. azure-identity handles caching.
        from azure.identity.aio import DefaultAzureCredential  # type: ignore

        # exclude_managed_identity_credential: ManagedIdentityCredential probes
        # the Azure IMDS endpoint (169.254.169.254) at construction time, causing
        # a ~50s hang on local machines. Skip it in non-production; AzureCliCredential
        # (via az login) handles local dev. Production (Container App) sets APP_ENV=production.
        _cred = DefaultAzureCredential(
            exclude_managed_identity_credential=not settings.is_production,
        )

        async def _get_token() -> str:
            token = await _cred.get_token(
                "https://ossrdbms-aad.database.windows.net/.default"
            )
            return token.token

        # Azure PostgreSQL Flexible Server uses DigiCert-signed certs which are
        # in all standard CA stores — no need to disable verification.
        ssl_ctx = ssl.create_default_context()
        return {"ssl": ssl_ctx, "password": _get_token}

    if any(h in url for h in ("supabase.com", "neon.tech", "railway.app")):
        return {"ssl": ssl.create_default_context()}

    return {}


engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    connect_args=_build_connect_args(),
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Aliases
async_session_factory = async_session
AsyncSessionLocal = async_session  # semantic alias for seeding / background tasks


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


async def get_db():
    """FastAPI dependency — yields an async session, auto-closes."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
