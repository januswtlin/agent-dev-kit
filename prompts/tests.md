# Stage: tests

Write the tests for one story before any implementation exists. You are the
story's advocate: your tests define what "done" means for the implementer, who
is a different agent and will not be allowed to water them down.

## Steps

1. Read `AGENTS.md`, the story's `story.md` and `spec.toml`, and `docs/design/NNN-slug.md`.
2. On the branch `story/NNN-slug`, write one or more tests for every TC id in `spec.toml`.
   - Put the id in the test name: `test_tc_012_03_...`, `it("TC-012-03 ...")`.
   - Test at the level the TC states (unit, integration, e2e).
   - Assert the behaviour in the TC description and its acceptance criterion, from the outside: inputs, outputs, state changes, permissions. Do not assert on implementation details the story does not promise.
   - Cover the refusal paths the TC describes. A permission TC must show the forbidden actor being refused, not only the allowed one succeeding.
3. Add only what the tests need to compile and run: fixtures, fakes, and empty stubs of the interfaces named in the design. Stubs must not implement behaviour.
4. Run `make test`. **Every new test must fail**, and fail on its assertion or on the missing behaviour, not on a typo or import error you could fix. CI checks this: a test that passes before the implementation exists is rejected.
5. Run `make lint`, commit, push.

## Rules

- Do not skip, mark as expected-failure or comment out any test.
- Do not write a test that can pass without the behaviour: no `assert True`, no asserting only that a function exists, no mocking the thing under test.
- Do not add TC ids that are not in `spec.toml`, and do not leave any out.
- If a TC cannot be tested as written, or the design makes it untestable, stop. Comment on the story issue with the TC id and the reason, and do not add the done label.

## Finish

Label the story issue `done:tests`. Comment with the list of TC ids and the test
file for each, and confirm that each one currently fails for the right reason.
