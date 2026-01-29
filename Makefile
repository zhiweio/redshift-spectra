# =============================================================================
# Redshift Spectra - Makefile
# =============================================================================
# Build, test, and deployment automation using UV package manager
# =============================================================================

.PHONY: help install install-dev clean lint format type-check test test-unit \
        test-integration test-cov build package deploy-dev deploy-prod \
        docs docs-serve tf-init tf-plan tf-apply tf-destroy

# Default shell
SHELL := /bin/bash

# Project settings
PROJECT_NAME := redshift-spectra
PYTHON_VERSION := 3.11
SRC_DIR := src/spectra
TESTS_DIR := tests
LAMBDA_DIR := dist/lambda
DOCS_DIR := docs

# Terraform settings
TF_DIR := terraform
TF_VARS_DEV := -var-file=environments/dev.tfvars
TF_VARS_PROD := -var-file=environments/prod.tfvars

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m  # No Color

# =============================================================================
# Help
# =============================================================================

help:  ## Show this help message
	@echo -e "$(BLUE)Redshift Spectra - Development Commands$(NC)"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

# =============================================================================
# Environment Setup
# =============================================================================

install:  ## Install production dependencies with uv
	@echo -e "$(BLUE)Installing production dependencies...$(NC)"
	uv sync --no-dev

install-dev:  ## Install all dependencies including dev tools
	@echo -e "$(BLUE)Installing all dependencies...$(NC)"
	uv sync
	uv run pre-commit install

upgrade:  ## Upgrade all dependencies
	@echo -e "$(BLUE)Upgrading dependencies...$(NC)"
	uv lock --upgrade
	uv sync

clean:  ## Clean build artifacts and caches
	@echo -e "$(YELLOW)Cleaning build artifacts...$(NC)"
	rm -rf dist/ build/ *.egg-info .pytest_cache .mypy_cache .ruff_cache
	rm -rf .coverage htmlcov/ coverage.xml
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# =============================================================================
# Code Quality
# =============================================================================

lint:  ## Run linting with ruff
	@echo -e "$(BLUE)Running ruff linter...$(NC)"
	uv run ruff check $(SRC_DIR) $(TESTS_DIR)

lint-fix:  ## Fix linting issues automatically
	@echo -e "$(BLUE)Fixing lint issues...$(NC)"
	uv run ruff check --fix $(SRC_DIR) $(TESTS_DIR)

format:  ## Format code with ruff
	@echo -e "$(BLUE)Formatting code...$(NC)"
	uv run ruff format $(SRC_DIR) $(TESTS_DIR)

format-check:  ## Check code formatting
	@echo -e "$(BLUE)Checking code format...$(NC)"
	uv run ruff format --check $(SRC_DIR) $(TESTS_DIR)

type-check:  ## Run type checking with mypy
	@echo -e "$(BLUE)Running type checks...$(NC)"
	uv run mypy $(SRC_DIR)

check-all: lint format-check type-check  ## Run all code quality checks

# =============================================================================
# Testing
# =============================================================================

test:  ## Run all tests
	@echo -e "$(BLUE)Running all tests...$(NC)"
	uv run pytest $(TESTS_DIR)

test-unit:  ## Run unit tests only
	@echo -e "$(BLUE)Running unit tests...$(NC)"
	uv run pytest $(TESTS_DIR) -m unit

test-integration:  ## Run integration tests only
	@echo -e "$(BLUE)Running integration tests...$(NC)"
	uv run pytest $(TESTS_DIR) -m integration

test-cov:  ## Run tests with coverage report
	@echo -e "$(BLUE)Running tests with coverage...$(NC)"
	uv run pytest $(TESTS_DIR) --cov=$(SRC_DIR) --cov-report=html --cov-report=xml

test-watch:  ## Run tests in watch mode
	@echo -e "$(BLUE)Running tests in watch mode...$(NC)"
	uv run pytest-watch $(TESTS_DIR)

# =============================================================================
# Build & Package
# =============================================================================

