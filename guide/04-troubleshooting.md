# 04 — Troubleshooting

Real problems hit while building this project, with the actual diagnosis and
fix. These are not hypothetical — each one cost time here.

---

## Container says "unhealthy" but the site works fine

**Symptom.** `docker compose ps` reported `pensieve-web ... (unhealthy)`, yet
`curl http://localhost:5174/` returned 200 and the dashboard loaded normally.

**Diagnosis.** Read the probe output rather than guessing:

```bash
docker inspect pensieve-web --format "{{range .State.Health.Log}}{{.ExitCode}} {{.Output}}{{end}}"
```

```
exit=1  wget: can't connect to remote host: Connection refused
```

The probe genuinely could not connect. Testing from inside narrowed it down:

```bash
docker compose exec web sh -c "wget -q --spider http://localhost/ ; echo $?"   # 1
docker compose exec web sh -c "wget -q --spider http://127.0.0.1/ ; echo $?"   # 0
```

`localhost` failed; `127.0.0.1` worked. The cause:

```bash
docker compose exec web cat /etc/hosts | grep localhost
```

```
127.0.0.1   localhost
::1         localhost ip6-localhost ip6-loopback
```

`localhost` resolves to **both** IPv4 and IPv6. BusyBox `wget` tries `::1`
first and does not fall back — and nginx listens only on IPv4 (`0.0.0.0:80`).

**Fix.** Use the literal address in the healthcheck:

```dockerfile
HEALTHCHECK CMD wget --quiet --tries=1 --spider http://127.0.0.1/ || exit 1
```

**Why it matters beyond cosmetics.** Anything with
`depends_on: condition: service_healthy` waits forever on a container that is
serving perfectly. In production it pages someone at 3 a.m. for nothing.

---

## Port is already allocated

**Symptom.**

```
Error: bind: Only one usage of each socket address is normally permitted
```

**Diagnosis.** Something else already owns that host port:

```powershell
netstat -ano | findstr :5433
```

**Fix.** Change the host side in `.env` — never the container side:

```
POSTGRES_PORT=5434
```

Then `docker compose up -d`. Ports map as `HOST:CONTAINER`; only the left
number is yours to change. This is exactly why the project defaults to 5433
rather than PostgreSQL's usual 5432.

---

## `bash: executable file not found`

**Symptom.**

```
OCI runtime exec failed: exec: "bash": executable file not found in $PATH
```

**Cause.** Alpine-based images ship BusyBox `sh`, not `bash`, to stay small.
`pensieve-web` is `nginx:1.27-alpine`; `pensieve-api` is Debian-based and does
have bash.

**Fix.**

```bash
docker compose exec web sh
```

Rule of thumb: if the image tag contains `alpine`, use `sh`.

---

## `the input device is not a TTY` (Git Bash)

**Cause.** Git Bash on Windows does not expose a real Windows console TTY, so
`-it` cannot allocate one.

**Fixes**, in order of preference:

1. Use **PowerShell** or **cmd**
2. `winpty docker exec -it pensieve-api bash`
3. Drop `-it` if you do not need interactivity

---

## Container path becomes `C:/Program Files/Git/...`

**Symptom.**

```bash
docker exec pensieve-api cat /app/pyproject.toml
```
```
cat: 'C:/Program Files/Git/app/pyproject.toml': No such file or directory
```

**Cause.** Git Bash rewrites anything that looks like a Unix path into a
Windows path before Docker sees it. The container never received `/app/...`.

**Fixes.** Leading double slash:

```bash
docker exec pensieve-api cat //app/pyproject.toml
```

Or disable conversion for that command:

```bash
MSYS_NO_PATHCONV=1 docker exec pensieve-api cat /app/pyproject.toml
```

Neither is needed in PowerShell.

---

## `WinError 32` during a pipeline run

**Symptom.**

```
PermissionError: [WinError 32] The process cannot access the file
because it is being used by another process
```

**Cause.** This repository sits inside **OneDrive**. When the pipeline writes
Parquet, OneDrive's sync engine opens the same files to upload them, and
Windows refuses the concurrent access. A pipeline writing many small files is
close to a worst case.

It looks exactly like a pipeline bug, so the instinct is to debug the code.

**Fixes**, in order of preference:

1. Move the repository outside OneDrive (e.g. `C:\dev\pensieve`)
2. Keep the repo where it is and move only the heavy folders out, using
   directory junctions — OneDrive skips reparse points:

```powershell
New-Item -ItemType Junction -Path .\data -Target C:\dev\pensieve-local\data
```

