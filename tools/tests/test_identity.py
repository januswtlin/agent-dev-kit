import base64
import json
import os
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

from agentctl import apptoken, github

ROOT = Path(__file__).resolve().parents[2]


class SecretLookupTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)

    def test_developer_specific_secret_wins_over_shared(self):
        os.environ["CONDUCTOR_SECRETS"] = json.dumps({"DISPATCH_TOKEN": "shared", "DISPATCH_TOKEN_ALICE_SMITH": "hers"})
        self.assertEqual(github.secret("DISPATCH_TOKEN", "alice-smith"), "hers")
        self.assertEqual(github.secret("DISPATCH_TOKEN", "bob"), "shared")
        self.assertEqual(github.secret("DISPATCH_TOKEN"), "shared")
        self.assertEqual(github.secret("MISSING", "bob"), "")

    def test_falls_back_to_the_environment_for_local_runs(self):
        os.environ.pop("CONDUCTOR_SECRETS", None)
        os.environ["CLAUDE_TRIGGER_URL_BOB"] = "https://bob"
        self.assertEqual(github.secret("CLAUDE_TRIGGER_URL", "bob"), "https://bob")


class AppTokenTests(unittest.TestCase):
    def test_remote_url_forms(self):
        for url in ["https://github.com/acme/app.git", "git@github.com:acme/app.git", "https://github.com/acme/app/\n",
                    "https://x-access-token:abc@github.com/acme/app"]:
            self.assertEqual(apptoken.repo_from_remote(url), "acme/app", url)
        self.assertIsNone(apptoken.repo_from_remote("https://example.com/acme/app"))

    @unittest.skipUnless(shutil.which("openssl"), "openssl not installed")
    def test_jwt_is_signed_with_the_app_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, pub = Path(tmp) / "key.pem", Path(tmp) / "pub.pem"
            subprocess.run(["openssl", "genrsa", "-out", str(key), "2048"], check=True, capture_output=True)
            subprocess.run(["openssl", "rsa", "-in", str(key), "-pubout", "-out", str(pub)], check=True, capture_output=True)
            token = apptoken.make_jwt("12345", key, now=1_000_000)
            header, payload, signature = token.split(".")
            pad = lambda s: s + "=" * (-len(s) % 4)
            self.assertEqual(json.loads(base64.urlsafe_b64decode(pad(payload))),
                             {"iat": 999_940, "exp": 1_000_540, "iss": "12345"})
            sig = Path(tmp) / "sig"
            sig.write_bytes(base64.urlsafe_b64decode(pad(signature)))
            verify = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(pub), "-signature", str(sig)],
                                    input=f"{header}.{payload}".encode(), capture_output=True)
            self.assertEqual(verify.returncode, 0, verify.stderr)

    def test_cached_token_is_reused_only_while_valid_and_for_the_same_repo(self):
        cached = {"repo": "acme/app", "app_id": "1", "token": "t", "expires": 2000}
        self.assertTrue(apptoken._fresh(cached, "acme/app", "1", now=1000))
        self.assertFalse(apptoken._fresh(cached, "acme/app", "1", now=1800))
        self.assertFalse(apptoken._fresh(cached, "acme/other", "1", now=1000))
        self.assertFalse(apptoken._fresh(cached, "acme/app", "2", now=1000))


class TemplateNeutralityTests(unittest.TestCase):
    def test_init_fills_in_the_people(self):
        with tempfile.TemporaryDirectory() as tmp:
            for rel in ("scripts/init.sh", ".github/CODEOWNERS", "policy/roles.toml"):
                (Path(tmp) / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / rel, Path(tmp) / rel)
            run = subprocess.run([str(Path(tmp) / "scripts/init.sh"), "alice", "bob-b"], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            roles = tomllib.loads((Path(tmp) / "policy/roles.toml").read_text())
            self.assertEqual(roles["directors"], ["alice"])
            self.assertEqual(roles["humans"], ["alice", "bob-b"])
            owners = (Path(tmp) / ".github/CODEOWNERS").read_text()
            self.assertIn("@alice", owners)
            self.assertNotIn("DIRECTOR_LOGIN", owners)
            again = subprocess.run([str(Path(tmp) / "scripts/init.sh"), "carol"], capture_output=True, text=True)
            self.assertNotEqual(again.returncode, 0)
            bad = subprocess.run([str(ROOT / "scripts/init.sh"), "not a login"], capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)


if __name__ == "__main__":
    unittest.main()
