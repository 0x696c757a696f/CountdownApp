import unittest

from countdownapp.ambient import synthesize_mix, synthesize_mono


class AmbientSynthesisTests(unittest.TestCase):
    def test_recorded_textures_cannot_fall_back_to_noise_synthesis(self):
        for kind in (
            "recording:storm",
            "recording:rain",
            "texture:speech",
            "texture:rain",
            "texture:airflow",
        ):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                synthesize_mono(kind, sample_rate=8_000, duration_sec=0.5, seed=42)

    def test_noise_and_tone_can_be_synthesized_as_a_bounded_mix(self):
        noise = synthesize_mono(
            "pink", sample_rate=8_000, duration_sec=0.25, seed=42
        )
        tone = synthesize_mono(
            "tone:528", sample_rate=8_000, duration_sec=0.25, seed=42
        )

        mixed = synthesize_mix(
            ("pink", "tone:528"),
            sample_rate=8_000,
            duration_sec=0.25,
            seed=42,
        )

        self.assertEqual(2_000, len(mixed))
        self.assertLessEqual(max(abs(value) for value in mixed), 32_767)
        self.assertNotEqual(noise.tolist(), mixed.tolist())
        self.assertNotEqual(tone.tolist(), mixed.tolist())

    def test_noise_colours_are_bounded_distinct_and_deterministic(self):
        results = {
            kind: synthesize_mono(kind, sample_rate=8_000, duration_sec=0.25, seed=42)
            for kind in ("white", "pink", "brown", "grey")
        }

        for samples in results.values():
            self.assertEqual(2_000, len(samples))
            self.assertLessEqual(max(abs(value) for value in samples), 32_767)
        self.assertNotEqual(results["white"].tolist(), results["pink"].tolist())
        self.assertNotEqual(results["pink"].tolist(), results["brown"].tolist())
        self.assertNotEqual(results["pink"].tolist(), results["grey"].tolist())
        self.assertEqual(
            results["white"].tolist(),
            synthesize_mono(
                "white", sample_rate=8_000, duration_sec=0.25, seed=42
            ).tolist(),
        )

    def test_solfeggio_tone_uses_the_selected_frequency(self):
        samples = synthesize_mono(
            "tone:528", sample_rate=8_000, duration_sec=1.0, seed=1
        )
        positive_crossings = sum(
            1
            for previous, current in zip(samples, samples[1:])
            if previous <= 0 < current
        )

        self.assertIn(positive_crossings, range(527, 530))


if __name__ == "__main__":
    unittest.main()
