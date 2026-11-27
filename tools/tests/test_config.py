import tempfile
import unittest
from pathlib import Path

from agentctl import config, ids, owners, prompts, specs


def load(text: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "agentdev.toml").write_text(text, encoding="utf-8")
        return config.load(tmp)


class ConfigTests(unittest.TestCase):
    def tearDown(self):
        ids.configure(3)

    def test_without_a_file_the_kit_defaults_apply(self):
        cfg = config.load(Path(__file__).parent / "no-such-project")
        self.assertEqual(cfg["tests"]["junit_glob"], "reports/junit/*.xml")
        self.assertEqual(cfg["conductor"]["wip_limit"], 2)

    def test_tables_merge_and_values_replace(self):
        cfg = load('[tests]\ntest_cmd = "npm test"\n[risk.t2]\nhigh_risk = ["infra/**"]\n')
        self.assertEqual(cfg["tests"]["test_cmd"], "npm test")
        self.assertEqual(cfg["tests"]["junit_glob"], "reports/junit/*.xml")  # untouched key kept
        self.assertEqual(cfg["risk"]["t2"]["high_risk"], ["infra/**"])     # a list replaces
        self.assertIn("**/package.json", cfg["risk"]["t2"]["dependency_manifests"])

    def test_the_rules_that_judge_a_change_are_always_guarded(self):
        cfg = load('[risk.t2]\nguardrails = ["AGENTS.md"]\n')
        self.assertEqual(cfg["risk"]["t2"]["guardrails"], ["AGENTS.md", ".github/**", "agentdev.toml"])

    def test_t2_can_never_be_merged_automatically(self):
        with self.assertRaises(SystemExit):
            load('[conductor]\nauto_merge_tiers = ["T1", "T2"]\n')

    def test_a_broken_file_is_reported_not_ignored(self):
        with self.assertRaises(SystemExit):
            load("[tests\n")

    def test_story_ids_of_four_digits(self):
        load("[stories]\nid_digits = 4\n")
        self.assertEqual(ids.story_from_branch("story/0463-booking"), "0463")
        self.assertIsNone(ids.story_from_branch("story/463-booking"))
        self.assertTrue(ids.TC_RE.fullmatch("TC-0463-01"))
        self.assertEqual([m.group(1) for m in ids.TC_IN_TEST_RE.finditer("test_tc_0463_02 TC-463-01")], ["0463"])
        with self.assertRaises(SystemExit):
            load("[stories]\nid_digits = 1\n")


class OwnersTests(unittest.TestCase):
    def test_codeowners_lists_every_protected_pattern_for_the_directors(self):
        cfg = load('[roles]\ndirectors = ["alice"]\n[risk.t2]\nhigh_risk = ["infra/**", "**/migrations/**"]\n')
        text = owners.codeowners(cfg)
        for line in ["/docs/specs/** @alice", "/.github/** @alice", "/agentdev.toml @alice",
                     "**/package.json @alice", "/infra/** @alice", "**/migrations/** @alice"]:
            pattern, owner = line.split()
            self.assertRegex(text, rf"(?m)^{pattern.replace('*', r'[*]').replace('.', r'[.]')} +{owner}$")

    def test_codeowners_needs_a_director(self):
        with self.assertRaises(SystemExit):
            owners.codeowners(load(""))


class PromptTests(unittest.TestCase):
    def test_every_placeholder_is_filled(self):
        for translation in ("zh-TW", ""):
            cfg = load(f'[stories]\ntranslation = "{translation}"\n[tests]\ntest_cmd = "npm test"\n')
            for path in sorted(prompts.PROMPTS.glob("*.md")):
                text = prompts.render(path.stem, cfg)
                self.assertNotIn("${", text, path.name)
            self.assertIn("`npm test`", prompts.render("impl", cfg))

    def test_the_story_translation_follows_the_configuration(self):
        self.assertIn("story-zh-TW.md", prompts.render("product-owner", load("")))
        self.assertNotIn("story-", prompts.render("product-owner", load('[stories]\ntranslation = ""\n')))


class SpecIdTests(unittest.TestCase):
    def tearDown(self):
        ids.configure(3)

    def test_lint_follows_the_configured_id_length(self):
        ids.configure(4)
        good = ('id = "0001"\ntouches = ["x"]\n[[ac]]\nid = "AC-0001-1"\n[[tc]]\nid = "TC-0001-01"\n'
                'ac = ["AC-0001-1"]\nlevel = "unit"\n')
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp, "0001-x")
            folder.mkdir()
            (folder / "spec.toml").write_text(good, encoding="utf-8")
            (folder / "story.md").write_text("AC-0001-1 TC-0001-01\n", encoding="utf-8")
            self.assertEqual(specs.lint(tmp, translation=""), [])


if __name__ == "__main__":
    unittest.main()
