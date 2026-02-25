import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.database import Base
from app.business.billing import models as billing_models  # noqa: F401
from app.business.payments import models as payments_models  # noqa: F401
from app.business.catalog import models as catalog_models  # noqa: F401
from app.business.revenue import models as revenue_models  # noqa: F401
from app.business.subscription import models as subscription_models  # noqa: F401
from app.authz import models as authz_models  # noqa: F401
from app.crm import models as crm_models  # noqa: F401
from app.platform.ledger import models as ledger_models  # noqa: F401
from app.models import audit  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = os.getenv("DATABASE_URL", section.get("sqlalchemy.url", ""))
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
