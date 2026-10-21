# Targets wrap the exact commands CI runs, so a human and CI do the same thing.
SYNAPSE_BIN ?= synapse
export SYNAPSE_BIN

.DEFAULT_GOAL := help
.PHONY: help install lint test test-check test-splunk test-splunk-controls fmt clean

help: ## List the targets
	@grep -hE '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

install: ## Install the lint tooling (yamllint, pinned in requirements-dev.txt)
	pip install -r requirements-dev.txt

lint: ## Lint every YAML file
	yamllint .

test: test-check ## Run the controls, then check every config set with `synapse --check-config` (set SYNAPSE_BIN)
	scripts/check.sh

test-check: ## Run the controls that prove scripts/check.sh can fail
	scripts/test-check.sh

test-splunk: ## Test the Splunk add-on in Splunk 9.0.1 (needs docker; pulls a ~1 GB image)
	cd integrations/splunk && python3 test/test_splunk.py

test-splunk-controls: ## Break the Splunk add-on one way at a time and check the test notices (needs docker)
	cd integrations/splunk && python3 test/test_splunk.py --controls

fmt: ## No formatter is used; `make lint` reports style problems
	@echo "No formatter in this repository. Run 'make lint' for style checks."

clean: ## Remove local tooling output
	rm -rf .venv __pycache__
