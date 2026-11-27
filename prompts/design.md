# Stage: design

Write the technical design for one approved story. The director does not read
this document; the agents writing tests and code do, and they have no other
context. Aim for the shortest design that removes their guesswork.

## Steps

1. Read `AGENTS.md`, then the story's `story.md` and `spec.toml`.
2. Read the code the story touches and the designs of the stories it depends on.
3. Create the branch `story/NNN-slug` from main and write `docs/design/NNN-slug.md`:
   - **Approach**: how the behaviour will be delivered, in a few paragraphs.
   - **Changes**: modules and files to add or change; data model and API changes with their exact shapes.
   - **Test plan**: for each TC id, where the test will live, what it sets up, what it asserts. Note anything that needs a fixture or a fake.
   - **Risks and decisions**: alternatives you rejected and why; anything irreversible.
4. Compare your list of changed modules with `touches` in `spec.toml`. If the story will touch something not listed, say so in your comment on the story issue: another story may be running in parallel on it.
5. Push the branch. The conductor opens the pull request.

## Escalate instead of deciding

Stop and add the label `needs-human` with a comment if the story needs any of:
a new service or deployable, a new datastore, a change to an existing table's
meaning, a new external dependency or third-party API, or a change to
authentication or payment flows that the story does not spell out.

Also stop if an acceptance criterion is ambiguous enough that two reasonable
designs would behave differently for a user. Do not pick one silently.

## Finish

Label the story issue `done:design` and comment with a three-line summary.
You write no production code and no tests in this stage.
