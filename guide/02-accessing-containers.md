# 02 — Accessing the Containers from the Command Line

How to get inside each container, run one-off commands, read logs, and move
files across the boundary.

---

## Two ways to name a container

Every command below works in one of two forms, and mixing them up is the most
common source of *"No such container"*.

**Compose form** — uses the **service** name from `docker-compose.yml`
(`api`, `web`, `postgres`). Must be run from the project directory:

```bash
docker compose exec api bash
```

**Plain Docker form** — uses the **container** name (`pensieve-api`,
`pensieve-web`, `pensieve-postgres`). Works from anywhere on your machine:

```bash
docker exec -it pensieve-api bash
```

| | Compose form | Plain form |
|---|---|---|
| Name used | `api` | `pensieve-api` |
| Run from | project folder only | anywhere |
| Needs `-it`? | no, it is implied | **yes**, for interactive shells |

Use the compose form while working in the project; the plain form from a random
terminal.

---

## Getting a shell

### The API container — has `bash`

```bash
docker compose exec api bash
```

You land in `/app` as user `pensieve` (uid 1001, non-root). Try:

```bash
ls
```

```bash
python --version
```

That prints **Python 3.12.13** — not your host's 3.12.0. Proof that the
container has its own completely separate Python installation and does not use
your `.venv`.

Type `exit` to leave. The container keeps running.

### The web container — `sh` only, no `bash`

```bash
docker compose exec web sh
```

Using `bash` here fails:

```
OCI runtime exec failed: exec: "bash": executable file not found in $PATH
```

That is not a broken container. It is Alpine Linux, which ships BusyBox `sh`
instead of `bash` to stay small. **Alpine-based images generally need `sh`.**

Once inside, see what the frontend actually is:

```bash
ls /usr/share/nginx/html
```

```
50x.html   assets   index.html
```

Three compiled files and no source. That is the entire frontend in production.

### The database container — go straight into psql

You *can* get a shell, but there is rarely a reason to. Go directly to the
database client:

```bash
docker compose exec postgres psql -U pensieve -d pensieve
```

You get a `pensieve=#` prompt. **Whatever appears before `=#` is the database
you are connected to** — the quickest way to confirm you are in the right one.

No password is needed: connections originating inside the container are
trusted.

---

## Working inside psql

These backslash commands are psql's own, not SQL:

```
\l          list all databases
\dt         list tables in the current database
\d <table>  describe one table's columns
\dn         list schemas
\du         list users and roles
\dt+        tables with sizes
\x          toggle expanded rows (good for wide results)
\?          help on backslash commands
\q          quit
```

Confirm where you are:

```sql
SELECT current_database(), current_user, inet_server_port();
```

```
 pensieve | pensieve | 5432
```

Note **5432** — the port *inside* the container. Your host reaches it on 5433
through the port mapping.

> **Every SQL statement needs a trailing semicolon.** Without one the prompt
> changes to `pensieve-#` and appears to hang. It is simply waiting for you to
> finish the statement. Type `;` and press Enter.

### What you will see today

```sql
\dt
```

```
Did not find any relations.
```

That is correct, not an error — the tables arrive in Phase 6. To prove the
server is healthy and merely empty:

```sql
SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname = 'pg_catalog';
```

Dozens of internal catalog tables exist. Your `public` schema is simply bare.

### The four databases

`\l` shows four. Only one is yours:

| Database | What it is |
|---|---|
| **`pensieve`** | **Yours** — created from `POSTGRES_DB`. The 9 tables will live here. |
| `postgres` | Default landing database every PostgreSQL install creates. Some tools connect here before knowing which database they want. Harmless, ~7.5 MB. |
| `template0` | Pristine read-only master template. Never modify. |
| `template1` | The template copied by `CREATE DATABASE`. Leave alone. |

---

## Running one-off commands (no shell)

Append the command instead of a shell name. Useful in scripts, and it returns
you straight to your own prompt.

Check the API's Python version:

```bash
docker compose exec api python --version
```

List tables without entering psql — `-c` runs one command and exits:

```bash
docker compose exec postgres psql -U pensieve -d pensieve -c "\dt"
```

Machine-readable output — `-t` drops headers, `-A` drops padding:

```bash
docker compose exec postgres psql -U pensieve -d pensieve -tAc "SELECT version();"
```

Check nginx's config is valid:

```bash
docker compose exec web nginx -t
```

