# Targets wrap the exact commands CI runs, so a human and CI do the same thing.
SYNAPSE_BIN ?= synapse
export SYNAPSE_BIN

.DEFAULT_GOAL := help
.PHONY: help install lint test test-check test-splunk test-splunk-unit test-splunk-controls test-fail2ban test-syslog-ng test-syslog-ng-controls fmt clean

help: ## List the targets
	@grep -hE '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

install: ## Install the lint tooling (yamllint, pinned in requirements-dev.txt)
	pip install -r requirements-dev.txt

lint: ## Lint every YAML file, and refuse a brace-less `in` in rules expressions
	yamllint .
	scripts/check-expressions.sh
	scripts/check-expressions.sh scripts/fixtures/expr-ok >/dev/null 2>&1
	scripts/check-expressions.sh scripts/fixtures/expr-no-brace >/dev/null 2>&1; test $$? -eq 1
	scripts/check-expressions.sh scripts/fixtures/expr-block-scalar 2>&1 >/dev/null | grep -c "without braces" | grep -qx 4

test: test-check ## Run the controls, then check every config set with `synapse --check-config` (set SYNAPSE_BIN; SYNAPSE_REQUIRE_ML=1 fails sets skipped for lack of the classifier feature)
	scripts/check.sh

test-check: ## Run the controls that prove scripts/check.sh can fail
	scripts/test-check.sh

test-splunk: ## Test the Splunk add-on in Splunk 9.0.1 (needs docker; pulls a ~1 GB image)
	cd integrations/splunk && python3 test/test_splunk.py

test-splunk-unit: ## Unit-test the Splunk controls runner against a fake Splunk (no docker)
	cd integrations/splunk && python3 -m unittest discover -s test -p 'test_controls_runner.py'

test-splunk-controls: ## Break the Splunk add-on one way at a time and check the test notices (needs docker)
	cd integrations/splunk && python3 test/test_splunk.py --controls

test-fail2ban: ## Test the Fail2Ban action (needs the fail2ban package, e.g. apt install fail2ban)
	cd integrations/fail2ban && python3 test/test_action.py

test-syslog-ng: ## Test the syslog-ng forwarding config in AxoSyslog 4.29.0 (needs docker)
	cd integrations/syslog-ng && python3 test/test_forward.py

test-syslog-ng-controls: ## Break the syslog-ng config one way at a time and check the test notices (needs docker)
	cd integrations/syslog-ng && python3 test/test_forward.py --controls

fmt: ## No formatter is used; `make lint` reports style problems
	@echo "No formatter in this repository. Run 'make lint' for style checks."

clean: ## Remove local tooling output
	rm -rf .venv __pycache__
