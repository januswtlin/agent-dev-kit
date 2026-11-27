import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class InstallTests(unittest.TestCase):
    """install.sh puts a version outside every project; the launcher runs the one main pins."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        # A kit clone with one commit holding the files install.sh needs.
        self.kit = self.tmp / "kit"
        for rel in ("install.sh", "libexec/agentctl", "tools/run.py"):
            (self.kit / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, self.kit / rel)
        shutil.copytree(ROOT / "tools/agentctl", self.kit / "tools/agentctl", ignore=shutil.ignore_patterns("__pycache__"))
        git("init", "-q", cwd=self.kit)
        git("-c", "user.name=t", "-c", "user.email=t@t", "add", ".", cwd=self.kit)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "kit", cwd=self.kit)
        self.sha = git("rev-parse", "HEAD", cwd=self.kit)
        self.env = dict(os.environ, AGENTDEV_HOME=str(self.tmp / "data"), AGENTDEV_BIN=str(self.tmp / "bin"))
        self.env.pop("AGENTDEV_KIT_VERSION", None)

    def tearDown(self):
        subprocess.run(["chmod", "-R", "u+w", str(self.tmp)], check=False)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def install(self):
        return subprocess.run([str(self.kit / "install.sh")], env=self.env, capture_output=True, text=True)

    def project(self, pin_on_main: str, pin_in_tree: str | None = None) -> Path:
        """A project whose origin/main pins one version and whose working tree may say another."""
        origin = self.tmp / "origin.git"
        proj = self.tmp / "proj"
        git("init", "-q", "--bare", "-b", "main", str(origin), cwd=self.tmp)
        git("init", "-q", "-b", "main", str(proj), cwd=self.tmp)
        (proj / "agentdev.toml").write_text(f'[kit]\nversion = "{pin_on_main}"\n')
        git("-c", "user.name=t", "-c", "user.email=t@t", "add", ".", cwd=proj)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "pin", cwd=proj)
        git("remote", "add", "origin", str(origin), cwd=proj)
        git("push", "-q", "origin", "main", cwd=proj)
        git("fetch", "-q", "origin", cwd=proj)
        git("remote", "set-head", "origin", "main", cwd=proj)
        if pin_in_tree is not None:
            (proj / "agentdev.toml").write_text(f'[kit]\nversion = "{pin_in_tree}"\n')
        return proj

    def run_launcher(self, cwd, *args):
        return subprocess.run([str(self.tmp / "bin/agentctl"), *args], cwd=cwd, env=self.env, capture_output=True, text=True)

    def test_installs_read_only_by_sha_and_runs_the_version_main_pins(self):
        self.assertEqual(self.install().returncode, 0)
        dest = self.tmp / "data/versions" / self.sha
        self.assertTrue((dest / "tools/run.py").exists())
        self.assertEqual((dest / "tools/run.py").stat().st_mode & 0o222, 0)  # mode bits: root ignores them
        self.assertEqual(self.install().returncode, 0)  # again: nothing to do
        proj = self.project(self.sha)
        run = self.run_launcher(proj, "repo-name", "https://github.com/o/r.git")
        self.assertEqual((run.returncode, run.stdout.strip()), (0, "o/r"), run.stderr)

    def test_the_working_tree_cannot_choose_the_version(self):
        self.install()
        proj = self.project(self.sha, pin_in_tree="0" * 40)
        self.assertEqual(self.run_launcher(proj, "repo-name", "https://github.com/o/r").returncode, 0)
        proj2 = self.tmp / "proj"
        shutil.rmtree(proj2)
        shutil.rmtree(self.tmp / "origin.git")
        proj = self.project("1" * 40, pin_in_tree=self.sha)
        run = self.run_launcher(proj, "repo-name", "https://github.com/o/r")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("is not installed", run.stderr)

    def test_a_pin_that_is_not_a_full_sha_is_refused(self):
        self.install()
        run = self.run_launcher(self.project("main"), "repo-name", "x")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("40-character", run.stderr)


if __name__ == "__main__":
    unittest.main()
