# The kit's own checks. Projects do not use this file: their commands are
# [tests] setup_cmd, lint_cmd and test_cmd in their agentdev.toml.

.PHONY: lint test

SHELL_SCRIPTS = install.sh libexec/agentctl bin/agentctl sandbox/sbx.sh templates/project/.claude/hooks/guard.sh

lint:
	@python3 -m compileall -q tools >/dev/null
	@python3 -m pyflakes tools
	@shellcheck $(SHELL_SCRIPTS)
	@actionlint
	@bin/agentctl spec-lint
	@bin/agentctl docs-lint

test:
	@PYTHONPATH=tools python3 -m unittest discover -s tools/tests -q
