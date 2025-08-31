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
	flake8 perfect_system.py
	black --check perfect_system.py
	isort --check-only perfect_system.py

format: ## Format code with black and isort
	black perfect_system.py
	isort perfect_system.py

test: ## Run tests (none - placeholder)
	@echo "No tests configured for perfect_system yet"

test-verbose: ## Run tests with verbose output
	@echo "No tests configured for perfect_system yet"

test-coverage: ## Run tests with coverage
	@echo "No coverage configured"

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
	python perfect_system.py

run-dev: ## Run in development mode with reload
	uvicorn perfect_system:app --reload --host 0.0.0.0 --port 8011

pre-commit-install: ## Install pre-commit hooks
	pre-commit install

pre-commit-run: ## Run pre-commit on all files
	pre-commit run --all-files




