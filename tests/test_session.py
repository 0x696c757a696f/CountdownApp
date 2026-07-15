import unittest
from dataclasses import replace

from countdownapp.domain import AlgorithmMode, IntervalRange, SessionSettings, SessionState
from countdownapp.session import FocusSession, RuntimeEventKind

from .test_scheduler import FixedRandom


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def now(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class FocusSessionTests(unittest.TestCase):
    def test_manual_pause_preserves_the_pending_reminder(self):
        clock = FakeClock()
        settings = SessionSettings.defaults(
            focus_duration_sec=20 * 60,
            algorithm_mode=AlgorithmMode.CLASSIC,
        )
        settings = SessionSettings(
            **{
                **settings.__dict__,
                "classic_interval": type(settings.classic_interval)(60, 60),
            }
        )
        session = FocusSession(settings, FixedRandom([60, 60]), clock.now)

        session.start()
        for _ in range(3):
            clock.advance(10)
            self.assertEqual([], session.tick())
        session.pause()
        clock.advance(10 * 60)
        self.assertEqual([], session.tick())
        session.resume()
        for seconds in (10, 10, 9):
            clock.advance(seconds)
            self.assertEqual([], session.tick())
        clock.advance(1)

        events = session.tick()

        self.assertEqual(SessionState.FOCUSING, session.state)
        self.assertEqual([RuntimeEventKind.REMINDER_DUE], [event.kind for event in events])
        self.assertEqual(60, session.active_elapsed_sec)

    def test_long_callback_gap_auto_pauses_without_counting_the_gap(self):
        clock = FakeClock()
        settings = SessionSettings.defaults(
            focus_duration_sec=20 * 60,
            algorithm_mode=AlgorithmMode.CLASSIC,
        )
        session = FocusSession(settings, FixedRandom([3 * 60, 3 * 60]), clock.now)
        session.start()

        clock.advance(11)
        events = session.tick()

        self.assertEqual(SessionState.PAUSED, session.state)
        self.assertEqual(0, session.active_elapsed_sec)
        self.assertEqual(
            [RuntimeEventKind.SUSPEND_DETECTED], [event.kind for event in events]
        )

    def test_focus_deadline_wins_and_is_emitted_only_once(self):
        clock = FakeClock()
        defaults = SessionSettings.defaults(
            focus_duration_sec=60,
            algorithm_mode=AlgorithmMode.CLASSIC,
        )
        settings = replace(defaults, classic_interval=IntervalRange(90, 90))
        session = FocusSession(settings, FixedRandom([90]), clock.now)
        session.start()

        events = []
        for _ in range(6):
            clock.advance(10)
            events.extend(session.tick())

        self.assertEqual(SessionState.BREAK_PROMPT, session.state)
        self.assertEqual(
            [RuntimeEventKind.SESSION_FINISHED], [event.kind for event in events]
        )
        self.assertEqual([], session.tick())


if __name__ == "__main__":
    unittest.main()
