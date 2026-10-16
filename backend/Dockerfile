# API del comparativo (FastAPI + SQLAlchemy + Alembic).
# Multi-stage: el builder crea el venv; el runtime solo lo copia.

# ---------------------------------------------------------------- builder
FROM python:3.14-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
# Primero las dependencias: si solo cambia el código, esta capa sale de caché.
COPY requirements/base.txt requirements/base.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements/base.txt

# ---------------------------------------------------------------- runtime
FROM python:3.14-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"
RUN useradd --create-home --shell /bin/bash --uid 1000 app
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
# El código queda en propiedad de root: el usuario `app` (y el código del
# notebook que ejecuta) puede leerlo pero no modificarlo.
COPY alembic.ini ./
COPY migrations/ migrations/
COPY app/ app/
# UID numérico (el de `app`): verificable por runAsNonRoot y por hadolint (DL3066).
USER 1000:1000
EXPOSE 8000
# Sano = /healthz responde 200, y /healthz hace SELECT 1 contra Postgres.
# urllib lanza excepción con un 503, así que el proceso sale con código 1.
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"]
# Migraciones al arrancar; `exec` deja a uvicorn como PID 1 (recibe SIGTERM).
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:crear_app --factory --host 0.0.0.0 --port 8000 --proxy-headers"]
