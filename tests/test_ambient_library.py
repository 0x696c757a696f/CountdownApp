import unittest
from pathlib import Path

from countdownapp.ambient_library import build_ambient_plan, prepare_ambient


class AmbientLibraryTests(unittest.TestCase):
    def test_recording_is_separated_from_sources_that_require_synthesis(self):
        plan = build_ambient_plan(
            ("pink", "recording:storm", "tone:528"),
            resolve_resource=lambda name: Path("bundle") / name,
        )

        self.assertEqual(("pink", "tone:528"), plan.synthetic_sources)
        self.assertEqual(
            (Path("bundle") / "ambient_storm.ogg",),
            plan.recording_paths,
        )

    def test_recording_only_selection_needs_no_generated_pcm(self):
        prepared = prepare_ambient(
            ("recording:rain",),
            sample_rate=8_000,
            duration_sec=0.25,
            seed=42,
            resolve_resource=lambda name: Path("bundle") / name,
        )

        self.assertEqual(("recording:rain",), prepared.sources)
        self.assertEqual([], prepared.samples.tolist())
        self.assertEqual(8_000, prepared.sample_rate)
        self.assertEqual(
            (Path("bundle") / "ambient_rain.ogg",),
            prepared.recording_paths,
        )


if __name__ == "__main__":
    unittest.main()
