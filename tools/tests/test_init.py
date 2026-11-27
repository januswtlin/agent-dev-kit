import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from agentctl import config, init, owners, pins

SHA = "a" * 40


class InitTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_a_new_project_gets_every_file_filled_in(self):
        created, kept = init.init(self.root, ["alice", "bob-b"], SHA)
        self.assertEqual(kept, [])
        for rel in ("agentdev.toml", ".github/CODEOWNERS", ".github/workflows/agentdev-ci.yml",
                    ".claude/agents/reviewer.md", "AGENTS.md", "docs/specs/_template/spec.toml"):
            self.assertIn(rel, created)
        cfg = config.load(self.root)
        self.assertEqual(cfg["kit"]["version"], SHA)
        self.assertEqual(cfg["roles"]["directors"], ["alice"])
        self.assertEqual(cfg["roles"]["humans"], ["alice", "bob-b"])
        for path in self.root.rglob("*"):
            if path.is_file() and ".git" not in path.parts:
                text = path.read_text(encoding="utf-8")
                self.assertNotRegex(text, r"__[A-Z_]+(:[a-z-]+)?__", path)
                if path.suffix == ".md":  # an unfilled prompt placeholder
                    self.assertNotIn("${", text, path)
        self.assertIn("Stage: review", (self.root / ".claude/agents/reviewer.md").read_text())
        self.assertEqual(pins.check(self.root, cfg["kit"]["repository"], SHA), [])
        self.assertEqual((self.root / ".github/CODEOWNERS").read_text(), owners.codeowners(cfg))
        self.assertTrue((self.root / ".claude/hooks/guard.sh").stat().st_mode & 0o100)

    def test_files_from_a_read_only_kit_are_writable_in_the_project(self):
        import os
        template = init.TEMPLATE / "agentdev.toml"
        mode = template.stat().st_mode
        os.chmod(template, mode & ~0o222)
        try:
            init.init(self.root, ["alice"], SHA)
        finally:
            os.chmod(template, mode)
        self.assertTrue((self.root / "agentdev.toml").stat().st_mode & 0o200)

    def test_existing_files_are_kept_never_overwritten(self):
        (self.root / "AGENTS.md").write_text("ours\n")
        created, kept = init.init(self.root, ["alice"], SHA)
        self.assertIn("AGENTS.md", kept)
        self.assertEqual((self.root / "AGENTS.md").read_text(), "ours\n")
        again_created, again_kept = init.init(self.root, ["alice"], SHA)
        self.assertEqual(again_created, [])

    def test_a_dry_run_writes_nothing(self):
        created, _ = init.init(self.root, ["alice"], SHA, dry_run=True)
        self.assertIn("agentdev.toml", created)
        self.assertFalse((self.root / "agentdev.toml").exists())

    def test_bad_input_is_refused(self):
        for people, version in ((["not a login"], SHA), (["alice"], "main"), ([], SHA)):
            with self.assertRaises(SystemExit):
                init.init(self.root, people, version)

    @unittest.skipUnless(shutil.which("actionlint"), "actionlint is not installed")
    def test_the_generated_workflows_pass_actionlint(self):
        init.init(self.root, ["alice"], SHA)
        files = sorted(str(p) for p in (self.root / ".github/workflows").glob("*.yml"))
        run = subprocess.run(["actionlint", *files], capture_output=True, text=True, cwd=self.root)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


class PinTests(unittest.TestCase):
    def write(self, text):
        root = Path(tempfile.mkdtemp())
        (root / ".github/workflows").mkdir(parents=True)
        (root / ".github/workflows/x.yml").write_text(text)
        return root

    def test_every_call_of_the_kit_uses_the_pinned_version(self):
        good = f"jobs:\n  ci:\n    uses: o/kit/.github/workflows/ci.yml@{SHA}\n    with:\n      kit_version: {SHA}\n"
        self.assertEqual(pins.check(self.write(good), "o/kit", SHA), [])
        other = "b" * 40
        self.assertTrue(pins.check(self.write(good.replace(f"@{SHA}", f"@{other}")), "o/kit", SHA))
        self.assertTrue(pins.check(self.write(good.replace(f"kit_version: {SHA}", "kit_version: main")), "o/kit", SHA))
        self.assertTrue(pins.check(self.write(good.replace(f"      kit_version: {SHA}\n", "")), "o/kit", SHA))
        self.assertTrue(pins.check(self.write(good), "o/kit", "main"))
        self.assertTrue(pins.check(self.write(good.replace("o/kit/", "fork/kit/")), "o/kit", SHA))
        self.assertTrue(pins.check(self.write(good + "      kit_repository: fork/kit\n"), "o/kit", SHA))


if __name__ == "__main__":
    unittest.main()
