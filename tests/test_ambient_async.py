import unittest
from array import array

from countdownapp.ambient_async import AsyncAmbientController, PreparedAmbient


class ManualFuture:
    def __init__(self):
        self.callbacks = []
        self.value = None
        self.error = None

    def add_done_callback(self, callback):
        self.callbacks.append(callback)

    def cancel(self):
        return False

    def result(self):
        if self.error is not None:
            raise self.error
        return self.value

    def complete(self, value=None, error=None):
        self.value = value
        self.error = error
        for callback in tuple(self.callbacks):
            callback(self)


class ManualExecutor:
    def __init__(self):
        self.futures = []
        self.shutdown_called = False

    def submit(self, _function, *_args):
        future = ManualFuture()
        self.futures.append(future)
        return future

    def shutdown(self, wait=False, cancel_futures=False):
        self.shutdown_called = True


class AsyncAmbientControllerTests(unittest.TestCase):
    def test_only_the_latest_completed_selection_is_played(self):
        executor = ManualExecutor()
        dispatched = []
        played = []
        completed = []
        controller = AsyncAmbientController(
            player=lambda prepared, volume: played.append(
                (prepared.sources, volume)
            )
            or True,
            dispatch=dispatched.append,
            executor=executor,
        )

        controller.request(("pink",), 0.2, completed.append)
        controller.request(
            ("brown", "recording:rain", "tone:528"),
            0.35,
            completed.append,
        )
        executor.futures[0].complete(
            PreparedAmbient(("pink",), array("h", [1]), 44_100)
        )
        executor.futures[1].complete(
            PreparedAmbient(
                ("brown", "recording:rain", "tone:528"),
                array("h", [2]),
                44_100,
            )
        )

        self.assertEqual(1, len(dispatched))
        dispatched.pop()()
        self.assertEqual(
            [(("brown", "recording:rain", "tone:528"), 0.35)], played
        )
        self.assertEqual([True], completed)

    def test_cancel_prevents_a_pending_mix_from_starting_later(self):
        executor = ManualExecutor()
        dispatched = []
        played = []
        controller = AsyncAmbientController(
            player=lambda prepared, volume: played.append((prepared, volume)) or True,
            dispatch=dispatched.append,
            executor=executor,
        )

        controller.request(("grey", "tone:174"), 0.2)
        controller.cancel()
        executor.futures[0].complete(
            PreparedAmbient(("grey", "tone:174"), array("h", [1]), 44_100)
        )

        self.assertEqual([], dispatched)
        self.assertEqual([], played)

    def test_volume_changed_while_rendering_is_used_when_playback_starts(self):
        executor = ManualExecutor()
        dispatched = []
        played = []
        controller = AsyncAmbientController(
            player=lambda prepared, volume: played.append(volume) or True,
            dispatch=dispatched.append,
            executor=executor,
        )

        controller.request(("pink",), 0.2)
        controller.set_volume(0.55)
        executor.futures[0].complete(
            PreparedAmbient(("pink",), array("h", [1]), 44_100)
        )
        dispatched.pop()()

        self.assertEqual([0.55], played)

    def test_render_failure_reports_failure_without_calling_the_player(self):
        executor = ManualExecutor()
        dispatched = []
        played = []
        completed = []
        controller = AsyncAmbientController(
            player=lambda prepared, volume: played.append((prepared, volume)) or True,
            dispatch=dispatched.append,
            executor=executor,
        )

        controller.request(("white",), 0.2, completed.append)
        executor.futures[0].complete(error=RuntimeError("render failed"))

        dispatched.pop()()
        self.assertEqual([], played)
        self.assertEqual([False], completed)


if __name__ == "__main__":
    unittest.main()
