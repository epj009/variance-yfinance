# Makefile for Variance

# Python interpreter in virtual environment
VENV_PYTHON = ./venv/bin/python3
VENV_PIP = ./venv/bin/pip
PYTEST = ./venv/bin/pytest

# Default shell
SHELL := /bin/bash

.PHONY: help setup clean check test triage screen

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%%-15s\033[0m %s\n", $$1, $$2}'

setup: ## Create venv and install dependencies
	@echo "Setting up virtual environment..."
	@rm -rf venv
	@python3 -m venv venv
	@echo "Installing dependencies..."
	@$(VENV_PIP) install -r requirements.txt
	@echo "Setup complete. Virtual environment ready in ./venv"

clean: ## Remove venv, cache, and temporary files
	@echo "Cleaning up..."
	@rm -rf venv
	@rm -rf __pycache__
	@rm -rf .pytest_cache
	@rm -rf .market_cache.db
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@echo "Clean complete."

check: ## Run diagnostics (requires setup)
	@echo "Running environment check..."
	@$(VENV_PYTHON) --version
	@echo "Checking key packages..."
	@$(VENV_PYTHON) -c "import yfinance; import pandas; import numpy; print('Imports successful.')"

test: ## Run unit tests
	@echo "Running tests..."
	@$(PYTEST) -q

triage: ## Run portfolio analysis (defaults to sample if no file provided)
	@echo "Running Morning Triage..."
	@if [ -z "$(FILE)" ]; then \
		echo "No FILE specified. Using sample data."; \
		$(VENV_PYTHON) scripts/analyze_portfolio.py util/sample_positions.csv; \
	else \
		$(VENV_PYTHON) scripts/analyze_portfolio.py $(FILE); \
	fi

screen: ## Run volatility screener
	@echo "Running Volatility Screener..."
	@$(VENV_PYTHON) scripts/vol_screener.py $(ARGS)

screen-non-equity: ## Run screener excluding Equity assets (Correlation Defense)
	@echo "Running Non-Equity Screener..."
	@$(VENV_PYTHON) scripts/vol_screener.py --exclude-asset-classes Equity
