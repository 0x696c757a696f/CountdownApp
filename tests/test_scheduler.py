import unittest

from countdownapp.domain import AlgorithmMode, SessionSettings, V2Phase
from countdownapp.scheduler import EventKind, ReminderScheduler


class FixedRandom:
    def __init__(self, values):
        self._values = iter(values)

    def randint(self, minimum, maximum):
        value = next(self._values)
        if not minimum <= value <= maximum:
            raise AssertionError(f"{value} is outside [{minimum}, {maximum}]")
        return value


class ReminderSchedulerTests(unittest.TestCase):
    def test_v2_starts_with_a_random_reminder_in_attention_anchor_phase(self):
        settings = SessionSettings.defaults(
            focus_duration_sec=90 * 60,
            algorithm_mode=AlgorithmMode.V2,
        )
        scheduler = ReminderScheduler(settings, FixedRandom([6 * 60]))

        event = scheduler.next_event(active_elapsed_sec=0)

        self.assertEqual(EventKind.REMINDER_DUE, event.kind)
        self.assertEqual(6 * 60, event.due_active_sec)
        self.assertEqual(V2Phase.ATTENTION_ANCHOR, event.phase)

    def test_crossing_a_phase_boundary_resamples_in_the_new_phase(self):
        settings = SessionSettings.defaults(
            focus_duration_sec=90 * 60,
            algorithm_mode=AlgorithmMode.V2,
        )
        scheduler = ReminderScheduler(settings, FixedRandom([7 * 60, 12 * 60]))

        boundary = scheduler.next_event(active_elapsed_sec=29 * 60)
        after_boundary = scheduler.next_event(active_elapsed_sec=boundary.due_active_sec)

        self.assertEqual(EventKind.PHASE_CHANGED, boundary.kind)
        self.assertEqual(30 * 60, boundary.due_active_sec)
        self.assertEqual(EventKind.REMINDER_DUE, after_boundary.kind)
        self.assertEqual(42 * 60, after_boundary.due_active_sec)
        self.assertEqual(V2Phase.DEEP_FOCUS, after_boundary.phase)

    def test_a_candidate_after_the_focus_deadline_finishes_without_a_reminder(self):
        settings = SessionSettings.defaults(
            focus_duration_sec=90 * 60,
            algorithm_mode=AlgorithmMode.V2,
        )
        scheduler = ReminderScheduler(settings, FixedRandom([5 * 60]))

        event = scheduler.next_event(active_elapsed_sec=89 * 60)

        self.assertEqual(EventKind.SESSION_FINISHED, event.kind)
        self.assertEqual(90 * 60, event.due_active_sec)


if __name__ == "__main__":
    unittest.main()
