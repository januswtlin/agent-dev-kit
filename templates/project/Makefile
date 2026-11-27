# Starting point for a new project: Python's unittest over tests/, with JUnit XML
# for the kit's gates. Replace the commands once the project has chosen its stack,
# and keep [tests] in agentdev.toml in step:
#   pytest:   pytest --junitxml=reports/junit/python.xml
#   vitest:   vitest run --reporter=junit --outputFile=reports/junit/web.xml
#   node:     node --test --test-reporter=junit --test-reporter-destination=reports/junit/node.xml
#   go:       gotestsum --junitfile reports/junit/go.xml ./...

.PHONY: lint test

lint:
	@true

test:
	@mkdir -p reports/junit
	@agentctl junit-unittest tests reports/junit/unittest.xml
