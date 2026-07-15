import unittest

from countdownapp.adaptive import AdaptiveReminderPolicy, AttentionFeedback


class AdaptiveReminderPolicyTests(unittest.TestCase):
    def test_two_distracted_reports_shorten_the_next_interval(self):
        policy = AdaptiveReminderPolicy(enabled=True)

        policy.record(AttentionFeedback.DISTRACTED)
        self.assertEqual(1.0, policy.consume_multiplier())
        policy.record(AttentionFeedback.DISTRACTED)

        self.assertEqual(0.75, policy.consume_multiplier())
        self.assertEqual(2, policy.summary.distracted_count)
        self.assertEqual(0, policy.summary.on_task_count)

    def test_three_on_task_reports_extend_the_next_interval(self):
        policy = AdaptiveReminderPolicy(enabled=True)

        for _ in range(2):
            policy.record(AttentionFeedback.ON_TASK)
            self.assertEqual(1.0, policy.consume_multiplier())
        policy.record(AttentionFeedback.ON_TASK)

        self.assertEqual(1.25, policy.consume_multiplier())
        self.assertEqual(3, policy.summary.on_task_count)

    def test_flow_feedback_delays_the_next_reminder_immediately(self):
        policy = AdaptiveReminderPolicy(enabled=True)

        policy.record(AttentionFeedback.FLOW)

        self.assertEqual(1.5, policy.consume_multiplier())
        self.assertEqual(1, policy.summary.flow_count)

    def test_disabled_policy_preserves_existing_timing(self):
        policy = AdaptiveReminderPolicy(enabled=False)

        policy.record(AttentionFeedback.DISTRACTED)
        policy.record(AttentionFeedback.DISTRACTED)

        self.assertEqual(1.0, policy.consume_multiplier())
        self.assertEqual(0, policy.summary.total_count)


if __name__ == "__main__":
    unittest.main()
