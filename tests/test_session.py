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
    def test_exposes_next_reminder_as_remaining_active_time(self):
        clock = FakeClock()
        defaults = SessionSettings.defaults(
            focus_duration_sec=20 * 60,
            algorithm_mode=AlgorithmMode.CLASSIC,
        )
        settings = replace(defaults, classic_interval=IntervalRange(60, 60))
        session = FocusSession(settings, FixedRandom([60]), clock.now)

        session.start()
        self.assertEqual(60, session.next_reminder_remaining_sec)
        clock.advance(10)
        session.tick()

        self.assertEqual(50, session.next_reminder_remaining_sec)

    def test_does_not_claim_a_reminder_time_when_phase_change_comes_first(self):
        clock = FakeClock()
        defaults = SessionSettings.defaults(
            focus_duration_sec=90 * 60,
            algorithm_mode=AlgorithmMode.V2,
        )
        settings = replace(
            defaults,
            v2=replace(
                defaults.v2,
                anchor_end_sec=20 * 60,
                anchor_interval=IntervalRange(30 * 60, 30 * 60),
            ),
        )
        session = FocusSession(settings, FixedRandom([30 * 60]), clock.now)

        session.start()

        self.assertIsNone(session.next_reminder_remaining_sec)

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

    def test_long_break_uses_the_same_monotonic_session_clock(self):
        clock = FakeClock()
        defaults = SessionSettings.defaults(
            focus_duration_sec=60,
            algorithm_mode=AlgorithmMode.CLASSIC,
        )
        settings = replace(defaults, classic_interval=IntervalRange(90, 90))
        session = FocusSession(settings, FixedRandom([90]), clock.now)
        session.start()
        for _ in range(6):
            clock.advance(10)
            session.tick()

        session.start_long_break(20)
        clock.advance(19)
        self.assertEqual([], session.tick())
        self.assertEqual(1, session.long_break_remaining_sec)
        clock.advance(1)

        events = session.tick()

        self.assertEqual(SessionState.IDLE, session.state)
        self.assertEqual(
            [RuntimeEventKind.LONG_BREAK_FINISHED],
            [event.kind for event in events],
        )
        self.assertEqual([], session.tick())

    def test_long_break_pause_preserves_its_remaining_time_and_context(self):
        clock = FakeClock()
        defaults = SessionSettings.defaults(
            focus_duration_sec=60,
            algorithm_mode=AlgorithmMode.CLASSIC,
        )
        settings = replace(defaults, classic_interval=IntervalRange(90, 90))
        session = FocusSession(settings, FixedRandom([90]), clock.now)
        session.start()
        for _ in range(6):
            clock.advance(10)
            session.tick()
        session.start_long_break(20)
        clock.advance(5)
        session.tick()

        session.pause()
        clock.advance(100)
        self.assertEqual([], session.tick())

        self.assertEqual(SessionState.PAUSED, session.state)
        self.assertTrue(session.is_long_break)
        self.assertEqual(15, session.long_break_remaining_sec)
        session.resume()
        self.assertEqual(SessionState.LONG_BREAK, session.state)
        clock.advance(15)
        events = session.tick()
        self.assertEqual(
            [RuntimeEventKind.LONG_BREAK_FINISHED],
            [event.kind for event in events],
        )
        self.assertEqual(SessionState.IDLE, session.state)

    def test_shutdown_is_a_session_transition_not_a_gui_state_write(self):
        clock = FakeClock()
        settings = SessionSettings.defaults(
            focus_duration_sec=20 * 60,
            algorithm_mode=AlgorithmMode.CLASSIC,
        )
        session = FocusSession(settings, FixedRandom([180]), clock.now)
        session.start()

        session.shutdown()

        self.assertEqual(SessionState.SHUTTING_DOWN, session.state)
        self.assertEqual([], session.tick())
        self.assertFalse(session.reminder_visible)


if __name__ == "__main__":
    unittest.main()
