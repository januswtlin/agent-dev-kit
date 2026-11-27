"""What each stage is allowed to hold. Least privilege, enforced outside the agent.

Every dispatched stage runs in its own sandbox, so each can be given different
things. Three dimensions:

  token     what the stage's GitHub token may do. Enforced by GitHub: an App
            installation token can be minted with a subset of the App's permissions.
              write  push branches; comment and label on issues. Cannot open,
                     review or merge a pull request.
              read   read the repository; comment, label, review a pull request.
                     Cannot push.
  network   which hosts the sandbox may reach.
              base   source control and the model providers
              build  base plus the package registries
  settings  which deny rules the harness runs under (a soft, second layer).
              story  may not edit guardrail paths or approved specs
              spec   may not edit guardrail paths; may write specs, sprints, product docs

These are constants in code on purpose. A sandbox is set up by the copy of this
file pinned outside the repository (see sandbox/sbx.sh), so a branch cannot grant
itself more.

What this cannot express: GitHub permissions are per repository, not per path.
"The test writer may not touch the implementation" stays a matter for the gates.
"""

from __future__ import annotations

# A token that can push cannot open, retarget or review pull requests: opening them
# is the conductor's job. A token that can review cannot push. Nobody but the
# conductor gets both.
#
# This does NOT stop a push token from merging: GitHub's merge endpoint asks for
# "contents: write" only. What stops it is the `main-merge` ruleset, which lets
# only repository admins and the Conductor App update the default branch.
TOKEN_PERMISSIONS = {
    "write": {"contents": "write", "pull_requests": "read", "issues": "write"},
    "read": {"contents": "read", "pull_requests": "write", "issues": "write"},
}

BUILD = ("write", "build", "story")
STAGE_PROFILES = {
    "design": BUILD,
    "tests": BUILD,
    "impl": BUILD,
    "fix": BUILD,
    "resolve-conflict": BUILD,
    "fix-main": BUILD,
    "review": ("read", "base", "story"),
    "triage": ("read", "base", "story"),
    "product-owner": ("write", "base", "spec"),
    "planner": ("write", "base", "spec"),
}
# A stage this file does not know gets the least it can.
DEFAULT = ("read", "base", "story")


def for_stage(stage: str) -> dict[str, str]:
    token, network, settings = STAGE_PROFILES.get(stage, DEFAULT)
    return {"token": token, "network": network, "settings": settings}
