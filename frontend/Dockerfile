# Interfaz del comparativo (NiceGUI, puerto 8080). Solo habla con la API por HTTP.
# Multi-stage: el builder crea el venv; el runtime solo lo copia.

# ---------------------------------------------------------------- builder
FROM python:3.13-slim AS builder
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
FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    UI_HOST=0.0.0.0 \
    UI_PUERTO=8080
RUN useradd --create-home --shell /bin/bash --uid 1000 app
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY app/ app/
# UID numérico (el de `app`): verificable por runAsNonRoot y por hadolint (DL3066).
USER 1000:1000
# NiceGUI guarda su almacenamiento en `.nicegui/` del directorio de trabajo;
# /app es de root, así que se trabaja desde el home del usuario.
WORKDIR /home/app
ENV PYTHONPATH=/app
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4)"]
CMD ["python", "-m", "app.main"]
