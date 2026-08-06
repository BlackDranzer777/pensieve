# 01 — Building the Docker Stack, Step by Step

How the three containers are built from nothing, what each file contributes, and
what every command actually does.

---

## Prerequisites

Only one thing must exist on your machine:

```bash
docker --version
```

Expected: `Docker version 26.0.0` or newer. That is genuinely all — Python,
Node and PostgreSQL are **not** required to run the Docker stack, because each
container brings its own.

Verify the engine is not just installed but actually running:

```bash
docker version
```

If you see a `Server:` section, the daemon is up. If it says
*"error during connect"*, start Docker Desktop and wait ~30 seconds.

---

## The files involved

Seven files drive the whole build. Nothing else is consulted.

| File | Lines | Role |
|---|---|---|
| `docker-compose.yml` | 88 | Defines the services, ports, volumes, healthchecks and startup order |
| `infrastructure/docker/api.Dockerfile` | 69 | Recipe for the backend image |
| `infrastructure/docker/web.Dockerfile` | 37 | Recipe for the frontend image |
| `infrastructure/docker/nginx.conf` | 43 | Web server config baked into the frontend image |
| `infrastructure/docker/spark.Dockerfile` | 37 | Recipe for the optional PySpark job image |
| `.dockerignore` | 32 | What **not** to send to the build — critical for speed |
| `.env` | — | Credentials and ports (copied from `.env.example`) |

The database needs no Dockerfile: it uses the official `postgres:16-alpine`
image straight from Docker Hub, unmodified.

### Why `.dockerignore` matters more than it looks

When you run a build, Docker first uploads a copy of the project — the "build
context" — to the engine. Without `.dockerignore`, that upload would include
`node_modules` (173 MB, 22,186 files) and `.venv` (866 MB, 17,844 files) on
**every single build**. The file excludes them, along with the generated
`data/` layers, so the context stays small and builds stay fast.

---

## Step 1 — Create your `.env`

The compose file reads credentials and ports from `.env`, which is gitignored
so secrets never reach the repository.

**PowerShell:**

```powershell
Copy-Item .env.example .env
```

**Bash / macOS / Linux:**

```bash
cp .env.example .env
```

The defaults work as-is for local development. The values that matter here:

```
POSTGRES_USER=pensieve
POSTGRES_PASSWORD=pensieve_local_dev
POSTGRES_DB=pensieve
POSTGRES_PORT=5433
```

> **Why port 5433 and not the usual 5432?** So it cannot collide with a
> PostgreSQL already installed natively on your machine. If you skip this and
> something already owns 5432, the container fails to start with
> *"port is already allocated"* — a confusing error for a container that is
> otherwise perfectly configured.

---

## Step 2 — Check the compose file is valid

Before building anything, catch syntax and reference errors in one second:

```bash
docker compose config --quiet
```

Silence means valid. This parses the YAML, resolves every `${VARIABLE}` against
your `.env`, and verifies the referenced Dockerfiles exist.

To see what services are defined:

```bash
docker compose config --services
```

Output for this project:

```
postgres
api
web
```

---

## Step 3 — Build the images

```bash
docker compose build
```

This reads the two Dockerfiles and produces two images. It does **not** start
anything — building and running are separate steps.

Expect roughly **3–6 minutes on the first run** and a handful of seconds
afterwards, because Docker caches each layer.

### What happens inside the API build

`api.Dockerfile` is a **multi-stage** build — two `FROM` statements, but only
the last one becomes the final image:

**Stage 1 (`builder`)** — starts from `python:3.12-slim`, creates a virtualenv
at `/opt/venv`, and installs dependencies. Crucially it copies *only*
`pyproject.toml` first, so the slow dependency install is cached and re-runs
only when the dependency list itself changes — not when you edit a `.py` file.

**Stage 2 (`runtime`)** — a fresh `python:3.12-slim`, into which the finished
`/opt/venv` is copied. pip's caches, build tooling and intermediate files stay
behind in stage 1 and never reach the final image.

The image also installs its dependencies via the `serving` extra, not
`pipelines`:

```dockerfile
RUN pip install ".[api,serving]"
```

