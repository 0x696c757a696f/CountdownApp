import unittest
from types import SimpleNamespace
from unittest.mock import patch

from countdownapp.app import CountdownApp
from countdownapp.config import AppSettings
from countdownapp.domain import SessionState


class ValueStub:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class AudioStub:
    def __init__(self, play_result=True):
        self.events = []
        self.play_result = play_result

    def play_ambient(self, noise, tone, volume):
        self.events.append(("play", noise, tone, volume))
        return self.play_result

    def pause_ambient(self):
        self.events.append(("pause",))

    def stop_ambient(self):
        self.events.append(("stop",))


class AmbientTaskStub:
    def __init__(self, play_result=True):
        self.events = []
        self.play_result = play_result

    def request(self, noise, tone, volume, on_complete=None):
        self.events.append(("request", noise, tone, volume))
        if on_complete is not None:
            on_complete(self.play_result)

    def cancel(self):
        self.events.append(("cancel",))

    def set_volume(self, volume):
        self.events.append(("volume", volume))


class StoreStub:
    def __init__(self):
        self.saved = []

    def save(self, settings):
        self.saved.append(settings)


class RuntimeAmbientTests(unittest.TestCase):
    @staticmethod
    def make_app(state=SessionState.FOCUSING, play_result=True):
        app = CountdownApp.__new__(CountdownApp)
        app.audio = AudioStub(play_result)
        app.ambient_tasks = AmbientTaskStub(play_result)
        app.store = StoreStub()
        app.app_settings = AppSettings()
        app.session = SimpleNamespace(state=state)
        app.ambient_var = ValueStub("粉红噪音")
        app.solfeggio_var = ValueStub("Solfeggio 528 Hz")
        app.ambient_volume_var = ValueStub(35)
        app.ambient_volume_label_var = ValueStub("")
        app.runtime_summary = ValueStub("")
        app.runtime_view = SimpleNamespace(
            set_ambient_summary=app.runtime_summary.set
        )
        return app

    def test_runtime_selection_applies_immediately_and_becomes_the_default(self):
        app = self.make_app()

        app._apply_runtime_ambient()

        self.assertEqual(
            [("request", "pink", "tone:528", 0.35)],
            app.ambient_tasks.events,
        )
        self.assertEqual([], app.audio.events)
        self.assertEqual("pink", app.app_settings.ambient_choice)
        self.assertEqual("tone:528", app.app_settings.solfeggio_choice)
        self.assertEqual(35, app.app_settings.ambient_volume)
        self.assertEqual([app.app_settings], app.store.saved)
        self.assertEqual(
            "粉红噪音 + Solfeggio 528 Hz · 35%",
            app.runtime_summary.get(),
        )

    def test_changing_the_mix_while_paused_does_not_resume_audio(self):
        app = self.make_app(SessionState.PAUSED)

        app._apply_runtime_ambient()

        self.assertEqual(
            [("pause",)],
            app.audio.events,
        )

    def test_turning_background_audio_off_cancels_pending_rendering(self):
        app = self.make_app()
        app.ambient_var.set("关闭")
        app.solfeggio_var.set("关闭")

        app._apply_runtime_ambient()

        self.assertEqual([("cancel",)], app.ambient_tasks.events)
        self.assertEqual([("stop",)], app.audio.events)

    def test_failed_runtime_playback_is_visible_instead_of_claiming_success(self):
        app = self.make_app(play_result=False)

        with patch("countdownapp.app.messagebox.showwarning") as warning:
            app._apply_runtime_ambient()

        warning.assert_called_once()
        self.assertIn("播放失败", app.runtime_summary.get())


if __name__ == "__main__":
    unittest.main()
