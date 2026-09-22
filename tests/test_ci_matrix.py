import unittest

from ci_matrix import ALL, select


class SelectionTests(unittest.TestCase):
    def test_docs_only_skips_images(self):
        self.assertEqual(select(["docs/hermes.md", "README.md"]), set())

    def test_app_change_selects_one_image(self):
        self.assertEqual(select(["runtimes/chatgpt-desktop/root/launcher"]), {"grotto-chatgpt-desktop"})

    def test_shared_or_unknown_change_selects_every_image(self):
        self.assertEqual(select(["tests/smoke-desktop.sh"]), ALL)
        self.assertEqual(select([".github/workflows/build.yml"]), ALL)

    def test_brewfile_selects_users(self):
        self.assertEqual(select(["Brewfile"]), {"grotto-openclaw", "grotto-hermes", "grotto-hermes-desktop"})


if __name__ == "__main__":
    unittest.main()
