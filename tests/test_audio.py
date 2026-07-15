import unittest

from countdownapp.audio import AudioService, should_play_return_bell


class FailingBackend:
    def play(self, path):
        raise RuntimeError("audio device unavailable")

    def stop(self):
        pass

    def close(self):
        pass


class AudioServiceTests(unittest.TestCase):
    def test_return_bell_only_plays_after_an_automatic_enabled_countdown(self):
        self.assertTrue(
            should_play_return_bell(countdown_enabled=True, completed_automatically=True)
        )
        self.assertFalse(
            should_play_return_bell(countdown_enabled=True, completed_automatically=False)
        )
        self.assertFalse(
            should_play_return_bell(countdown_enabled=False, completed_automatically=True)
        )

    def test_falls_back_after_retry_without_leaking_the_backend_error(self):
        fallbacks = []
        created = []

        def factory():
            created.append(True)
            return FailingBackend()

        service = AudioService(
            backend_factory=factory,
            fallback=lambda: fallbacks.append(True),
        )

        service.play("missing.mp3")

        self.assertEqual(2, len(created))
        self.assertEqual([True], fallbacks)


if __name__ == "__main__":
    unittest.main()