3. Exclude `data/`, `.venv/` and `node_modules/` via OneDrive settings →
   *Sync and backup* → *Advanced* → *Choose folders*

The model cache is already handled — `HF_HOME` in `.env.example` points outside
OneDrive by default.

Confirm whether this applies to you:

```bash
python scripts/check_env.py
```

It warns when the repository is inside a synced folder.

---

## Build is extremely slow

**Cause.** Docker uploads a copy of the project (the "build context") to the
engine before building. Without `.dockerignore` that includes `node_modules`
(173 MB, 22,186 files) and `.venv` (866 MB, 17,844 files) on **every build**.

**Fix.** Confirm `.dockerignore` exists at the repository root and excludes:

```
**/node_modules
**/.venv
data/bronze
data/silver
data/gold
data/quarantine
```

Watch the first build line — `transferring context` should be a few MB, not
hundreds.

---

## Disk filling up

**Cause.** Every rebuild moves the `:latest` tag to the new image and leaves
the previous one untagged. Three rebuilds here produced three `<none>` images
totalling 1.6 GB, plus 2.1 GB of build cache.

**Diagnosis.**

```bash
docker system df
```

**Fix.**

```bash
docker image prune -f
```

```bash
docker builder prune -f
```

Both are safe — Docker refuses to remove an image any container still
references.

> Avoid `docker system prune -a` unless you mean it: `-a` also removes images
> not used by a *running* container, which would delete your project images if
> the stack were stopped.

---

## API cannot reach the database

**Symptom.** `/api/v1/health` returns `"status":"degraded"` with
`"database":"unavailable"`.

**Check the database is actually healthy first:**

```bash
docker compose ps postgres
```

**Then check the address.** Inside the Docker network, containers reach each
other by **service name and internal port**:

```
postgresql+psycopg://pensieve:...@postgres:5432/pensieve     correct
postgresql+psycopg://pensieve:...@localhost:5433/pensieve    wrong from a container
```

`localhost` inside a container means *that container*, not your machine and not
another container. The compose file overrides `DATABASE_URL` accordingly.

Test connectivity from inside the API container:

```bash
docker compose exec api python -c "import socket; socket.create_connection(('postgres', 5432), 5); print('reachable')"
```

**Note:** the health endpoint reports the outage rather than hanging, because
the engine sets an explicit `connect_timeout`. Without one, psycopg blocks
indefinitely against a host that silently drops packets — and the endpoint
meant to *detect* the outage becomes the thing that hangs.

---

## Changes to code are not showing up

**Cause.** Images are built once and contain a **copy** of your source. Editing
a file on your host does not change an already-built image.

**Fix — rebuild:**

```bash
docker compose up --build -d
```

**Better fix for active development — use dev mode instead**, where the API and
frontend run natively with hot reload:

```bash
docker compose up -d postgres
```

```powershell
.\make.ps1 dev
```

Dashboard on **5173** with instant reload, versus 5174 for the Docker copy.

The exception is `data/` — it is bind-mounted, so files written there on your
host appear in the container immediately without any rebuild.

---

## Docker commands fail entirely

**Symptom.**

```
error during connect: ... The system cannot find the file specified
```

**Cause.** The Docker engine is not running. The CLI is installed, the daemon
is not up.

**Fix.** Start Docker Desktop and wait ~30 seconds. Confirm:

```bash
docker version
```

A `Server:` section means the daemon is up. If only `Client:` appears, it is
still starting.

---

## Database seems empty

**Symptom.** `\dt` says *"Did not find any relations."*

**This is correct as of Phase 1.** The SQLAlchemy models and Alembic migrations
that create the nine tables arrive in Phase 6.

Prove the server is healthy and merely unpopulated:

```sql
SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname = 'pg_catalog';
```

Dozens of internal catalog tables exist. Your `public` schema is simply bare.

Also check you are connected to the right database — the prompt tells you:

```
pensieve=#
```

The name before `=#` is your current database. If it says `postgres=#` you are
in the default landing database, which will always be empty.

---

## General debugging order

When something is wrong, work outward in this order:

1. **Is it running?** — `docker compose ps`
2. **What did it say?** — `docker compose logs --tail 50 <service>`
3. **Why is the probe failing?** — `docker inspect <container> --format "{{range .State.Health.Log}}{{.Output}}{{end}}"`
4. **Can I reproduce it inside?** — `docker compose exec <service> sh`
5. **Is it a networking problem?** — try the service name, not `localhost`
6. **Is it a stale image?** — `docker compose up --build -d`

Step 2 solves most problems. A container that starts and immediately dies
cannot be `exec`'d into, so the logs are the only evidence you have.
