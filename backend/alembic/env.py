import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import dotenv_values
from sqlalchemy import engine_from_config, pool

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import settings
from backend.app.core.database import Base
from backend.app.models import User, RefreshToken, Conversation, Message, Device

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_migration_url() -> str:
    """Resolve the migration database URL strictly and fail closed if missing.

    Resolution order:
    1. OS environment variable: MIGRATION_DATABASE_URL
    2. backend/.env file: MIGRATION_DATABASE_URL parsed via python-dotenv

    Never falls back to runtime DATABASE_URL or default SQLite settings.
    """
    # 1. Check OS environment first (e.g. CI/CD or explicit shell environment)
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if url and url.strip():
        return url.strip()

    # 2. Check backend/.env directly via python-dotenv
    backend_env = PROJECT_ROOT / "backend" / ".env"
    if backend_env.exists():
        parsed = dotenv_values(backend_env)
        env_url = parsed.get("MIGRATION_DATABASE_URL")
        if env_url and env_url.strip():
            return env_url.strip()

    # 3. Fail closed — never silently fall back to application DATABASE_URL or SQLite default
    raise RuntimeError(
        "FATAL STARTUP BLOCKED: MIGRATION_DATABASE_URL is not configured. "
        "Alembic migrations require dedicated migration credentials (oliver_migrator). "
        "Define MIGRATION_DATABASE_URL in the OS environment or in backend/.env."
    )


def run_migrations_offline() -> None:
    url = get_migration_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_migration_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
