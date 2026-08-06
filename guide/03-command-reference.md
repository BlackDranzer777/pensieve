# 03 — Command Reference

A one-page cheat sheet. Everything here has been run against this project.

---

## Daily driver

```bash
docker compose up -d              # start everything in the background
docker compose up --build -d      # rebuild changed images, then start
docker compose ps                 # what is running and is it healthy
docker compose logs -f api        # follow one service's logs
docker compose down               # stop and remove containers (DATA SURVIVES)
```

---

## Lifecycle

| Command | Effect | Data? |
|---|---|---|
| `docker compose up -d` | Create and start | — |
| `docker compose stop` | Pause; containers remain | kept |
| `docker compose start` | Resume paused containers | kept |
| `docker compose restart api` | Restart one service | kept |
| `docker compose down` | Stop and **remove** containers | **kept** |
| `docker compose down -v` | Also delete volumes | **DESTROYED** |

**The only destructive one is `down -v`.** That `-v` removes
`pensieve-postgres-data` and every row in it.

---

## Building

```bash
docker compose build                    # build all images
docker compose build api                # build one
docker compose build --no-cache api     # ignore cached layers (slow, thorough)
docker compose config --quiet           # validate the compose file
docker compose config --services        # list defined services
docker compose config --profiles        # list profiles (here: spark)
```

---

## Getting inside

```bash
docker compose exec api bash                                    # API shell (has bash)
docker compose exec web sh                                      # web shell (Alpine: sh only)
docker compose exec postgres psql -U pensieve -d pensieve       # database client
docker compose exec api python --version                        # one-off command
docker compose exec -T api python --version                     # same, safe in scripts
```

From outside the project folder, use container names and add `-it`:

```bash
docker exec -it pensieve-api bash
docker exec -it pensieve-postgres psql -U pensieve -d pensieve
```

---

## Logs

```bash
docker compose logs               # everything, once
docker compose logs -f            # follow live
docker compose logs -f api        # one service
docker compose logs --tail 50 api # last 50 lines
docker compose logs -t api        # with timestamps
docker compose logs --since 10m   # last 10 minutes
```

---

## Inspecting

```bash
docker compose top api                    # processes inside
docker stats --no-stream                  # CPU and memory snapshot
docker compose port api 8000              # which host port maps here
docker inspect pensieve-api               # full JSON config
docker inspect pensieve-api --format "{{.State.Health.Status}}"
docker inspect pensieve-api --format "{{.Config.Image}}"
docker network ls --filter name=pensieve
docker volume ls --filter name=pensieve
```

Why a healthcheck is failing:

```bash
docker inspect pensieve-web --format "{{range .State.Health.Log}}{{.ExitCode}} {{.Output}}{{end}}"
```

---

## Containers and images

```bash
docker ps                                  # RUNNING containers only
docker ps -a                               # ALL, including stopped
docker image ls                            # all images
docker image ls --filter dangling=true     # untagged leftovers
```

**`docker ps` vs `docker ps -a` is the single most common Docker confusion.**
A container that exited two years ago still appears in `-a` and still pins its
image, blocking deletion.

Which containers use a given image:

```bash
docker ps -a --filter ancestor=postgres:16-alpine
```

Which image a container came from:

```bash
docker inspect pensieve-postgres --format "{{.Config.Image}}"
```

Everything as a table:

```bash
docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
```

---

## Deleting — in the required order

The order is enforced: an image cannot be removed while any container, even a
stopped one, references it.

```bash
docker stop <container>     # 1. running -> stopped
docker rm <container>       # 2. stopped -> gone
docker rmi <image>          # 3. now the image can go
```

Bulk cleanup:

```bash
docker image prune -f       # untagged <none> images     -- safe
docker builder prune -f     # build cache                -- safe
docker container prune -f   # all stopped containers     -- safe
docker system df            # what is using disk
```

> **`docker system prune -a` — handle with care.** Plain `prune` removes only
> dangling junk. Adding `-a` also deletes images not used by a *running*
> container, which would remove `pensieve-api`, `pensieve-web` and
> `postgres:16-alpine` if the stack happened to be stopped.

---

## Database

Open a session:

```bash
docker compose exec postgres psql -U pensieve -d pensieve
```

Inside psql:

```
\l          list databases        \du   list users
\dt         list tables           \dn   list schemas
\d <table>  describe a table      \x    expanded output
\dt+        tables with sizes     \q    quit
```

One-off queries from your shell:

```bash
docker compose exec postgres psql -U pensieve -d pensieve -c "\dt"
docker compose exec postgres psql -U pensieve -d pensieve -tAc "SELECT version();"
```

Backup and restore:

```bash
docker compose exec postgres pg_dump -U pensieve pensieve > backup.sql
docker compose exec -T postgres psql -U pensieve -d pensieve < backup.sql
```

Connection details for a GUI (DBeaver, pgAdmin, TablePlus):

```
Host: localhost   Port: 5433   Database: pensieve
User: pensieve    Password: pensieve_local_dev
```

---

## Files

```bash
docker cp pensieve-api:/app/pyproject.toml ./copy.toml     # out
docker cp ./data.csv pensieve-api:/app/data/samples/       # in
```

`docker cp` always takes the **container** name, never the service name.
For anything under `data/`, you do not need this — that folder is bind-mounted
and already shared.

---

## Endpoint checks

```bash
curl http://localhost:8000/api/v1/health          # API directly
curl http://localhost:5174/api/v1/health          # through nginx
curl http://localhost:5174/                       # dashboard
curl http://localhost:8000/docs                   # OpenAPI UI
```

Between containers, address by **service name and internal port**:

```bash
docker compose exec web wget -qO- http://api:8000/api/v1/health
```

---

## Ports

| Service | Host | Container | Why |
|---|---|---|---|
| web | 5174 | 80 | nginx serves the built dashboard |
| api | 8000 | 8000 | uvicorn |
| postgres | **5433** | 5432 | 5433 avoids clashing with a native PostgreSQL |

From your machine → `localhost:5433`.
From another container → `postgres:5432`.

---

## Windows notes

| Problem | Fix |
|---|---|
| `the input device is not a TTY` (Git Bash) | Use PowerShell, or prefix `winpty` |
| Container path becomes `C:/Program Files/Git/app/...` | Use `//app/...` or set `MSYS_NO_PATHCONV=1` |
| `bash: executable file not found` on web | Alpine has no bash — use `sh` |
| `error during connect` | Docker Desktop is not running |

---

## The Spark profile

```bash
docker compose config --profiles                          # -> spark
docker compose --profile spark run --rm spark-job         # run the Gold stage
```

Not started by `docker compose up` — the image bundles a JDK 17 and should only
be built when actually needed. `--rm` removes the container when the batch job
exits.
