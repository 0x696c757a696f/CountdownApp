import unittest

from countdownapp.audio import AudioEngine, should_play_return_bell


class RecordingEngineBackend:
    def __init__(
        self,
        fail_bell=False,
        fail_ambient=False,
        fail_stop_bell=False,
        fail_volume=False,
        fail_pause=False,
    ):
        self.events = []
        self.fail_bell = fail_bell
        self.fail_ambient = fail_ambient
        self.fail_stop_bell = fail_stop_bell
        self.fail_volume = fail_volume
        self.fail_pause = fail_pause

    def play_bell(self, path):
        self.events.append(("play_bell", str(path)))
        if self.fail_bell:
            raise RuntimeError("audio device changed")

    def stop_bell(self):
        self.events.append(("stop_bell",))
        if self.fail_stop_bell:
            raise RuntimeError("audio device disappeared while stopping")

    def play_ambient(self, sources, volume):
        self.events.append(("play_ambient", sources, volume))
        if self.fail_ambient:
            raise RuntimeError("ambient device changed")

    def set_ambient_volume(self, volume):
        self.events.append(("ambient_volume", volume))
        if self.fail_volume:
            raise RuntimeError("audio device disappeared while changing volume")

    def pause_ambient(self):
        self.events.append(("pause_ambient",))
        if self.fail_pause:
            raise RuntimeError("audio device disappeared while pausing")

    def resume_ambient(self):
        self.events.append(("resume_ambient",))

    def stop_ambient(self):
        self.events.append(("stop_ambient",))

    def close(self):
        self.events.append(("close",))


