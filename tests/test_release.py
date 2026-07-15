import re
import unittest
from pathlib import Path

from countdownapp import __version__


class ReleaseMetadataTests(unittest.TestCase):
    def test_spec_builds_one_self_extracting_executable(self):
        project_root = Path(__file__).resolve().parents[1]
        spec = (project_root / "countdown_app.spec").read_text(encoding="utf-8")

        self.assertNotIn("COLLECT(", spec)
        self.assertNotIn("exclude_binaries=True", spec)
        self.assertIn("a.binaries,", spec)
        self.assertIn("a.datas,", spec)

    def test_package_and_windows_resource_versions_match(self):
        project_root = Path(__file__).resolve().parents[1]
        version_resource = (project_root / "version_info.txt").read_text(
            encoding="utf-8"
        )
        resource_versions = set(
            re.findall(r'StringStruct\("(?:File|Product)Version", "([^"]+)"\)', version_resource)
        )

        self.assertEqual({__version__}, resource_versions)
        self.assertIn('version=str(root / "version_info.txt")', (project_root / "countdown_app.spec").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
