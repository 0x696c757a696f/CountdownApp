import unittest

from countdownapp.adaptive import FeedbackSummary
from countdownapp.presentation import (
    RenderCache,
    format_ambient_summary,
    format_feedback_summary,
    format_reminder_status,
    responsive_window_layout,
    runtime_window_layout,
    scaled_scrollbar_width,
    scroll_fraction_to_reveal,
    v2_window_layout,
    window_ui_scale,
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
            "本轮反馈：仍在任务 3 · 走神 2 · 延后下次提醒 1",
            format_feedback_summary(summary, True),
        )


class AmbientSummaryTests(unittest.TestCase):
    def test_summarizes_a_runtime_background_audio_mix(self):
        self.assertEqual(
            "粉红噪音 + 风雨雷暴 + Solfeggio 528 Hz · 20%",
            format_ambient_summary(
                ("pink", "recording:storm", "tone:528"), 20
            ),
        )
        self.assertEqual("已关闭", format_ambient_summary(("off",), 20))


class ResponsiveWindowLayoutTests(unittest.TestCase):
    def test_scrollbar_stays_easy_to_grab_at_high_dpi(self):
        self.assertEqual(18, scaled_scrollbar_width(1.0))
        self.assertEqual(28, scaled_scrollbar_width(1.75))

    def test_high_dpi_scales_width_and_uses_measured_content_height(self):
        layout = responsive_window_layout(
            2560,
            1600,
            ui_scale=1.75,
            minimum_content_height=731,
        )

        self.assertEqual((1260, 731), (layout.width, layout.height))
        self.assertEqual((1120, 540), (layout.min_width, layout.min_height))
        self.assertEqual((650, 434), (layout.x, layout.y))

    def test_reads_the_tk_display_scale_relative_to_96_dpi(self):
        class WindowStub:
            def winfo_fpixels(self, value):
                self.requested = value
                return 168

        window = WindowStub()

        self.assertEqual(1.75, window_ui_scale(window))
        self.assertEqual("1i", window.requested)

    def test_leaves_vertical_room_around_the_window(self):
        layout = responsive_window_layout(1463, 914)

        self.assertEqual((720, 690), (layout.width, layout.height))
        self.assertEqual((371, 112), (layout.x, layout.y))
        self.assertLessEqual(layout.height, 914 - 140)

    def test_shrinks_for_a_small_display_instead_of_clipping(self):
        layout = responsive_window_layout(800, 600)

        self.assertEqual((720, 460), (layout.width, layout.height))
        self.assertEqual((640, 460), (layout.min_width, layout.min_height))
        self.assertEqual("720x460+40+70", layout.geometry)

    def test_scrolls_an_expanded_section_near_the_top_of_the_viewport(self):
        self.assertAlmostEqual(0.584, scroll_fraction_to_reveal(900, 1500), places=3)
        self.assertEqual(0.0, scroll_fraction_to_reveal(10, 1500))

    def test_running_window_uses_a_compact_height_that_tracks_audio_controls(self):
        collapsed = runtime_window_layout(1463, 914, controls_expanded=False)
        expanded = runtime_window_layout(1463, 914, controls_expanded=True)

        self.assertEqual((600, 280), (collapsed.width, collapsed.height))
        self.assertEqual((600, 460), (expanded.width, expanded.height))
        self.assertEqual(collapsed.x, expanded.x)

    def test_high_dpi_runtime_window_keeps_safety_space_below_measured_content(self):
        layout = runtime_window_layout(
            2560,
            1600,
            controls_expanded=False,
            minimum_content_height=402,
            ui_scale=1.75,
        )

        self.assertEqual(430, layout.height)

    def test_v2_dialog_is_compact_and_centered(self):
        layout = v2_window_layout(1463, 914)

        self.assertEqual((560, 430), (layout.width, layout.height))
        self.assertEqual((451, 242), (layout.x, layout.y))
        self.assertEqual((540, 410), (layout.min_width, layout.min_height))


if __name__ == "__main__":
    unittest.main()
