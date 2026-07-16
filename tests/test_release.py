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

    def test_spec_excludes_optional_image_codecs_unused_by_the_tray_icon(self):
        project_root = Path(__file__).resolve().parents[1]
        spec = (project_root / "countdown_app.spec").read_text(encoding="utf-8")

        for module in (
            "PIL._avif",
            "PIL._webp",
            "PIL._imagingcms",
            "PIL._imagingmath",
            "PIL._imagingtk",
        ):
            self.assertIn(f'"{module}"', spec)

    def test_spec_bundles_both_environment_recordings(self):
        project_root = Path(__file__).resolve().parents[1]
        spec = (project_root / "countdown_app.spec").read_text(encoding="utf-8")

        for filename in ("ambient_storm.ogg", "ambient_rain.ogg"):
            self.assertTrue((project_root / filename).is_file())
            self.assertIn(f'root / "{filename}"', spec)

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