That excludes Lingua (305 MB of bundled language models), SciPy and
scikit-learn — none of which the API imports. **This one line is the difference
between a 1.1 GB image and a 594 MB one.**

Finally it creates and switches to a non-root user:

```dockerfile
RUN useradd --create-home --uid 1001 pensieve
USER pensieve
```

You can confirm this on the running container:

```bash
docker compose exec api id
```

```
uid=1001(pensieve) gid=1001(pensieve) groups=1001(pensieve)
```

### What happens inside the web build

Also multi-stage, and the contrast is even sharper:

**Stage 1 (`builder`)** — `node:20-alpine`, runs `npm ci` then `npm run build`,
producing compiled static files in `dist/`.

**Stage 2 (`runtime`)** — `nginx:1.27-alpine`, into which only `dist/` and
`nginx.conf` are copied.

**The final image contains no Node, no npm and no source code.** Verify it:

```bash
docker compose exec web sh -c "command -v node || echo 'no node here'"
```

That is why the frontend image is 49.8 MB while `node_modules` on your host is
173 MB. Node was scaffolding for the build and got thrown away.

---

## Step 4 — Start the stack

```bash
docker compose up -d
```

`-d` means "detached" — it runs in the background and gives your terminal back.
Omit it to watch the logs stream live (then `Ctrl+C` stops everything).

To build and start in one go:

```bash
docker compose up --build -d
```

### Startup order is not accidental

The compose file makes the API wait for a genuinely ready database, not merely
a started one:

```yaml
depends_on:
  postgres:
    condition: service_healthy
```

Without `condition: service_healthy`, Docker would start the API the moment the
Postgres *container* existed — several seconds before PostgreSQL finished
initialising — and the API would crash on a connection refused. The web
container waits on the API in the same way.

You can watch this in the output:

```
Container pensieve-postgres  Waiting
Container pensieve-postgres  Healthy
Container pensieve-api       Starting
```

---

## Step 5 — Verify it worked

```bash
docker compose ps
```

The target state — all three `(healthy)`:

```
NAME                STATUS                    PORTS
pensieve-api        Up 7 hours (healthy)      0.0.0.0:8000->8000/tcp
pensieve-postgres   Up 7 hours (healthy)      0.0.0.0:5433->5432/tcp
pensieve-web        Up 7 hours (healthy)      0.0.0.0:5174->80/tcp
```

"healthy" is not decorative — each container runs a real probe on a schedule:

| Container | Probe | Interval |
|---|---|---|
| postgres | `pg_isready -U pensieve -d pensieve` | 5s |
| api | `curl --fail --silent http://127.0.0.1:8000/api/v1/health` | 15s |
| web | `wget --quiet --tries=1 --spider http://127.0.0.1/` | 15s |

Now check the endpoints:

```bash
curl http://localhost:8000/api/v1/health
```

```json
{"status":"ok","version":"0.1.0","environment":"development",
 "processing_version":"1.0.0","checks":[{"name":"database","status":"ok"}]}
```

`"database":"ok"` proves the API reached PostgreSQL across the internal
network — the whole stack is wired correctly.

Then the dashboard, and the API through nginx's proxy:

```bash
curl -o /dev/null -w "%{http_code}\n" http://localhost:5174/
```

```bash
curl http://localhost:5174/api/v1/health
```

That second one is important: nginx forwards `/api/*` to the API container, so
the browser only ever talks to one origin and CORS never applies.

---

## Step 6 — Stopping

**Stop but keep everything** (containers removed, database preserved):

```bash
docker compose down
```

**Pause without removing** (fastest to resume):

```bash
docker compose stop
```

```bash
docker compose start
```

**Destroy the database too** — the dangerous one:

```bash
docker compose down -v
```

The `-v` deletes the `pensieve-postgres-data` volume and every row in it.
Today that costs nothing because the database is empty. After Phase 6 it would
mean re-running the entire pipeline. **`down` without `-v` is always safe.**

---

## Where the data lives

Two different storage mechanisms, for two different reasons.

### Named volume — the database

```yaml
volumes:
  - postgres-data:/var/lib/postgresql/data
```