build:  ## Build Python package
	@echo -e "$(BLUE)Building package...$(NC)"
	uv build

# Generate requirements.txt from pyproject.toml dynamically
requirements.txt: pyproject.toml  ## Generate requirements.txt from pyproject.toml
	@echo -e "$(BLUE)Generating requirements.txt from pyproject.toml...$(NC)"
	uv export --no-hashes --no-dev --no-emit-project > requirements.txt
	@echo -e "$(GREEN)Generated requirements.txt$(NC)"

requirements-dev.txt: pyproject.toml  ## Generate dev requirements.txt from pyproject.toml
	@echo -e "$(BLUE)Generating requirements-dev.txt from pyproject.toml...$(NC)"
	uv export --no-hashes --no-emit-project > requirements-dev.txt
	@echo -e "$(GREEN)Generated requirements-dev.txt$(NC)"

# =============================================================================
# Lambda Layer (Shared Dependencies)
# =============================================================================

package-layer: requirements.txt  ## Create Lambda layer with shared dependencies
	@echo -e "$(BLUE)Creating Lambda layer with shared dependencies...$(NC)"
	@rm -rf $(LAMBDA_DIR)/layer
	@mkdir -p $(LAMBDA_DIR)/layer/python
	
	# Install dependencies for Amazon Linux 2 (Lambda runtime)
	@echo -e "$(GREEN)Installing dependencies for Lambda runtime...$(NC)"
	pip install \
		--platform manylinux2014_x86_64 \
		--implementation cp \
		--python-version 3.11 \
		--only-binary=:all: \
		--target $(LAMBDA_DIR)/layer/python \
		-r requirements.txt \
		--quiet || pip install -r requirements.txt -t $(LAMBDA_DIR)/layer/python --quiet
	
	# Remove unnecessary files to reduce layer size
	@echo -e "$(GREEN)Optimizing layer size...$(NC)"
	@find $(LAMBDA_DIR)/layer -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find $(LAMBDA_DIR)/layer -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
	@find $(LAMBDA_DIR)/layer -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find $(LAMBDA_DIR)/layer -type f -name "*.pyc" -delete 2>/dev/null || true
	@find $(LAMBDA_DIR)/layer -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
	@find $(LAMBDA_DIR)/layer -type d -name "test" -exec rm -rf {} + 2>/dev/null || true
	
	# Create layer zip
	cd $(LAMBDA_DIR)/layer && zip -r ../layer.zip . -x "*.pyc" -x "__pycache__/*" -x "*.dist-info/*"
	
	# Show layer size
	@echo -e "$(GREEN)Lambda layer created: $(LAMBDA_DIR)/layer.zip$(NC)"
	@ls -lh $(LAMBDA_DIR)/layer.zip | awk '{print "Layer size: " $$5}'

# =============================================================================
# Lambda Function Packages (Code Only - No Dependencies)
# =============================================================================

