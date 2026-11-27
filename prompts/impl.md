# Stage: impl

Implement one story so that its tests pass. The tests were written first by
another agent from the approved spec. They are the definition of done.

## Steps

1. Read `AGENTS.md`, the story's `story.md` and `spec.toml`, `docs/design/NNN-slug.md`, and the tests on the branch `story/NNN-slug`.
2. Implement the behaviour following the design. If the design is wrong or incomplete, fix the approach, and update the design document in the same commit so it stays true.
3. Stay inside the story. Do not add features, refactor unrelated code or "improve" things the story does not mention.
4. Run `make lint` and `make test` until both pass. Commit in small steps; push once, when the stage is complete.

## About the tests

Do not change a test's assertions to make it pass. If you believe a test is
wrong (it contradicts the spec, or asserts something the spec does not promise):

- fix it only if the spec clearly supports you, in a separate commit whose message starts with `test-change:` and explains, per TC id, what changed and why;
- otherwise stop and comment on the story issue.

The reviewer is told about every test changed after the tests stage and will
check each one against the spec. Never delete, skip or weaken a test.

## Other rules

- A new dependency needs a justification line in your comment and will be reviewed by a human. Verify the package name and publisher first.
- If you need something another unfinished story provides, stop and say which story. Do not build a temporary copy of it.
- If you touch a module not listed in the story's `touches`, say so in your comment.

## Finish

Label the story issue `done:impl`. Comment with: what you built, any test or
design changes and why, anything you could not do.

## When dispatched as `fix`

The prompt gives the reason: failing checks or review findings. Read the check
logs or the reviewer's findings on the pull request, fix exactly those, run
`make lint` and `make test`, push. The push is what asks for a fresh review: a
review verdict belongs to one commit. Comment on the story issue with what you
changed per finding. If you disagree with a finding, say why in the comment; do not ignore it.

## When dispatched as `resolve-conflict`

Rebase or merge main into the branch, resolve conflicts preserving both
stories' behaviour, run `make test`, push. If the conflict shows that the two
stories want incompatible things, stop and comment; do not pick a winner.
