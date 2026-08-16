.PHONY: help install dev migrate revision seed up down logs test lint fmt codecheck preparepush

help:
	@echo "install      Install runtime + dev deps into the active venv"
	@echo "dev          Run the API locally with reload"
	@echo "migrate      Apply Alembic migrations (alembic upgrade head)"
	@echo "revision     Autogenerate a migration: make revision m='message'"
	@echo "seed         Seed demo data"
	@echo "up           docker compose up --build"
	@echo "down         docker compose down"
	@echo "logs         Tail the api container logs"
	@echo "test         Run pytest"
	@echo "fmt          Auto-fix Ruff lint and format"
	@echo "lint         Check lint, format, and compile (CI)"
	@echo "codecheck    Alias for lint"
	@echo "preparepush  Format/fix then verify — run before git push"

install:
	pip install -r requirements-dev.txt

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8001

migrate:
	alembic upgrade head

revision:
	alembic revision --autogenerate -m "$(m)"

seed:
	python -m scripts.seed

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f api

test:
	pytest -q

lint:
	ruff check app scripts migrations/env.py
	ruff format --check app scripts migrations/env.py
	python -m compileall -q app scripts

codecheck: lint

fmt:
	ruff check --fix app scripts migrations/env.py
	ruff format app scripts migrations/env.py

preparepush: fmt lint
