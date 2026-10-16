# PyDual — Python imperativo vs. declarativo

[![CI](https://github.com/NicolasAndresCL/PyDual/actions/workflows/ci.yml/badge.svg)](https://github.com/NicolasAndresCL/PyDual/actions/workflows/ci.yml)
![Versión](https://img.shields.io/badge/versi%C3%B3n-2.0.0-blue)
![Python](https://img.shields.io/badge/python-3.13-3776AB)

| | |
|---|---|
| **Versión** | 2.0.0 |
| **Fecha** | 15 de octubre de 2026 |
| **Autor** | [Nicolás Andrés Cano Leal](#autor) |

Aplicación web para estudiar Python comparando, ejercicio a ejercicio, la
versión **imperativa** (cómo se hace) y la **declarativa** (qué se quiere) del
mismo problema. Lee un notebook de 20 ejercicios
([`datos/python_declarativo.ipynb`](datos/python_declarativo.ipynb)) y muestra
las dos mitades lado a lado, con métricas, explicación y ejecución real.

Es la segunda versión de un comparativo de escritorio en tkinter (la «v1», que
no forma parte de este repositorio), ahora como aplicación web con persistencia:

- **Frontend**: NiceGUI (puerto 8080).
- **Backend**: FastAPI, con SQLAlchemy 2 (`Mapped[]`), psycopg v3 y Alembic.
- **Persistencia**: PostgreSQL 17 (secciones, metadatos del cuaderno e
  historial de ejecuciones).
- **Todo dockerizado** con Compose.

El notebook de `datos/` es la **única fuente de verdad**: no se copia a ninguna
imagen; la API lo lee desde un bind mount de solo lectura y lo vuelca a la base
de datos al arrancar (si está vacía) o al pulsar *Sincronizar*.

El código está escrito en el mismo estilo que enseña el notebook: funciones
puras, `dataclass(frozen=True)`, `match`, `Enum`, comprehensions y generadores.
El parser de la v1 era un bucle con variables de estado («título pendiente»);
aquí la misma regla se expresa como datos (`itertools.pairwise` sobre celdas
clasificadas), y un test de paridad garantiza que ambos producen lo mismo.

## Arquitectura

```
PyDual/
├── .github/                  # CI (workflows/ci.yml), Dependabot, plantillas
├── datos/
│   └── python_declarativo.ipynb   # los 20 ejercicios: fuente de verdad
├── docker-compose.yml        # db (postgres:17-alpine) + api + ui
├── .env.example              # plantilla de variables (copiar a .env)
├── pyproject.toml            # ruff: reglas del repo, objetivo py313
├── scripts/verificar.sh      # los mismos jobs que el CI, en el mismo orden
├── backend/
│   ├── Dockerfile            # multi-stage, no-root, HEALTHCHECK a /healthz
│   ├── alembic.ini
│   ├── migrations/           # env.py + versions/0001_esquema_inicial.py
│   ├── requirements/{base,dev}.txt
│   ├── app/
│   │   ├── config.py         # pydantic-settings, todo desde el entorno
│   │   ├── main.py           # fábrica crear_app(), lifespan, /healthz
│   │   ├── core/             # lógica pura, sin I/O (100 % de cobertura)
│   │   │   ├── parser.py     #   notebook JSON -> CuadernoParseado
│   │   │   ├── metricas.py   #   líneas efectivas, reducción
│   │   │   ├── veredicto.py  #   ahorra / ocupa más / sin datos
│   │   │   ├── filtro.py     #   búsqueda sin tildes ni mayúsculas
│   │   │   ├── modelos.py    #   dataclasses inmutables + plan de sincronización
│   │   │   └── errores.py    #   excepciones de dominio (raíz ErrorDeDominio)
│   │   ├── data/             # SQLAlchemy: motor, modelos ORM, repositorio
│   │   ├── servicios/        # casos de uso: sincronizar, ejecutar en subproceso
│   │   └── api/              # rutas, esquemas pydantic, dependencias, errores
│   └── tests/                # pytest: core, API (TestClient), paridad con la v1 (si está)
└── frontend/
    ├── Dockerfile            # multi-stage, no-root, HEALTHCHECK a /healthz
    ├── requirements/{base,dev}.txt
    ├── app/
    │   ├── config.py         # API_URL, tiempos, host y puerto
    │   ├── cliente.py        # httpx: único acceso a datos; errores -> ErrorApi
    │   ├── modelos.py        # lo que la UI espera de la API (pydantic)
    │   ├── presentacion.py   # decisiones de vista como funciones puras
    │   ├── pagina.py         # la página NiceGUI (ui.refreshable_method)
    │   └── main.py           # registra la página y arranca ui.run
    └── tests/                # pytest + fixture `user` de NiceGUI, API simulada
```

Flujo: navegador → **ui** (NiceGUI) → HTTP → **api** (FastAPI) → **db**
(Postgres). La UI nunca toca la base de datos ni el notebook.

## Levantar con Docker

```bash
cp .env.example .env
# Pon una contraseña en POSTGRES_PASSWORD (Compose se niega a arrancar sin ella):
python -c "import secrets; print(secrets.token_hex(24))"
docker compose up -d --build --wait   # espera a que los 3 servicios estén healthy
```

| Servicio | URL (solo `127.0.0.1`) |
|---|---|
| Interfaz | <http://127.0.0.1:8080> |
| API + documentación OpenAPI | <http://127.0.0.1:8000/docs> |
| Postgres (para correr la API sin Docker) | `127.0.0.1:5433` |

La API aplica `alembic upgrade head` al arrancar y, si la tabla de secciones
está vacía, sincroniza el notebook. Los datos viven en el volumen nombrado
`postgres_data`: `docker compose down` los conserva; `docker compose down -v`
los borra.

Tras editar `datos/python_declarativo.ipynb` en el host, pulsa **Sincronizar** en la UI (o
`POST /api/v1/sincronizacion`): el bind mount ya ve el archivo nuevo.

## Correr en local sin Docker

Requiere Python 3.13+ (probado con 3.14.3: todas las dependencias tienen wheel).

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements/dev.txt -r frontend/requirements/dev.txt
# (en Linux/macOS: .venv/bin/python)

# Base de datos: la del compose (`docker compose up -d db`) u otra cualquiera.
export DATABASE_URL="postgresql://comparativo:<contraseña>@127.0.0.1:5433/comparativo"
export NOTEBOOK_RUTA="$(pwd)/datos/python_declarativo.ipynb"

cd backend
../.venv/Scripts/python -m alembic upgrade head
../.venv/Scripts/python -m uvicorn app.main:crear_app --factory --port 8000

# En otra terminal, desde la raíz del repo:
cd frontend
API_URL=http://127.0.0.1:8000 ../.venv/Scripts/python -m app.main   # http://127.0.0.1:8080
```

## Endpoints

Prefijo `/api/v1`. Ninguna ruta acepta código en el cuerpo: solo se ejecuta lo
que ya está guardado.

| Método | Ruta | Qué hace |
|---|---|---|
| `GET` | `/healthz` | `SELECT 1` contra la BD; 200 o 503 (sin prefijo) |
| `GET` | `/secciones?q=` | Lista con métricas y veredicto; `q` filtra sin tildes ni mayúsculas en título, explicación, código de ambas mitades y referencia (mismo criterio que `_coincide` de la v1) |
| `GET` | `/secciones/{n}` | Detalle: ambas mitades, explicación, referencia, epílogo, métricas, veredicto |
| `GET` | `/cuaderno` | Introducción y tabla resumen «qué reemplaza a qué» (409 si no se ha sincronizado) |
| `POST` | `/sincronizacion` | Reimporta el notebook: idempotente y transaccional |
| `POST` | `/secciones/{n}/ejecuciones` | Ejecuta preludio + celda de la sección y guarda el resultado (201) |
| `GET` | `/secciones/{n}/ejecuciones?limite=` | Historial de la sección, la más reciente primero |
| `POST` | `/cuaderno/ejecuciones` | Ejecuta el notebook completo, incluida la comprobación final (201) |
| `GET` | `/cuaderno/ejecuciones?limite=` | Historial de ejecuciones del cuaderno completo |

Todos los errores —de dominio, de validación de FastAPI, 404/405 de rutas y los
no controlados— salen con el mismo contrato:

```json
{"error": {"codigo": "seccion_no_encontrada", "mensaje": "No existe la sección 99.", "detalle": {"seccion": 99}}}
```

| Código | HTTP | Cuándo |
|---|---|---|
| `cuaderno_invalido` | 422 | El notebook rompe el contrato de marcadores (`detalle.seccion` dice cuál) o no es JSON |
| `validacion` | 422 | Parámetros inválidos (`detalle.errores`) |
| `seccion_no_encontrada` | 404 | Número de sección inexistente |
| `cuaderno_no_sincronizado` | 409 | Aún no se importó el notebook |
| `notebook_no_disponible` | 503 | El archivo no existe o no se puede leer |
| `base_de_datos_no_disponible` | 503 | `/healthz` no logra hacer `SELECT 1` |
| `error_interno` | 500 | Cualquier otra excepción (la traza va al log, no a la respuesta) |

## La interfaz

- **Lista lateral** con filtro (`/` para enfocarlo, `Esc` para limpiarlo) y un
  punto de color por veredicto.
- **Dos paneles de código** con resaltado (`ui.code`) y métricas de cada uno.
- **Veredicto** bajo el título de la sección.
- **Pestañas**: *Por qué*, *Referencia*, *Comprobación*, *Salida* e
  *Historial* de ejecuciones.
- **Diálogos** de introducción (`F1`) y de tabla resumen (`F2`).
- **Ejecutar** la sección (`F5`) o **ejecutar todo** (`Ctrl+F5`); el navegador
  no recarga la página con `F5` porque la propia página anula esas teclas.
- **Sincronizar** reimporta el notebook y notifica qué cambió.

Si la API no responde, aparece un aviso con *Reintentar*; la página no se cae.

## Variables de entorno

| Variable | Servicio | Por defecto | Para qué |
|---|---|---|---|
| `POSTGRES_PASSWORD` | db, api | **obligatoria** | Contraseña de Postgres (Compose falla si falta) |
| `POSTGRES_USER` / `POSTGRES_DB` | db, api | `comparativo` | Usuario y base |
| `DATABASE_URL` | api | **obligatoria** (Compose la arma) | URL de SQLAlchemy; `postgres://` y `postgresql://` se normalizan a psycopg v3 |
| `NOTEBOOK_RUTA` | api | **obligatoria** (Compose: `/datos/python_declarativo.ipynb`) | Notebook fuente |
| `TIEMPO_LIMITE_EJECUCION_S` | api | `60` | Límite de cada ejecución en subproceso |
| `SINCRONIZAR_AL_ARRANCAR` | api | `true` | Sincroniza si la tabla está vacía |
| `LIMITE_HISTORIAL` | api | `50` | Ejecuciones devueltas por defecto |
| `NIVEL_LOG` | api | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `API_URL` | ui | **obligatoria** (Compose: `http://api:8000`) | URL base de la API |
| `TIEMPO_ESPERA_API_S` | ui | `90` | Espera máxima a la API; debe superar el límite de ejecución |
| `UI_HOST` / `UI_PUERTO` | ui | `127.0.0.1` / `8080` | Escucha de NiceGUI (la imagen usa `0.0.0.0`) |
| `PUERTO_DB` / `PUERTO_API` / `PUERTO_UI` | compose | `5433` / `8000` / `8080` | Puertos publicados en `127.0.0.1` |

## Verificación

```bash
scripts/verificar.sh
```

Reproduce los jobs de [`.github/workflows/ci.yml`](.github/workflows/ci.yml)
en el mismo orden y sale con código ≠ 0 si algo falla:

1. **lint** — `ruff check` y `ruff format --check` de todo el repo y hadolint
   de ambos Dockerfiles.
2. **test** — pytest con cobertura ≥ 83 % en backend (SQLite en memoria) y
   frontend, y `app/core/` del backend al 100 %.
3. **test-postgres** — Postgres desechable, `alembic upgrade head`,
   `alembic check` (modelos y migraciones coinciden) y la suite del backend.
4. **build** — `docker compose up --build --wait` en un proyecto aparte
   (`comparativo-verificar`, puertos 15433/18000/18080), humo contra el stack
   (healthz, 20 secciones, una ejecución real, UI 200) y `down -v`. No toca tu
   stack ni tus datos.

Por separado:

```bash
cd backend && ../.venv/Scripts/python -m pytest -rs --cov --cov-fail-under=83
../.venv/Scripts/python -m coverage report --include='app/core/*' --fail-under=100
cd ../frontend && ../.venv/Scripts/python -m pytest --cov --cov-fail-under=83
```

Los tests del backend usan SQLite en memoria salvo que el entorno traiga un
`DATABASE_URL` (así corre el job `test-postgres`).

## Decisiones de diseño

- **Capas.** `core/` no hace I/O: el parser recibe el texto del notebook, no la
  ruta. Leer el archivo y escribir en la BD está en `servicios/` y `data/`.
  Así lo que más importa (el contrato de marcadores) se prueba sin disco ni BD.
- **Paridad strangler-fig.** `tests/test_paridad_v1.py` importa la v1
  (`comparativo.py`) y exige que el parser v2 produzca exactamente las mismas
  secciones (número, título, explicación, referencia, ambas mitades, epílogo,
  celda) y los mismos metadatos. La v1 no está en este repo: se busca en
  `$COMPARATIVO_V1` o en `../comparativo.py`. Si no existe, el test se **omite
  con el motivo a la vista** (`-rs`; así corre en CI); si existe pero no se
  puede importar (falta tkinter), **falla**.
- **Sincronización idempotente y transaccional.** Primero se parsea entero (si
  falla, 422 y la BD intacta); luego `planificar_sincronizacion` —función
  pura— decide qué crear, actualizar (por hash SHA-256 del contenido), dejar o
  borrar, y todo se escribe en una sola transacción. Repetirla sin cambios no
  escribe nada. Las secciones que desaparecen del notebook se borran con su
  historial (`ON DELETE CASCADE`).
- **Filtro en Python, no en SQL.** `ILIKE` no ignora tildes de forma portable
  entre SQLite y Postgres; con 20 filas, reutilizar el criterio exacto de la v1
  vale más que empujarlo a la BD.
- **Ejecución acotada.** Solo se ejecuta código guardado (por número de
  sección o el cuaderno completo). Subproceso con `python -I`, archivo temporal
  (nunca `python -c`: WinError 206 con el notebook completo), directorio de
  trabajo desechable, timeout configurable y **entorno filtrado**: el código
  del notebook no ve `DATABASE_URL`. La transacción de lectura se cierra antes
  de lanzar el subproceso para no retener una conexión durante la ejecución.
- **Contenedores endurecidos.** Usuario no-root (UID 1000), código propiedad de
  root (legible, no modificable), sistema de archivos de solo lectura con
  `tmpfs` en `/tmp`, `cap_drop: ALL`, `no-new-privileges` y `pids_limit` en la
  API. Puertos publicados solo en `127.0.0.1`.
- **Un único manejador de errores** (`api/errores.py`, con `match` por tipo):
  `warning` para errores de negocio, `exception` con traza para lo no
  reconocido.
- **`crear_app()` como fábrica** (`uvicorn --factory`): importar el módulo no
  exige entorno, y los tests inyectan su propio motor de BD.
- **El frontend valida lo que recibe** con sus propios modelos pydantic (un
  subconjunto de los de la API) y convierte cualquier fallo de red o de formato
  en `ErrorApi`, que la página muestra como aviso.
- **Atajos.** `Ctrl+F` es la búsqueda del navegador, así que el filtro se
  enfoca con `/`. `F1`, `F2` y `F5` se anulan en el navegador para que lleguen
  a la aplicación.

## Autor

**Nicolás Andrés Cano Leal**\
Backend Engineer → SRE | Python · Django · Kubernetes · Terraform · CI/CD

- LinkedIn: [linkedin.com/in/nicolasandrescl](https://www.linkedin.com/in/nicolasandrescl/)
- Portafolio: [nicolasandrescl.github.io](https://nicolasandrescl.github.io/)
- Correo: [nicolas.cano.leal@gmail.com](mailto:nicolas.cano.leal@gmail.com)

PyDual v2.0.0 · 15 de octubre de 2026