Docker manages this. It survives `docker compose down` and container rebuilds.
Inspect it:

```bash
docker volume ls --filter name=pensieve
```

```
pensieve-postgres-data
```

### Bind mount — the data layers

```yaml
volumes:
  - ./data:/app/data
```

This maps a real folder on your machine straight into the container:

```
C:\Users\...\pensieve\data  ->  /app/data
```

It is a live two-way window. Write a file on your host and the container sees
it instantly:

```bash
echo hello > data/samples/probe.txt
```

```bash
docker compose exec api cat /app/data/samples/probe.txt
```

**This is the bridge that makes the architecture work.** The pipeline runs
*outside* Docker for fast iteration, writing Parquet to `data/`; the API
running *inside* Docker reads that same Parquet with no copying, no syncing and
no rebuild.

---

## The Spark profile

A fourth service exists but does not start with `docker compose up`:

```yaml
spark-job:
  profiles: ['spark']
```

Confirm it is defined:

```bash
docker compose config --profiles
```

```
spark
```

**Why it is opt-in:** its image bundles a JDK 17, making it far larger than the
others. You should not pay that build cost unless you are actually running the
Gold aggregation stage.

**Why it exists at all:** PySpark 4.x requires Java 17 or newer. This machine
has Java 8, so Spark cannot run natively here. Putting the JDK in a container
sidesteps that entirely — and also avoids the `winutils.exe`/`HADOOP_HOME`
problem that Spark hits when writing files on Windows.

Run it explicitly:

```bash
docker compose --profile spark run --rm spark-job
```

`--rm` deletes the container when the job finishes — correct for a batch job
that runs once and exits, rather than a long-lived service.

> Not yet runnable: the job module it invokes arrives in Phase 5.

---

## Rebuilding after a code change

| You changed | Command |
|---|---|
| Python or TypeScript source | `docker compose up --build -d` |
| A dependency (`pyproject.toml` / `package.json`) | `docker compose build --no-cache <service>` |
| `.env` values | `docker compose up -d` (recreates with new env) |
| `docker-compose.yml` | `docker compose up -d` |

Rebuild just one service:

```bash
docker compose build api
```

Force a completely fresh build, ignoring all cached layers:

```bash
docker compose build --no-cache api
```

Only reach for `--no-cache` when you suspect the cache is stale — it discards
several minutes of work.

---

## Checking disk usage

Images accumulate. Every rebuild leaves the previous image untagged:

```bash
docker system df
```

```
TYPE          TOTAL   ACTIVE   SIZE      RECLAIMABLE
Images        7       4        2.837GB   1.607GB (56%)
Build Cache   75      0        2.123GB   2.123GB
```

Clear the untagged leftovers:

```bash
docker image prune -f
```

Clear the build cache:

```bash
docker builder prune -f
```

Both are safe: Docker refuses to delete an image that any container — even a
stopped one — still references.

> **Do not casually run `docker system prune -a`.** The `-a` flag also removes
> images not used by a *running* container. If your stack happened to be
> stopped, that deletes `pensieve-api`, `pensieve-web` and `postgres:16-alpine`
> and forces a full rebuild.

---

## The two ways to run this project

Docker is not the only mode, and it is not the best one for writing code.

### Docker mode — reproducible

```bash
docker compose up --build -d
```

Everything containerised. Your `.venv` and `node_modules` are ignored entirely.
Anyone with Docker can run it. **Dashboard on port 5174.**

### Dev mode — fast

```bash
docker compose up -d postgres
```

then, in the project root:

```bash
.\make.ps1 dev
```

Only PostgreSQL stays in Docker. The API runs from your `.venv` and the
frontend from your `node_modules`. **Dashboard on port 5173.**

**Why bother?** Hot reload. Saving a `.tsx` file updates the browser in about
50 ms and saving a `.py` file restarts uvicorn immediately. In Docker mode you
would rebuild an image — tens of seconds. PostgreSQL has no reason to reload,
so it stays containerised either way and you never install PostgreSQL on
Windows.

Both modes can run simultaneously; they use different ports and share the same
database.
