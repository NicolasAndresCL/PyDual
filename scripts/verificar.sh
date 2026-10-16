#!/usr/bin/env bash
# Reproduce en local los jobs de .github/workflows/ci.yml, en el mismo orden:
#   lint → test (backend, frontend) → test-postgres → build
# Termina con código ≠ 0 si algo falla. Uso, desde cualquier sitio:
#   scripts/verificar.sh
#
# Necesita: el venv del repo (.venv) con requirements/dev.txt de ambos
# servicios, y Docker. No toca tu stack ni tus datos: el build usa un proyecto
# de Compose aparte («comparativo-verificar»), con puertos y volumen propios.
set -uo pipefail

V2="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -x "$V2/.venv/Scripts/python.exe" ]]; then
  PY="${PY:-$V2/.venv/Scripts/python.exe}"   # Windows (Git Bash)
else
  PY="${PY:-$V2/.venv/bin/python}"
fi
HADOLINT_IMAGE="hadolint/hadolint:v2.15.1"
PROYECTO="comparativo-verificar"
PG_CONTENEDOR="comparativo-verificar-pg"
PG_PUERTO=55433
export PYTHONIOENCODING=utf-8
# Ojo, Git Bash: NO exportar MSYS_NO_PATHCONV=1 aquí. Este script pasa a docker
# rutas del host (/tmp/..., /c/dev/...) que SÍ necesitan la conversión de MSYS;
# solo hace falta desactivarla para rutas Linux *dentro* del contenedor
# (p. ej. `docker exec ... ls /app`), y aquí no hay ninguna.

REGISTRO="$(mktemp)"
ENV_TEMPORAL="$(mktemp)"
fallos=0

limpiar() {
  docker rm -f "$PG_CONTENEDOR" >/dev/null 2>&1
  docker compose -p "$PROYECTO" --env-file "$ENV_TEMPORAL" -f "$V2/docker-compose.yml" \
    down -v >/dev/null 2>&1
  rm -f "$REGISTRO" "$ENV_TEMPORAL"
}
trap limpiar EXIT

paso() { # <descripción> <comando...>
  local descripcion="$1"; shift
  if "$@" >"$REGISTRO" 2>&1; then
    echo "  ✔ $descripcion"
  else
    echo "  ✖ $descripcion"
    tail -30 "$REGISTRO" | sed 's/^/      /'
    fallos=$((fallos + 1))
  fi
}

en() { # <directorio> <comando...>: ejecuta en un subshell dentro del directorio
  local directorio="$1"; shift
  (cd "$directorio" && "$@")
}

# --------------------------------------------------------------------- lint
echo "lint"
paso "ruff check" en "$V2" "$PY" -m ruff check .
paso "ruff format --check" en "$V2" "$PY" -m ruff format --check .
hadolint() { docker run --rm -i "$HADOLINT_IMAGE" <"$1"; }
paso "hadolint backend/Dockerfile" hadolint "$V2/backend/Dockerfile"
paso "hadolint frontend/Dockerfile" hadolint "$V2/frontend/Dockerfile"

# --------------------------------------------------------------------- test
echo "test"
pytest_cov() { "$PY" -m pytest -q -rs -p no:cacheprovider --cov --cov-report=term-missing --cov-fail-under=83; }
paso "backend: pytest + cobertura ≥ 83 % (SQLite)" en "$V2/backend" pytest_cov
paso "backend: core/ al 100 %" en "$V2/backend" "$PY" -m coverage report --include='app/core/*' --fail-under=100
paso "frontend: pytest + cobertura ≥ 83 %" en "$V2/frontend" pytest_cov

# ------------------------------------------------------------ test-postgres
echo "test-postgres"
postgres_listo() {
  docker run -d --rm --name "$PG_CONTENEDOR" -e POSTGRES_USER=app -e POSTGRES_PASSWORD=app \
    -e POSTGRES_DB=app_test -p "127.0.0.1:$PG_PUERTO:5432" postgres:17-alpine >/dev/null || return 1
  for _ in $(seq 1 60); do
    # pg_isready por TCP: el socket local responde antes de que acepte conexiones de fuera.
    docker exec "$PG_CONTENEDOR" pg_isready -h 127.0.0.1 -U app -d app_test >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}
con_postgres() { # `local -x`: exportada solo mientras dura la función (sirve también para funciones)
  local -x DATABASE_URL="postgresql+psycopg://app:app@127.0.0.1:$PG_PUERTO/app_test"
  "$@"
}
paso "Postgres de prueba arriba" postgres_listo
paso "alembic upgrade head" en "$V2/backend" con_postgres "$PY" -m alembic upgrade head
paso "alembic check (modelos = migraciones)" en "$V2/backend" con_postgres "$PY" -m alembic check
paso "backend: pytest contra Postgres" en "$V2/backend" con_postgres pytest_cov
docker rm -f "$PG_CONTENEDOR" >/dev/null 2>&1

# -------------------------------------------------------------------- build
echo "build"
sed "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$("$PY" -c 'import secrets; print(secrets.token_hex(24))')/" \
  "$V2/.env.example" >"$ENV_TEMPORAL"
printf 'PUERTO_DB=15433\nPUERTO_API=18000\nPUERTO_UI=18080\n' >>"$ENV_TEMPORAL"
compose() { docker compose -p "$PROYECTO" --env-file "$ENV_TEMPORAL" -f "$V2/docker-compose.yml" "$@"; }
humo() {
  curl -fsS http://127.0.0.1:18000/healthz || return 1
  local total ok
  total=$(curl -fsS http://127.0.0.1:18000/api/v1/secciones \
    | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["total"])')
  echo "secciones: $total"; [[ "$total" == "20" ]] || return 1
  ok=$(curl -fsS -X POST http://127.0.0.1:18000/api/v1/secciones/1/ejecuciones \
    | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["ok"])')
  echo "ejecución ok: $ok"; [[ "$ok" == "True" ]] || return 1
  curl -fsS -o /dev/null http://127.0.0.1:18080/
}
paso "docker compose up --build --wait (3 servicios healthy)" compose up -d --build --wait --wait-timeout 180
paso "humo: /healthz, 20 secciones, ejecución ok, UI 200" humo
paso "docker compose down -v" compose down -v

echo
if [[ "$fallos" -eq 0 ]]; then
  echo "Todo en verde."
else
  echo "$fallos paso(s) en rojo. No pushees todavía."
  exit 1
fi
