import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from countdownapp.resources import install_dir, resource_path


class FrozenResourcePathTests(unittest.TestCase):
    def test_onefile_writes_user_data_beside_the_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "CountdownApp.exe"
            with patch.object(sys, "frozen", True, create=True), patch.object(
                sys, "executable", str(executable)
            ):
                self.assertEqual(executable.parent, install_dir())

    def test_onefile_reads_bundled_assets_from_the_temporary_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "_MEI12345"
            with patch.object(sys, "_MEIPASS", str(bundle), create=True):
                self.assertEqual(bundle / "0.wav", resource_path("0.wav"))


if __name__ == "__main__":
    unittest.main()
