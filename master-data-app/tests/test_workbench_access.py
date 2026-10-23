import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

SOURCE_DIR = Path(__file__).resolve().parents[1] / "src"
os.environ.setdefault("MASTER_DATA_CATALOG", "automation_d")
sys.path.insert(0, str(SOURCE_DIR))

from portal.core.identity import is_master_data_member, master_data_emails  # noqa: E402

RULES = {
    "members": pd.DataFrame(
        [
            {"member_id": "MDM001", "email": "Anna.Member@etexgroup.com", "active": "Y"},
            {"member_id": "MDM002", "email": "left.team@etexgroup.com", "active": "N"},
        ]
    )
}


class WorkbenchAccessTests(unittest.TestCase):
    def test_active_members_may_open_the_workbench(self):
        self.assertTrue(is_master_data_member("anna.member@etexgroup.com", RULES))  # case-insensitive

    def test_inactive_members_and_others_may_not(self):
        self.assertFalse(is_master_data_member("left.team@etexgroup.com", RULES))
        self.assertFalse(is_master_data_member("requester@etexgroup.com", RULES))
        self.assertFalse(is_master_data_member("", RULES))

    def test_extra_admins_from_the_environment(self):
        with patch.dict(os.environ, {"WORKBENCH_ADMINS": "admin.one@etexgroup.com, Admin.Two@etexgroup.com"}):
            emails = master_data_emails(RULES)
            self.assertIn("admin.two@etexgroup.com", emails)
            self.assertTrue(is_master_data_member("admin.one@etexgroup.com", RULES))


if __name__ == "__main__":
    unittest.main()
