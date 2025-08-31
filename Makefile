.PHONY: help install dev-install lint format test test-verbose clean docker-build docker-run docker-stop logs

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install production dependencies
	pip install -r requirements.txt

dev-install: ## Install development dependencies
	pip install -r requirements.txt
	pip install -e .[dev]

lint: ## Run linting checks
	flake8 main.py fill_placeholders.py tests/
	black --check main.py fill_placeholders.py tests/
	isort --check-only main.py fill_placeholders.py tests/

format: ## Format code with black and isort
	black main.py fill_placeholders.py tests/
	isort main.py fill_placeholders.py tests/

test: ## Run tests
	pytest tests/ -v

test-verbose: ## Run tests with verbose output
	pytest tests/ -vv --tb=long

test-coverage: ## Run tests with coverage
	pytest tests/ --cov=main --cov=fill_placeholders --cov-report=html --cov-report=term

clean: ## Clean up generated files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	rm -rf build/ dist/ htmlcov/ .coverage
	rm -f logs/*.log

docker-build: ## Build Docker image
	docker-compose build

docker-run: ## Run with Docker Compose
	docker-compose up -d

docker-stop: ## Stop Docker containers
	docker-compose down

docker-logs: ## Show Docker logs
	docker-compose logs -f

run: ## Run the application locally
	python main.py

run-dev: ## Run in development mode with reload
	uvicorn main:app --reload --host 0.0.0.0 --port 8000

pre-commit-install: ## Install pre-commit hooks
	pre-commit install

pre-commit-run: ## Run pre-commit on all files
	pre-commit run --all-files




