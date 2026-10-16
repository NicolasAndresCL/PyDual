"""Modelos ORM (SQLAlchemy 2, mapeo declarativo con `Mapped[]`)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Marcas:
    """Columnas de auditoría comunes."""

    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Seccion(Marcas, Base):
    """Un ejercicio del notebook."""

    __tablename__ = "seccion"

    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[int] = mapped_column(unique=True, index=True)
    titulo: Mapped[str] = mapped_column(String(300))
    explicacion: Mapped[str] = mapped_column(Text)
    referencia: Mapped[str] = mapped_column(Text)
    imperativo: Mapped[str] = mapped_column(Text)
    declarativo: Mapped[str] = mapped_column(Text)
    epilogo: Mapped[str] = mapped_column(Text)
    # La celda completa: es lo que se ejecuta (referencia + ambas mitades + epílogo).
    fuente: Mapped[str] = mapped_column(Text)
    hash_contenido: Mapped[str] = mapped_column(String(64))

    ejecuciones: Mapped[list[Ejecucion]] = relationship(
        back_populates="seccion", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def etiqueta(self) -> str:
        return f"{self.numero:>2}. {self.titulo}"


class Cuaderno(Marcas, Base):
    """Metadatos del notebook. Siempre hay como mucho una fila (id = 1)."""

    __tablename__ = "cuaderno"

    id: Mapped[int] = mapped_column(primary_key=True)
    intro: Mapped[str] = mapped_column(Text)
    preludio: Mapped[str] = mapped_column(Text)
    # Lista de pares [imperativo, declarativo].
    resumen: Mapped[list[list[str]]] = mapped_column(JSON)
    nota_final: Mapped[str] = mapped_column(Text)
    # Todas las celdas de código en orden: es lo que ejecuta «ejecutar todo».
    fuentes: Mapped[list[str]] = mapped_column(JSON)
    hash_contenido: Mapped[str] = mapped_column(String(64))


class Ejecucion(Base):
    """Una ejecución real en subproceso. `seccion` nula = el cuaderno completo."""

    __tablename__ = "ejecucion"

    id: Mapped[int] = mapped_column(primary_key=True)
    seccion_id: Mapped[int | None] = mapped_column(
        ForeignKey("seccion.id", ondelete="CASCADE"), index=True
    )
    salida: Mapped[str] = mapped_column(Text)
    codigo_salida: Mapped[int | None]
    duracion_ms: Mapped[int]
    ok: Mapped[bool]
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    seccion: Mapped[Seccion | None] = relationship(back_populates="ejecuciones")
