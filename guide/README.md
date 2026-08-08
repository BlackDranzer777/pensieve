# Pensieve — Docker Guide

A practical, step-by-step guide to the Docker setup for this project: how the
three containers are built, how to run them, and how to get inside them from a
plain command line.

Every command in these documents has been run against this project on Windows 11
with Docker 26.0.0. Nothing here is copied from generic tutorials — the outputs
shown are the real outputs from this machine.

---

## The documents

### Start here

| Document | What it covers |
|---|---|
| [architecture.md](architecture.md) | **What every script does to the data**, stage by stage, with diagrams and measured numbers. The map of the whole pipeline. |

### Docker

| Document | What it covers |
|---|---|
| [01-docker-setup.md](01-docker-setup.md) | Building the whole stack from zero: every file involved, every command, and what each one actually does |
| [02-accessing-containers.md](02-accessing-containers.md) | Getting inside each container from the command line — shells, one-off commands, logs, copying files |
| [03-command-reference.md](03-command-reference.md) | A one-page cheat sheet of the commands you will use daily |
| [04-troubleshooting.md](04-troubleshooting.md) | Real problems hit while building this, with the actual diagnosis and fix |

### Build phases

Each explains what the phase is for, how it depends on the one before, and what
it hands to the one after.

| Document | Phase |
|---|---|
| [phase2.md](phase2.md) | Synthetic data generation and ingestion into Bronze |
| [phase3.md](phase3.md) | Validation, quarantine, cleaning, deduplication, quality score |
| [phase4.md](phase4.md) | Language detection, sentiment, topic classification, Silver layer |
| [phase5.md](phase5.md) | DuckDB/PySpark aggregation, the Gold layer, statistical anomaly detection |
| [phase7.md](phase7.md) | The React dashboard — six pages against the API (written, unverified) |
| [phase6.md](phase6.md) | PostgreSQL schema, migrations, the loader and the REST API |

---

## 60-second version

Start everything:

```bash
docker compose up --build -d
```

Check it worked:

```bash
docker compose ps
```

You want three lines all saying `(healthy)`. Then open:

- Dashboard → <http://localhost:5174>
- API docs → <http://localhost:8000/docs>

Get inside a container:

```bash
docker compose exec api bash
```

Stop everything (your data survives):

```bash
docker compose down
```

---

## What is actually running

Three containers, each an isolated mini-machine:

| Container | Image | Contains | Host port |
|---|---|---|---|
| `pensieve-postgres` | `postgres:16-alpine` (294 MB) | PostgreSQL 16.14 | 5433 → 5432 |
| `pensieve-api` | `pensieve-api` (594 MB) | Python 3.12.13 + uvicorn + your code | 8000 → 8000 |
| `pensieve-web` | `pensieve-web` (49.8 MB) | nginx 1.27.5 + compiled JS/CSS | 5174 → 80 |

A fourth service, `spark-job`, exists but is behind an opt-in profile and is
**not built by default** — the Gold stage runs on DuckDB in-process, with no
JDK and no container. See
[01-docker-setup.md](01-docker-setup.md#the-spark-profile).

---

## The three words that matter

Most Docker confusion comes from these being used interchangeably. They are not
the same thing:

| Term | What it is | How many here |
|---|---|---|
| **Engine** | The background program running everything (Docker Desktop) | 1 |
| **Image** | An inert, read-only template on disk. Nothing runs in an image. | 3 |
| **Container** | A running instance created from an image | 3 |

An image is an installer; a container is the installed program actually
running. You can start ten containers from one image.

---

## A note on ports

Every container has its own private set of ports. The `5433 → 5432` notation
means "PostgreSQL listens on 5432 **inside** its container, and Docker forwards
your machine's port 5433 to it."

This has one consequence that catches everyone out:

- **From your machine**, reach the database at `localhost:5433`.
- **From another container**, reach it at `postgres:5432` — the service name and
  the *internal* port.

That is why `docker-compose.yml` sets the API's `DATABASE_URL` to
`...@postgres:5432/...` and not `localhost:5433`.
