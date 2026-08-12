.PHONY: docker-build docker-up docker-down docker-test docker-smoke docker-sse test

docker-build:
	docker build -t tooltrust:latest .

docker-up:
	docker compose up --detach --wait

docker-down:
	docker compose down

docker-smoke:
	uv run pytest tests/test_docker_smoke.py -v

docker-sse:
	uv run pytest tests/test_sse_integration.py -v

docker-test: docker-smoke docker-sse

test:
	uv run pytest --tb=short

fmt:
	ruff check --fix .
	ruff check .

typecheck:
	mypy --strict src/