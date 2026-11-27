# The contract between the pipeline and the project. CI and agents only call
# these targets, so the technology stack can change without touching workflows.
#
#   make setup   install toolchains and dependencies
#   make lint    static checks; non-zero on any finding
#   make test    run ALL tests and write JUnit XML to reports/junit/*.xml;
#                non-zero when a test fails
#   make build   produce deployable artefacts
#
# Replace the project-* targets when the stack is chosen. Examples:
#   pytest:      pytest --junitxml=reports/junit/python.xml
#   vitest:      vitest run --reporter=junit --outputFile=reports/junit/web.xml
#   go:          gotestsum --junitfile reports/junit/go.xml ./...

.PHONY: setup lint test build tools-test project-lint project-test project-build

setup:
	@echo "nothing to set up yet"

lint: project-lint
	@python3 -m compileall -q tools >/dev/null
	@bin/agentctl spec-lint

test: tools-test project-test

build: project-build

# Tests of the pipeline's own tooling. They do not write JUnit XML on purpose:
# they are not story tests and carry no TC ids.
tools-test:
	@PYTHONPATH=tools python3 -m unittest discover -s tools/tests -q

project-lint:
	@true

project-test:
	@mkdir -p reports/junit

project-build:
	@true