package-lambda: package-layer  ## Package Lambda functions (code only, uses layer for deps)
	@echo -e "$(BLUE)Packaging Lambda functions (code only)...$(NC)"
	@mkdir -p $(LAMBDA_DIR)
	
	# Clean previous builds
	@rm -rf $(LAMBDA_DIR)/api-handler $(LAMBDA_DIR)/worker $(LAMBDA_DIR)/authorizer
	
	# Create API handler package (code only)
	@echo -e "$(GREEN)Creating API handler package...$(NC)"
	@mkdir -p $(LAMBDA_DIR)/api-handler
	cp -r $(SRC_DIR) $(LAMBDA_DIR)/api-handler/spectra
	cd $(LAMBDA_DIR)/api-handler && zip -r ../api-handler.zip . -x "*.pyc" -x "__pycache__/*"
	
	# Create Worker package (code only)
	@echo -e "$(GREEN)Creating worker package...$(NC)"
	@mkdir -p $(LAMBDA_DIR)/worker
	cp -r $(SRC_DIR) $(LAMBDA_DIR)/worker/spectra
	cd $(LAMBDA_DIR)/worker && zip -r ../worker.zip . -x "*.pyc" -x "__pycache__/*"
	
	# Create Authorizer package (code only)
	@echo -e "$(GREEN)Creating authorizer package...$(NC)"
	@mkdir -p $(LAMBDA_DIR)/authorizer
	cp -r $(SRC_DIR) $(LAMBDA_DIR)/authorizer/spectra
	cd $(LAMBDA_DIR)/authorizer && zip -r ../authorizer.zip . -x "*.pyc" -x "__pycache__/*"
	
	# Show package sizes
	@echo -e "$(GREEN)Lambda packages created in $(LAMBDA_DIR)/$(NC)"
	@echo "Package sizes:"
	@ls -lh $(LAMBDA_DIR)/*.zip | awk '{print "  " $$9 ": " $$5}'

package-all: package-layer package-lambda  ## Create all Lambda packages (layer + functions)
	@echo -e "$(GREEN)All Lambda packages created!$(NC)"
	@echo ""
	@echo "Artifacts:"
	@echo "  - Layer:      $(LAMBDA_DIR)/layer.zip (shared dependencies)"
	@echo "  - API:        $(LAMBDA_DIR)/api-handler.zip (code only)"
	@echo "  - Worker:     $(LAMBDA_DIR)/worker.zip (code only)"
	@echo "  - Authorizer: $(LAMBDA_DIR)/authorizer.zip (code only)"

# Validate layer size (AWS limit: 250MB unzipped, 50MB zipped per layer)
validate-layer:  ## Validate Lambda layer size constraints
	@echo -e "$(BLUE)Validating Lambda layer...$(NC)"
	@LAYER_SIZE=$$(stat -f%z $(LAMBDA_DIR)/layer.zip 2>/dev/null || stat -c%s $(LAMBDA_DIR)/layer.zip); \
	if [ $$LAYER_SIZE -gt 52428800 ]; then \
		echo -e "$(RED)ERROR: Layer exceeds 50MB limit ($$LAYER_SIZE bytes)$(NC)"; \
		exit 1; \
	else \
		echo -e "$(GREEN)Layer size OK: $$LAYER_SIZE bytes (limit: 52428800)$(NC)"; \
	fi

# Build layer using Python script (supports Docker for production)
package-layer-docker:  ## Create Lambda layer using Docker (Amazon Linux 2 compatible)
	@echo -e "$(BLUE)Creating Lambda layer with Docker...$(NC)"
	uv run python scripts/build_layer.py --docker --output $(LAMBDA_DIR)/layer.zip

package-layer-script: requirements.txt  ## Create Lambda layer using Python script
	@echo -e "$(BLUE)Creating Lambda layer with script...$(NC)"
	uv run python scripts/build_layer.py --output $(LAMBDA_DIR)/layer.zip

# =============================================================================
# Terragrunt Infrastructure (Recommended)
# =============================================================================

# Terragrunt settings
TG_DIR := terragrunt
TG_DEV_DIR := $(TG_DIR)/environments/dev/us-east-1
TG_PROD_DIR := $(TG_DIR)/environments/prod/us-east-1

tg-init-dev:  ## Initialize Terragrunt for dev environment
	@echo -e "$(BLUE)Initializing Terragrunt (dev)...$(NC)"
	cd $(TG_DEV_DIR) && terragrunt run-all init

tg-init-prod:  ## Initialize Terragrunt for prod environment
	@echo -e "$(BLUE)Initializing Terragrunt (prod)...$(NC)"
	cd $(TG_PROD_DIR) && terragrunt run-all init

tg-validate-dev:  ## Validate Terragrunt configuration for dev
	@echo -e "$(BLUE)Validating Terragrunt (dev)...$(NC)"
	cd $(TG_DEV_DIR) && terragrunt run-all validate

tg-plan-dev:  ## Plan Terragrunt changes for dev
	@echo -e "$(BLUE)Planning Terragrunt (dev)...$(NC)"
	cd $(TG_DEV_DIR) && terragrunt run-all plan

tg-plan-prod:  ## Plan Terragrunt changes for prod
	@echo -e "$(BLUE)Planning Terragrunt (prod)...$(NC)"
	cd $(TG_PROD_DIR) && terragrunt run-all plan

tg-apply-dev:  ## Apply Terragrunt changes for dev
	@echo -e "$(YELLOW)Applying Terragrunt (dev)...$(NC)"
	cd $(TG_DEV_DIR) && terragrunt run-all apply

tg-apply-prod:  ## Apply Terragrunt changes for prod (requires confirmation)
	@echo -e "$(YELLOW)Applying Terragrunt (prod)...$(NC)"
	cd $(TG_PROD_DIR) && terragrunt run-all apply

tg-destroy-dev:  ## Destroy dev infrastructure (use with caution!)
	@echo -e "$(RED)Destroying dev infrastructure...$(NC)"
	cd $(TG_DEV_DIR) && terragrunt run-all destroy

tg-output-dev:  ## Show Terragrunt outputs for dev
	@echo -e "$(BLUE)Terragrunt outputs (dev):$(NC)"
	cd $(TG_DEV_DIR) && terragrunt run-all output

tg-graph-dev:  ## Show dependency graph for dev
	@echo -e "$(BLUE)Terragrunt dependency graph (dev):$(NC)"
	cd $(TG_DEV_DIR) && terragrunt graph-dependencies

# Module-specific commands
tg-plan-dynamodb-dev:  ## Plan DynamoDB module for dev
	@echo -e "$(BLUE)Planning DynamoDB (dev)...$(NC)"
	cd $(TG_DEV_DIR)/dynamodb && terragrunt plan

tg-plan-lambda-dev:  ## Plan Lambda module for dev
	@echo -e "$(BLUE)Planning Lambda (dev)...$(NC)"
	cd $(TG_DEV_DIR)/lambda && terragrunt plan

tg-plan-api-gateway-dev:  ## Plan API Gateway module for dev
	@echo -e "$(BLUE)Planning API Gateway (dev)...$(NC)"
	cd $(TG_DEV_DIR)/api-gateway && terragrunt plan

# =============================================================================
# Terraform Infrastructure (Legacy - use Terragrunt instead)
# =============================================================================

tf-init:  ## Initialize Terraform
	@echo -e "$(BLUE)Initializing Terraform...$(NC)"
	cd $(TF_DIR) && terraform init

tf-validate:  ## Validate Terraform configuration
	@echo -e "$(BLUE)Validating Terraform...$(NC)"
	cd $(TF_DIR) && terraform validate

tf-plan-dev:  ## Plan Terraform changes for dev
	@echo -e "$(BLUE)Planning Terraform (dev)...$(NC)"
	cd $(TF_DIR) && terraform plan $(TF_VARS_DEV) -out=tfplan

tf-plan-prod:  ## Plan Terraform changes for prod
	@echo -e "$(BLUE)Planning Terraform (prod)...$(NC)"
	cd $(TF_DIR) && terraform plan $(TF_VARS_PROD) -out=tfplan

tf-apply:  ## Apply Terraform changes
	@echo -e "$(YELLOW)Applying Terraform changes...$(NC)"
	cd $(TF_DIR) && terraform apply tfplan

tf-destroy-dev:  ## Destroy dev infrastructure (use with caution!)
	@echo -e "$(RED)Destroying dev infrastructure...$(NC)"
	cd $(TF_DIR) && terraform destroy $(TF_VARS_DEV)

tf-output:  ## Show Terraform outputs
	@echo -e "$(BLUE)Terraform outputs:$(NC)"
	cd $(TF_DIR) && terraform output

# =============================================================================
# Deployment (Using Terragrunt)
# =============================================================================

deploy-dev: package-all tg-plan-dev tg-apply-dev  ## Deploy to dev environment
	@echo -e "$(GREEN)Deployed to dev environment!$(NC)"

deploy-prod: package-all tg-plan-prod  ## Prepare prod deployment (manual apply required)
	@echo -e "$(YELLOW)Prod deployment planned. Run 'make tg-apply-prod' to deploy.$(NC)"

# =============================================================================
# Documentation
# =============================================================================

docs:  ## Build documentation
	@echo -e "$(BLUE)Building documentation...$(NC)"
	uv run mkdocs build

docs-serve:  ## Serve documentation locally
	@echo -e "$(BLUE)Serving documentation at http://localhost:8000$(NC)"
	uv run mkdocs serve

# =============================================================================
# Development Utilities
# =============================================================================

shell:  ## Start Python shell with project context
	@echo -e "$(BLUE)Starting Python shell...$(NC)"
	uv run python

repl:  ## Start IPython REPL
	@echo -e "$(BLUE)Starting IPython REPL...$(NC)"
	uv run ipython

pre-commit:  ## Run pre-commit hooks on all files
	@echo -e "$(BLUE)Running pre-commit hooks...$(NC)"
	uv run pre-commit run --all-files

update-hooks:  ## Update pre-commit hooks
	@echo -e "$(BLUE)Updating pre-commit hooks...$(NC)"
	uv run pre-commit autoupdate

# =============================================================================
# Local Development
# =============================================================================

local-api:  ## Run local API server (requires SAM CLI)
	@echo -e "$(BLUE)Starting local API server...$(NC)"
	sam local start-api --template template.yaml

local-invoke:  ## Invoke Lambda function locally
	@echo -e "$(BLUE)Invoking Lambda locally...$(NC)"
	sam local invoke ApiHandler --event events/sample-query.json

# =============================================================================
# CI/CD Helpers
# =============================================================================

ci-test:  ## Run CI test suite
	@echo -e "$(BLUE)Running CI tests...$(NC)"
	uv sync
	uv run pytest $(TESTS_DIR) --cov=$(SRC_DIR) --cov-report=xml --junitxml=test-results.xml

ci-lint:  ## Run CI linting
	@echo -e "$(BLUE)Running CI linting...$(NC)"
	uv sync
	uv run ruff check $(SRC_DIR) $(TESTS_DIR) --output-format=github
	uv run ruff format --check $(SRC_DIR) $(TESTS_DIR)
	uv run mypy $(SRC_DIR)

# =============================================================================
# Version Management
# =============================================================================

version:  ## Show current version
	@grep -E '^version = ' pyproject.toml | head -1 | cut -d'"' -f2

bump-patch:  ## Bump patch version
	@echo -e "$(BLUE)Bumping patch version...$(NC)"
	@uv run python -c "import re; \
		content = open('pyproject.toml').read(); \
		version = re.search(r'version = \"(\d+)\.(\d+)\.(\d+)\"', content).groups(); \
		new_version = f'{version[0]}.{version[1]}.{int(version[2])+1}'; \
		print(f'New version: {new_version}'); \
		open('pyproject.toml', 'w').write(re.sub(r'version = \"\d+\.\d+\.\d+\"', f'version = \"{new_version}\"', content))"

bump-minor:  ## Bump minor version
	@echo -e "$(BLUE)Bumping minor version...$(NC)"
	@uv run python -c "import re; \
		content = open('pyproject.toml').read(); \
		version = re.search(r'version = \"(\d+)\.(\d+)\.(\d+)\"', content).groups(); \
		new_version = f'{version[0]}.{int(version[1])+1}.0'; \
		print(f'New version: {new_version}'); \
		open('pyproject.toml', 'w').write(re.sub(r'version = \"\d+\.\d+\.\d+\"', f'version = \"{new_version}\"', content))"

bump-major:  ## Bump major version
	@echo -e "$(BLUE)Bumping major version...$(NC)"
	@uv run python -c "import re; \
		content = open('pyproject.toml').read(); \
		version = re.search(r'version = \"(\d+)\.(\d+)\.(\d+)\"', content).groups(); \
		new_version = f'{int(version[0])+1}.0.0'; \
		print(f'New version: {new_version}'); \
		open('pyproject.toml', 'w').write(re.sub(r'version = \"\d+\.\d+\.\d+\"', f'version = \"{new_version}\"', content))"
