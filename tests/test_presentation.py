import unittest

from countdownapp.adaptive import FeedbackSummary
from countdownapp.presentation import (
    RenderCache,
    format_feedback_summary,
    format_reminder_status,
)


class RenderCacheTests(unittest.TestCase):
    def test_only_renders_when_a_display_value_changes(self):
        rendered = []
        cache = RenderCache()

        self.assertTrue(cache.update("timer", "09:59", rendered.append))
        self.assertFalse(cache.update("timer", "09:59", rendered.append))
        self.assertTrue(cache.update("timer", "09:58", rendered.append))

        self.assertEqual(["09:59", "09:58"], rendered)

    def test_invalidate_forces_the_next_render(self):
        rendered = []
        cache = RenderCache()
        cache.update("phase", "深度专注期", rendered.append)

        cache.invalidate()

        self.assertTrue(cache.update("phase", "深度专注期", rendered.append))
        self.assertEqual(["深度专注期", "深度专注期"], rendered)


class ReminderStatusTests(unittest.TestCase):
    def test_exact_reminder_time_is_masked_by_default(self):
        text = format_reminder_status(180, 300, False, 245)

        self.assertEqual("当前随机区间：3–5 分钟", text)

    def test_user_can_reveal_the_next_reminder_countdown(self):
        text = format_reminder_status(180, 300, True, 245)

        self.assertEqual("当前随机区间：3–5 分钟 ｜ 下次提醒约 04:05 后", text)

    def test_phase_boundary_is_not_misrepresented_as_a_reminder(self):
        text = format_reminder_status(240, 420, True, None)

        self.assertEqual("当前随机区间：4–7 分钟 ｜ 阶段切换后重新抽取", text)

    def test_adaptive_mode_labels_the_configured_range_as_the_base_range(self):
        text = format_reminder_status(180, 300, False, 245, adaptive_enabled=True)

        self.assertEqual("当前基础随机区间：3–5 分钟 ｜ 自适应反馈开启", text)


class FeedbackSummaryTests(unittest.TestCase):
    def test_hidden_when_adaptive_feedback_is_disabled(self):
        self.assertEqual("", format_feedback_summary(FeedbackSummary(), False))

    def test_formats_cycle_feedback_counts(self):
        summary = FeedbackSummary(on_task_count=3, distracted_count=2, flow_count=1)

        self.assertEqual(
            "本轮反馈：仍在任务 3 · 走神 2 · 心流延后 1",
            format_feedback_summary(summary, True),
        )


if __name__ == "__main__":
    unittest.main()
