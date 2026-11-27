import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FAKE_SBX = r"""#!/usr/bin/env bash
echo "$*" >> "$SBX_LOG"
case "$1" in
  ls) [ -n "${SBX_EXISTING:-}" ] && echo "$SBX_EXISTING"; exit 0 ;;
  exec)
    last="${!#}"
    case "$last" in https://github.com/) echo "HTTP 200" ;; https://*) echo NONE ;; esac
    exit 0 ;;
esac
[ "$1" = "${SBX_FAIL:-}" ] && exit 1
exit 0
"""


class SbxJobTests(unittest.TestCase):
    """`sbx.sh job` against a fake sbx: a failed step stops it, and it removes only what it created."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        (bin_dir / "sbx").write_text(FAKE_SBX)
        (bin_dir / "sbx").chmod(0o755)
        self.project = self.tmp / "dev" / "proj"
        self.project.mkdir(parents=True)
        git = lambda *a: subprocess.run(["git", "-C", str(self.project), *a], check=True, capture_output=True)  # noqa: E731
        git("init", "-q", "-b", "main")
        (self.project / "agentdev.toml").write_text('[risk.t2]\nguardrails = ["ours/**"]\n')
        git("-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "main")
        # What the default branch says, as last fetched; and a tag that tries to pass for it.
        git("update-ref", "refs/remotes/origin/main", "HEAD")
        git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        git("checkout", "-q", "-b", "story/012-x")
        (self.project / "agentdev.toml").write_text('[risk.t2]\nguardrails = []\n')
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "agent")
        git("tag", "origin/main")
        git("remote", "add", "origin", "https://github.com/o/r.git")
        data = self.tmp / "data"
        helper = data / "agent-dev" / "o-r" / "github-token-write"
        helper.parent.mkdir(parents=True)
        helper.write_text("#!/bin/sh\n")
        helper.chmod(0o700)
        self.log = self.tmp / "sbx.log"
        self.env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", HOME=str(self.tmp),
                        XDG_DATA_HOME=str(data), XDG_STATE_HOME=str(self.tmp / "state"),
                        AGENT_PROJECT_DIR=str(self.project), SBX_LOG=str(self.log))

    def job(self, **env):
        run = subprocess.run(["bash", str(ROOT / "sandbox/sbx.sh"), "job", "claude", "012", "impl", "do it"],
                             env=dict(self.env, **env), capture_output=True, text=True, cwd=self.project)
        calls = [line.split()[0] for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return run.returncode, calls

    def test_a_failed_secret_stops_before_the_agent_runs_and_the_sandbox_is_removed(self):
        code, calls = self.job(SBX_FAIL="secret")
        self.assertNotEqual(code, 0)
        self.assertIn("create", calls)
        self.assertNotIn("run", calls)
        self.assertEqual(calls[-1], "rm")

    def test_a_failed_create_removes_nothing(self):
        code, calls = self.job(SBX_FAIL="create")
        self.assertNotEqual(code, 0)
        self.assertNotIn("run", calls)
        self.assertNotIn("rm", calls)

    def test_a_good_run_runs_the_agent_and_then_removes_the_sandbox(self):
        code, calls = self.job()
        self.assertEqual(code, 0)
        self.assertEqual(calls[calls.index("run"):], ["run", "rm"])
        self.assertFalse(list((self.tmp / "state").rglob("*.created")))

    def test_the_deny_rules_come_from_the_default_branch_not_a_tag_or_the_tree(self):
        copied = self.tmp / "copied.json"
        fake = (self.tmp / "bin/sbx").read_text().replace(
            "[ \"$1\" = \"${SBX_FAIL:-}\" ] && exit 1",
            "[ \"$1\" = cp ] && cp \"$2\" \"$SBX_COPY\"\n[ \"$1\" = \"${SBX_FAIL:-}\" ] && exit 1")
        (self.tmp / "bin/sbx").write_text(fake)
        code, _ = self.job(SBX_COPY=str(copied))
        self.assertEqual(code, 0)
        self.assertIn("Edit(ours/**)", copied.read_text())

    def test_without_settings_on_the_default_branch_the_job_does_not_start(self):
        subprocess.run(["git", "-C", str(self.project), "update-ref", "-d", "refs/remotes/origin/main"], check=True)
        code, calls = self.job()
        self.assertNotEqual(code, 0)
        self.assertNotIn("run", calls)


if __name__ == "__main__":
    unittest.main()
