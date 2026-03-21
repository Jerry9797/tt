import unittest

from src.config.sop_loader import SOPConfigLoader
from src.tools import ALL_TOOLS


class SOPConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loader = SOPConfigLoader("src/config/sop_config.yaml")

    def test_new_sops_are_loaded(self):
        expected_keys = {
            "asset_query",
            "access_record_query",
            "restore_user_scene",
            "merchant_exposure_query",
            "product_rule_issue",
        }

        loaded_keys = set(self.loader.get_all_sop_keys())
        self.assertTrue(expected_keys.issubset(loaded_keys))

    def test_restore_user_scene_is_no_longer_placeholder(self):
        sop = self.loader.get_sop("restore_user_scene")

        self.assertIsNotNone(sop)
        self.assertNotEqual(sop.steps, ["1", "2", "3"])
        self.assertIn("search_user_access_history", sop.tools)
        self.assertIn("restore_user_scene", sop.tools)
        self.assertIn("trace_id", sop.planning_prompt)

    def test_new_sop_tools_are_registered(self):
        tool_names = {tool.name for tool in ALL_TOOLS}

        expected_tools = {
            "query_request_related_assets",
            "query_merchant_exposure",
            "query_rule_engine_config",
        }

        self.assertTrue(expected_tools.issubset(tool_names))

    def test_new_sop_tools_resolve_from_loader(self):
        tool_names = {tool.name for tool in ALL_TOOLS}

        for intent in (
            "asset_query",
            "access_record_query",
            "restore_user_scene",
            "merchant_exposure_query",
            "product_rule_issue",
        ):
            sop = self.loader.get_sop(intent)
            self.assertIsNotNone(sop)
            for tool_name in sop.tools:
                self.assertIn(tool_name, tool_names, msg=f"{intent} -> missing tool {tool_name}")


if __name__ == "__main__":
    unittest.main()
