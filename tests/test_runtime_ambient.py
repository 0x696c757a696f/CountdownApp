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

    def request(self, sources, volume, on_complete=None):
        self.events.append(("request", sources, volume))
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


class SettingsFormStub:
    def __init__(self, ambient, texture, solfeggio):
        self.ambient = ambient
        self.ambient_texture = texture
        self.solfeggio = solfeggio

    @property
    def ambient_value(self):
        return {
            "关闭": "off",
            "粉红噪音": "pink",
        }.get(self.ambient.get(), "off")

    @property
    def solfeggio_value(self):
        return {
            "关闭": "off",
            "索尔费吉奥 528 赫兹": "tone:528",
        }.get(self.solfeggio.get(), "off")

    @property
    def ambient_texture_value(self):
        return {
            "关闭": "off",
            "风雨雷暴": "recording:storm",
        }.get(self.ambient_texture.get(), "off")

    @property
    def ambient_sources(self):
        return tuple(
            source
            for source in (
                self.ambient_value,
                self.ambient_texture_value,
                self.solfeggio_value,
            )
            if source != "off"
        )


class RuntimeAmbientTests(unittest.TestCase):
    @staticmethod
    def make_app(state=SessionState.FOCUSING, play_result=True):
        app = CountdownApp.__new__(CountdownApp)
        app.audio = AudioStub(play_result)
        app.ambient_tasks = AmbientTaskStub(play_result)
        app.store = StoreStub()
        app.app_settings = AppSettings()
        app.focus = SimpleNamespace(state=state)
        app.ambient_var = ValueStub("粉红噪音")
        app.ambient_texture_var = ValueStub("风雨雷暴")
        app.solfeggio_var = ValueStub("索尔费吉奥 528 赫兹")
        app.settings_form = SettingsFormStub(
            app.ambient_var,
            app.ambient_texture_var,
            app.solfeggio_var,
        )
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
            [("request", ("pink", "recording:storm", "tone:528"), 0.35)],
            app.ambient_tasks.events,
        )
        self.assertEqual([], app.audio.events)
        self.assertEqual("pink", app.app_settings.ambient_choice)
        self.assertEqual(
            "recording:storm", app.app_settings.ambient_texture_choice
        )
        self.assertEqual("tone:528", app.app_settings.solfeggio_choice)
        self.assertEqual(35, app.app_settings.ambient_volume)
        self.assertEqual([app.app_settings], app.store.saved)
        self.assertEqual(
            "粉红噪音 + 风雨雷暴 + 索尔费吉奥 528 赫兹 · 35%",
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
        app.ambient_texture_var.set("关闭")
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
