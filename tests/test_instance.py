"""What a running copy says about itself to run.bat."""

import os
import unittest
from unittest import mock

from parkour import config, extract, instance, transfer


class WhoAmI(unittest.TestCase):
    def test_names_the_app_its_folder_and_its_process(self):
        from app import app
        told = app.test_client().get("/whoami").get_json()
        self.assertEqual(told["app"], instance.NAME)
        self.assertEqual(told["folder"], str(config.ROOT))
        self.assertEqual(told["pid"], os.getpid())
        self.assertEqual(told["busy"], "")

    def test_says_what_slow_work_is_under_way(self):
        with mock.patch.object(extract._progress, "state", "running"), \
             mock.patch.object(transfer._progress, "state", "running"), \
             mock.patch.object(transfer._progress, "kind", "upload"):
            self.assertEqual(instance.busy(), "generating clips and uploading clips")


if __name__ == "__main__":
    unittest.main()
