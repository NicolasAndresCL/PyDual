"""Motor y fábrica de sesiones de SQLAlchemy."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def crear_motor(url: str) -> Engine:
    """Crea el motor. SQLite en memoria necesita una única conexión compartida.

    Sin `StaticPool`, cada conexión nueva vería una base de datos vacía distinta,
    y el `TestClient` atiende las peticiones en otro hilo.
    """
    match make_url(url):
        case u if u.get_backend_name() == "sqlite" and u.database in (None, "", ":memory:"):
            motor = create_engine(
                url, connect_args={"check_same_thread": False}, poolclass=StaticPool
            )
        case u if u.get_backend_name() == "sqlite":
            motor = create_engine(url, connect_args={"check_same_thread": False})
        case _:
            return create_engine(url, pool_pre_ping=True)
    # SQLite no aplica `ON DELETE CASCADE` salvo que se le pida en cada conexión.
    event.listen(motor, "connect", _activar_claves_foraneas)
    return motor


def _activar_claves_foraneas(conexion_dbapi: object, _registro: object) -> None:
    cursor = conexion_dbapi.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def crear_fabrica(motor: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=motor, expire_on_commit=False)


def responde(motor: Engine) -> bool:
    """`SELECT 1` contra la base de datos: lo que de verdad dice si está viva."""
    with motor.connect() as conexion:
        return conexion.execute(text("SELECT 1")).scalar_one() == 1
