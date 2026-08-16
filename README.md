# Aahaar — Backend (FastAPI)

Multi-tenant **restaurant / cafe QR ordering** platform. Customers scan a QR,
browse a mobile-first menu, and place orders; restaurant staff receive them in
real time and drive them through the preparation lifecycle.

This is the **backend** service: a modular, layered FastAPI application with
PostgreSQL, async SQLAlchemy, Alembic migrations, JWT auth, and Socket.IO
realtime. The React frontend lives in `../aahaar-fe` (built in a later pass).

---

## Architecture

```
HTTP  ─▶  API Router  ─▶  Dependencies  ─▶  Service  ─▶  Repository  ─▶  SQLAlchemy  ─▶  PostgreSQL
                                              │
                                              └─▶  NotificationService  ─▶  Socket.IO  (after commit)
```

- **Routers** (`app/api`) — thin; HTTP concerns only.
- **Dependencies** (`app/dependencies`) — DB session, current user, tenant/restaurant
  resolution, role checks, rate limiting.
- **Services** (`app/services`) — business rules (auth, menu, orders, QR, notifications).
- **Repositories** (`app/repositories`) — database access only.
- **Models** (`app/models`) — SQLAlchemy 2.0 ORM.
- **Schemas** (`app/schemas`) — Pydantic request/response (camelCase on the wire).

PostgreSQL is the source of truth. Socket.IO is a notification layer only and is
emitted **after** a successful commit; clients always have a REST recovery path.

## Tech stack

Python 3.13 · FastAPI · SQLAlchemy 2.x (async / asyncpg) · Alembic · PostgreSQL ·
python-socketio · PyJWT · Argon2 · Pydantic v2.

## Project structure

```
aahaar-be/
├── app/
│   ├── main.py              # FastAPI + Socket.IO combined ASGI app
│   ├── core/                # config, database, security, errors, logging
│   ├── models/              # SQLAlchemy models + enums
│   ├── schemas/             # Pydantic request/response (camelCase)
│   ├── repositories/        # DB access
│   ├── services/            # business logic
│   ├── dependencies/        # DI: db, auth, tenant/restaurant, rate limit
│   ├── api/v1/              # routers: auth, restaurants, menu, public, orders, qr
│   ├── sockets/             # Socket.IO server + event handlers
│   ├── middleware/          # request-id / logging middleware
│   └── utils/               # slugs, QR image generation
├── migrations/              # Alembic (async env)
├── scripts/                 # seed.py, wait_for_db.py
├── Dockerfile · docker-compose.yml · entrypoint.sh
├── requirements.txt · requirements-dev.txt · Makefile · .env.example
```

---

## Quickstart — Docker (recommended)

```bash
docker compose up --build
```

This starts PostgreSQL and the API. The entrypoint waits for the DB, runs
`alembic upgrade head`, seeds demo data (`SEED_ON_START=true`), then serves on
**http://localhost:8001** (host **8001** because port 8000 is often used by another app).

- API docs (Swagger): http://localhost:8001/docs
- Health: http://localhost:8001/health
- Optional DB UI: `docker compose --profile tools up adminer` → http://localhost:8080

Tear down (keep data): `docker compose down` · wipe data: `docker compose down -v`.

## Quickstart — local (venv)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                 # then set DATABASE_URL + SECRET_KEY
alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload --port 8001
```

## Demo credentials (from the seed)

Restaurant slug: **`spice-garden`** · password for all: **`Password123!`**

| Email                  | Role      |
|------------------------|-----------|
| owner@aahaar.app       | OWNER     |
| reception@aahaar.app   | RECEPTION |
| kitchen@aahaar.app     | KITCHEN   |

---

## API overview  (base: `/api/v1`)

| Area | Endpoints |
|------|-----------|
| Auth | `POST /auth/register` · `POST /auth/login` · `POST /auth/refresh` · `POST /auth/logout` · `GET /auth/me` · `GET/POST /auth/staff` · `PATCH /auth/staff/{id}` |
| Restaurants | `GET/POST /restaurants` · `GET/PATCH/DELETE /restaurants/{id}` |
| Menu | `GET /restaurants/{id}/menu` · `POST /restaurants/{id}/categories` · `PATCH/DELETE /categories/{id}` · `POST /categories/{id}/items` · `PATCH/DELETE /menu-items/{id}` |
| Public | `GET /public/restaurants/{slug}` · `GET /public/restaurants/{slug}/menu` · `POST /public/customer-sessions` · `GET /public/customer-sessions/{id}` |
| Orders | `POST /orders` (`Idempotency-Key` header) · `GET /orders/{id}` · `GET /restaurants/{id}/orders` · `POST /orders/{id}/accept` · `POST /orders/{id}/reject` · `PATCH /orders/{id}/status` |
| QR | `POST /restaurants/{id}/qr` · `GET /restaurants/{id}/qr` |

Errors use a consistent envelope:

```json
{ "success": false, "error": { "code": "MENU_ITEM_UNAVAILABLE", "message": "..." } }
```

Order totals are **always** recalculated server-side; client-supplied prices are
never trusted. Order creation is transactional and supports `Idempotency-Key`.

### Order lifecycle

`PENDING → ACCEPTED → PREPARING → READY → SERVED → COMPLETED`
(plus `REJECTED` / `CANCELLED`). Invalid transitions are rejected.

## Realtime (Socket.IO, path `/socket.io`)

Rooms: `restaurant:{id}` (staff dashboard, JWT-verified) and `order:{id}` (customer).

| Event | Direction | When |
|-------|-----------|------|
| `order:created` | → restaurant | new order placed |
| `order:accepted` / `order:rejected` | → order | staff decision |
| `order:status_updated` | → order | status change |
| `order:updated` | → restaurant | dashboard list refresh signal |

Client join messages: `join_restaurant {restaurantId}` (auth required),
`join_order {orderId}`.

## Migrations

```bash
alembic revision --autogenerate -m "describe change"   # after editing models
alembic upgrade head
```

All schema changes go through Alembic (`migrations/`).

## Security

JWT access + rotating refresh tokens (hashed at rest) · Argon2 password hashing ·
role-based authorization (`OWNER/MANAGER/RECEPTION/KITCHEN`) · server-side tenant
isolation (never trust a client `tenant_id`) · rate limiting on login / order /
public endpoints · request-id logging.

---

## Roadmap

- **Pass 1 (done):** modular FastAPI, PostgreSQL, Alembic, auth, menu, QR, orders,
  realtime, Docker, seed. Verified end-to-end + in-container.
- **Pass 2:** React frontend (`../aahaar-fe`) — customer ordering app + staff
  dashboard, Food-First Neo-Brutalist design system.