> **In scripts**, add `-T` to disable TTY allocation:
> `docker compose exec -T api python --version`. Without it, commands can fail
> in CI or when output is piped.

---

## Reading logs

Logs are how you diagnose a container that starts and then dies — you cannot
`exec` into something that is not running.

Everything, live:

```bash
docker compose logs -f
```

One service only:

```bash
docker compose logs -f api
```

Last 50 lines, no follow:

```bash
docker compose logs --tail 50 api
```

With timestamps:

```bash
docker compose logs -t api
```

Since a point in time:

```bash
docker compose logs --since 10m api
```

`Ctrl+C` stops following. It does **not** stop the container.

A real line from this project's API — structured JSON, as configured:

```
pensieve-api | 2026-08-06 00:32:43 [info] http_request [app.main]
               duration_ms=2.11 method=GET path=/api/v1/health status_code=200
```

---

## Moving files across the boundary

**Out of a container:**

```bash
docker cp pensieve-api:/app/pyproject.toml ./copy.toml
```

**Into a container:**

```bash
docker cp ./somefile.csv pensieve-api:/app/data/samples/
```

`docker cp` always uses the **container** name, never the compose service name.

For `data/` you rarely need this — that folder is bind-mounted, so files
written on your host appear in the container instantly. `docker cp` is for
paths *outside* the mounted folder.

---

## Inspecting a running container

Processes inside it:

```bash
docker compose top api
```

```
UID    PID    CMD
1001   8263   /opt/venv/bin/python /opt/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Live CPU and memory for everything:

```bash
docker stats --no-stream
```

Real numbers from this project at idle:

```
pensieve-web         0.00%   12.78 MiB
pensieve-api         0.37%   63.28 MiB
pensieve-postgres    0.01%   40.85 MiB
```

Under 120 MB for the entire stack.

Which host port maps to a container port:

```bash
docker compose port api 8000
```

```
0.0.0.0:8000
```

Full configuration as JSON:

```bash
docker inspect pensieve-api
```

That is a wall of output; pull out one field with `--format`:

```bash
docker inspect pensieve-api --format "{{.State.Health.Status}}"
```

```bash
docker inspect pensieve-api --format "{{.Config.Image}}"
```

Why a healthcheck is failing — the last few probe results:

```bash
docker inspect pensieve-web --format "{{range .State.Health.Log}}{{.ExitCode}} {{.Output}}{{end}}"
```

---

## Talking to the API without a browser

From your host:

```bash
curl http://localhost:8000/api/v1/health
```

Through nginx's proxy, exactly as the browser does:

```bash
curl http://localhost:5174/api/v1/health
```

From **inside** the web container, using the internal network:

```bash
docker compose exec web wget -qO- http://api:8000/api/v1/health
```

That last one is worth understanding. Inside the Docker network, containers
address each other by **service name and internal port** — `api:8000`, not
`localhost:8000`. Each container's `localhost` refers to itself alone.

See the private network and addresses:

```bash
docker network ls --filter name=pensieve
```

```bash
docker inspect pensieve-api --format "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"
```

```
172.18.0.3
```

---

## Two Windows-specific gotchas

### `-it` fails in Git Bash

```
the input device is not a TTY
```

Git Bash does not provide a Windows console TTY. Fixes, in order of preference:

1. Use **PowerShell** or **cmd** instead
2. Prefix with `winpty`: `winpty docker exec -it pensieve-api bash`
3. Drop `-it` if you do not need interactivity

### Git Bash mangles container paths

Git Bash rewrites `/app/data` into `C:/Program Files/Git/app/data` before Docker
ever sees it, producing a baffling "No such file" error. Either use a leading
double slash:

```bash
docker exec pensieve-api cat //app/pyproject.toml
```

or disable the conversion:

```bash
MSYS_NO_PATHCONV=1 docker exec pensieve-api cat /app/pyproject.toml
```

Neither is needed in PowerShell or cmd.

---

## Quick reference

| Goal | Command |
|---|---|
| Shell into the API | `docker compose exec api bash` |
| Shell into the web container | `docker compose exec web sh` |
| Open the database | `docker compose exec postgres psql -U pensieve -d pensieve` |
| One-off command | `docker compose exec api python --version` |
| Follow logs | `docker compose logs -f api` |
| Copy a file out | `docker cp pensieve-api:/app/file .` |
| Resource usage | `docker stats --no-stream` |
| Processes inside | `docker compose top api` |
| Health status | `docker inspect pensieve-api --format "{{.State.Health.Status}}"` |
