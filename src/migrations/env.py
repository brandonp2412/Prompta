"""Shared migration environment. The caller owns the serialized transaction."""

from alembic import context
from sqlalchemy.engine import Connection

connection = context.config.attributes.get("connection")
if not isinstance(connection, Connection):
    raise RuntimeError("Use prompta-migrate or the store initialization API")
context.configure(
    connection=connection,
    version_table=context.config.get_main_option("version_table"),
    transactional_ddl=True,
)
with context.begin_transaction():
    context.run_migrations()
