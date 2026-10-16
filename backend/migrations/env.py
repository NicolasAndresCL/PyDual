"""Entorno de Alembic: usa la misma URL y los mismos modelos que la aplicación."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import Configuracion
from app.data.modelos import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Solo hace falta la URL: se valida con el mismo validador que la aplicación
# (normaliza `postgres://` al driver psycopg v3) sin exigir el resto de campos.
url = Configuracion.model_validate(
    {"database_url": os.environ["DATABASE_URL"], "notebook_ruta": "."}
).database_url
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
target_metadata = Base.metadata


def migrar_sin_conexion() -> None:
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def migrar_con_conexion() -> None:
    motor = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with motor.connect() as conexion:
        context.configure(connection=conexion, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    migrar_sin_conexion()
else:
    migrar_con_conexion()
