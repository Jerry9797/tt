import unittest
from pathlib import Path


class LangSmithConfigTests(unittest.TestCase):
    def test_env_example_contains_langsmith_settings(self):
        env_example = Path(".env.example").read_text(encoding="utf-8")

        self.assertIn("LANGSMITH_API_KEY=", env_example)
        self.assertIn("LANGSMITH_TRACING=true", env_example)
        self.assertIn("LANGSMITH_PROJECT=tt", env_example)
        self.assertIn("LANGSMITH_ENDPOINT=https://api.smith.langchain.com", env_example)


if __name__ == "__main__":
    unittest.main()
