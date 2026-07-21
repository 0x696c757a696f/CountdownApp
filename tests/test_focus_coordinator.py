import unittest
from dataclasses import replace

from countdownapp.domain import (
    AlgorithmMode,
    IntervalRange,
    SessionSettings,
    SessionState,
)
from countdownapp.focus_coordinator import FocusCoordinator
from countdownapp.session import RuntimeEventKind


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def now(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class FixedRandom:
    def __init__(self, values):
        self.values = iter(values)

    def randint(self, minimum, maximum):
        value = next(self.values)
        if not minimum <= value <= maximum:
            raise AssertionError(f"{value} is outside {minimum}..{maximum}")
        return value


class FocusCoordinatorTests(unittest.TestCase):
    @staticmethod
    def settings():
        return replace(
            SessionSettings.defaults(
                focus_duration_sec=2 * 60,
                algorithm_mode=AlgorithmMode.CLASSIC,
            ),
            classic_interval=IntervalRange(60, 60),
        )

    def test_start_exposes_the_initial_runtime_display_and_generation(self):
        clock = FakeClock()
        coordinator = FocusCoordinator(FixedRandom([60]), clock.now)

        generation = coordinator.start(self.settings(), show_next_reminder=False)

        self.assertEqual(1, generation)
        self.assertEqual("02:00", coordinator.display.timer)
        self.assertEqual("经典随机", coordinator.display.phase)
        self.assertIn("1 分钟", coordinator.display.interval)
        self.assertNotIn("下次提醒", coordinator.display.interval)

    def test_tick_returns_events_display_and_whether_to_continue(self):
        clock = FakeClock()
        coordinator = FocusCoordinator(FixedRandom([60]), clock.now)
        generation = coordinator.start(self.settings(), show_next_reminder=False)
        for _ in range(6):
            clock.advance(10)
            update = coordinator.tick(generation)

        self.assertEqual(
            [RuntimeEventKind.REMINDER_DUE],
            [event.kind for event in update.events],
        )
        self.assertEqual("01:00", update.display.timer)
        self.assertTrue(update.should_continue)
        self.assertIsNone(coordinator.tick(generation - 1))

    def test_toggle_pause_reports_side_effects_without_performing_them(self):
        clock = FakeClock()
        coordinator = FocusCoordinator(FixedRandom([60, 60]), clock.now)
        coordinator.start(self.settings(), show_next_reminder=False)
        for _ in range(6):
            clock.advance(10)
            coordinator.tick(1)

        paused = coordinator.toggle_pause()
        resumed = coordinator.toggle_pause()

        self.assertTrue(paused.paused)
        self.assertTrue(paused.reminder_was_visible)
        self.assertFalse(paused.long_break)
        self.assertIn("已暂停", paused.display.phase)
        self.assertFalse(resumed.paused)
        self.assertEqual(SessionState.FOCUSING, coordinator.state)

    def test_long_break_uses_the_same_tick_and_display_contract(self):
        clock = FakeClock()
        settings = replace(
            self.settings(),
            focus_duration_sec=30,
            classic_interval=IntervalRange(60, 60),
        )
        coordinator = FocusCoordinator(FixedRandom([60]), clock.now)
        generation = coordinator.start(settings, show_next_reminder=False)
        for _ in range(3):
            clock.advance(10)
            update = coordinator.tick(generation)
        self.assertEqual(SessionState.BREAK_PROMPT, coordinator.state)

        display = coordinator.start_long_break(20)
        clock.advance(5)
        update = coordinator.tick(generation)

        self.assertEqual("00:20", display.timer)
        self.assertEqual("00:15", update.display.timer)
        self.assertTrue(update.long_break)
        self.assertTrue(update.should_continue)

    def test_stop_invalidates_pending_ticks(self):
        coordinator = FocusCoordinator(FixedRandom([60]), FakeClock().now)
        generation = coordinator.start(self.settings(), show_next_reminder=False)

        coordinator.stop()

        self.assertEqual(SessionState.IDLE, coordinator.state)
        self.assertIsNone(coordinator.settings)
        self.assertIsNone(coordinator.tick(generation))


if __name__ == "__main__":
    unittest.main()