class AudioEngineTests(unittest.TestCase):
    def test_bell_temporarily_ducks_and_then_restores_ambient_audio(self):
        backend = RecordingEngineBackend()
        engine = AudioEngine(backend_factory=lambda: backend, ducking_ratio=0.25)

        engine.play_ambient("pink", "tone:528", 0.4)
        played = engine.play_bell("start.wav")
        engine.stop_bell()

        self.assertIs(played, True)
        self.assertEqual(
            [
                ("play_ambient", ("pink", "tone:528"), 0.4),
                ("ambient_volume", 0.1),
                ("play_bell", "start.wav"),
                ("stop_bell",),
                ("ambient_volume", 0.4),
            ],
            backend.events,
        )

    def test_volume_changes_remain_ducked_while_a_bell_is_active(self):
        backend = RecordingEngineBackend()
        engine = AudioEngine(backend_factory=lambda: backend, ducking_ratio=0.25)
        engine.play_ambient("pink", "off", 0.4)
        engine.play_bell("start.wav")

        engine.set_ambient_volume(0.6)
        engine.stop_bell()

        self.assertEqual(
            [
                ("ambient_volume", 0.1),
                ("ambient_volume", 0.15),
                ("ambient_volume", 0.6),
            ],
            [event for event in backend.events if event[0] == "ambient_volume"],
        )

    def test_engine_owns_the_complete_ambient_lifecycle(self):
        backend = RecordingEngineBackend()
        engine = AudioEngine(backend_factory=lambda: backend)

        engine.play_ambient("brown", "off", 0.2)
        engine.set_ambient_volume(0.3)
        engine.pause_ambient()
        engine.resume_ambient()
        engine.stop_ambient()
        engine.close()

        self.assertEqual(
            [
                ("play_ambient", ("brown",), 0.2),
                ("ambient_volume", 0.3),
                ("pause_ambient",),
                ("resume_ambient",),
                ("stop_ambient",),
                ("close",),
            ],
            backend.events,
        )

    def test_bell_retry_recreates_one_backend_and_restores_ambient(self):
        backends = [RecordingEngineBackend(fail_bell=True), RecordingEngineBackend()]
        created = []

        def factory():
            backend = backends[len(created)]
            created.append(backend)
            return backend

        engine = AudioEngine(backend_factory=factory, ducking_ratio=0.25)
        engine.play_ambient("pink", "off", 0.4)

        engine.play_bell("start.wav")
        engine.stop_bell()

        self.assertEqual(2, len(created))
        self.assertEqual(("close",), backends[0].events[-1])
        self.assertEqual(
            [
                ("play_ambient", ("pink",), 0.4),
                ("ambient_volume", 0.1),
                ("play_bell", "start.wav"),
                ("stop_bell",),
                ("ambient_volume", 0.4),
            ],
            backends[1].events,
        )

    def test_ambient_retry_recreates_the_shared_backend(self):
        backends = [
            RecordingEngineBackend(fail_ambient=True),
            RecordingEngineBackend(),
        ]
        created = []

        def factory():
            backend = backends[len(created)]
            created.append(backend)
            return backend

        engine = AudioEngine(backend_factory=factory)

        played = engine.play_ambient("grey", "off", 0.2)

        self.assertIs(played, True)
        self.assertEqual(2, len(created))
        self.assertEqual(("close",), backends[0].events[-1])
        self.assertEqual(
            [("play_ambient", ("grey",), 0.2)], backends[1].events
        )

    def test_ambient_failure_is_reported_to_the_caller(self):
        engine = AudioEngine(
            backend_factory=lambda: RecordingEngineBackend(fail_ambient=True)
        )

        played = engine.play_ambient("pink", "tone:174", 0.2)

        self.assertIs(played, False)

    def test_stop_failure_does_not_escape_and_restores_ambient(self):
        backends = [
            RecordingEngineBackend(fail_stop_bell=True),
            RecordingEngineBackend(),
        ]
        created = []

        def factory():
            backend = backends[len(created)]
            created.append(backend)
            return backend

        engine = AudioEngine(backend_factory=factory)
        engine.play_ambient("pink", "off", 0.2)
        engine.play_bell("start.wav")

        engine.stop_bell()

        self.assertEqual(2, len(created))
        self.assertEqual(
            [("play_ambient", ("pink",), 0.2)], backends[1].events
        )

    def test_volume_failure_recreates_backend_at_the_new_volume(self):
        backends = [
            RecordingEngineBackend(fail_volume=True),
            RecordingEngineBackend(),
        ]
        created = []

        def factory():
            backend = backends[len(created)]
            created.append(backend)
            return backend

        engine = AudioEngine(backend_factory=factory)
        engine.play_ambient("grey", "off", 0.2)

        engine.set_ambient_volume(0.4)

        self.assertEqual(
            [("play_ambient", ("grey",), 0.4)], backends[1].events
        )

    def test_pause_failure_restores_the_background_in_a_paused_state(self):
        backends = [
            RecordingEngineBackend(fail_pause=True),
            RecordingEngineBackend(),
        ]
        created = []

        def factory():
            backend = backends[len(created)]
            created.append(backend)
            return backend

        engine = AudioEngine(backend_factory=factory)
        engine.play_ambient("brown", "off", 0.2)

        engine.pause_ambient()

        self.assertEqual(
            [
                ("play_ambient", ("brown",), 0.2),
                ("pause_ambient",),
            ],
            backends[1].events,
        )

    def test_turning_both_ambient_layers_off_stops_the_existing_loop(self):
        backend = RecordingEngineBackend()
        engine = AudioEngine(backend_factory=lambda: backend)
        engine.play_ambient("white", "off", 0.2)

        engine.play_ambient("off", "off", 0.2)

        self.assertEqual(("stop_ambient",), backend.events[-1])

    def test_stopping_an_idle_engine_does_not_initialize_the_audio_device(self):
        created = []
        engine = AudioEngine(
            backend_factory=lambda: created.append(True) or RecordingEngineBackend()
        )

        engine.stop_bell()
        engine.stop_ambient()
        engine.close()

        self.assertEqual([], created)

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
            backend = RecordingEngineBackend(fail_bell=True)
            created.append(backend)
            return backend

        engine = AudioEngine(
            backend_factory=factory,
            fallback=lambda: fallbacks.append(True),
        )
        engine.play_ambient("brown", "off", 0.2)

        played = engine.play_bell("missing.mp3")

        self.assertIs(played, False)
        self.assertEqual(3, len(created))
        self.assertEqual([True], fallbacks)
        self.assertEqual(
            [("play_ambient", ("brown",), 0.2)], created[2].events
        )


if __name__ == "__main__":
    unittest.main()
