# Stage: review

Review one story's pull request. You are a different agent from the one that
wrote the code, ideally from a different vendor, and you start with no memory
of how it was built. Be sceptical: agents overstate their own work, and the
director will not read this code. You are the last reader before it merges.

## Read

1. `AGENTS.md`, especially "Code Review Rules".
2. The story's `story.md` and `spec.toml`. This is the standard you review against.
3. The full diff of `story/NNN-slug` against main, and the commit history.
4. The comments on the story issue, including anything the implementer said it could not do.

## Part 1: test fidelity audit

For **every** TC id in `spec.toml`, find the test and answer:

- Does it exercise the situation in the TC description (the WHEN)?
- Do its assertions verify the outcome (the THEN), including state changes and refusals?
- Could it pass with a wrong or missing implementation (over-mocked, asserts too little, wrong level)?

List every commit that changed a test after the tests stage (messages starting
`test-change:` and any others you find in the history). For each, decide whether
the change is supported by the spec. A weakened assertion is a blocking finding.

## Part 2: implementation

- Does the behaviour satisfy each acceptance criterion? Read the code; do not infer from green tests.
- Anything outside the story's scope, or behaviour the story lists as out of scope?
- Security: missing authorisation checks, injection, secrets, unsafe file handling, data exposed to the wrong actor.
- Data: irreversible operations, migrations without a way back, lost updates.
- Dependencies added without justification. Changes to guardrail paths.

Do not block on style, naming or structure you would merely have done differently.

## Output

Do not commit or push. Write two files in the repository root.

`review-findings.md`, posted on the pull request:

```
## Agent review: story NNN — PASS | CHANGES REQUESTED

### Test fidelity
| TC | Test (file:line) | Verifies the TC? | Note |
|---|---|---|---|
| TC-NNN-01 | tests/...:42 | yes / partly / no | ... |

### Tests changed after the tests stage
- <commit> TC-NNN-0x: justified / not justified, because ...

### Blocking findings
1. file:line — what is wrong — what would fix it

### Non-blocking notes
- ...
```

`review-verdict.json`:

```json
{"verdict": "pass", "blocking": 0}
```

Use `"verdict": "fail"` if any TC is "partly" or "no", if any test change is not
justified, or if there is any blocking finding. When in doubt, fail and explain:
a wrong pass merges unreviewed code, a wrong fail costs one more round.

If you run as an interactive or cloud session rather than a workflow job, post
`review-findings.md` as a pull request review and end its body with the line
`agent-review: pass` or `agent-review: fail`.

## Finish

Label the story issue `done:review`. When you run as the `agent-review` workflow job, the job does this for you.
