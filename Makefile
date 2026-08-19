.PHONY: help install dev migrate revision seed up down logs test lint fmt codecheck preparepush

help:
	@echo "install      Install runtime + dev deps into the active venv"
	@echo "dev          Run the API locally with reload"
	@echo "migrate      Apply SQL files in supabase/migrations"
	@echo "revision     Create an empty SQL migration: make revision m='message'"
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
	python -m scripts.apply_migrations

revision:
	@test -n "$(m)" || (echo 'usage: make revision m="describe_change"' && exit 1)
	supabase migration new "$(m)"

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
	ruff check app scripts
	ruff format --check app scripts
	python -m compileall -q app scripts

codecheck: lint

fmt:
	ruff check --fix app scripts
	ruff format app scripts

preparepush: fmt lint
