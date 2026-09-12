import unittest
from unittest.mock import patch

import PhoneLinkOtpAutofill as otp


class HistoryGuardTests(unittest.TestCase):
    def make_app(self):
        app = object.__new__(otp.OtpAutofillApp)
        app.config = {
            "ignore_existing_on_start": True,
            "baseline_settle_seconds": 5.0,
            "detected_code_cooldown_seconds": 300.0,
            "otp_cooldown_seconds": 120.0,
            "pending_seconds": 15.0,
        }
        app.phone = object()
        app.phone_hwnd = 123
        app.seen_texts = set()
        app.observed_codes = {}
        app.filled_codes = {}
        app.pending = None
        app.baseline_settle_until = 0.0
        app._set_status = lambda _status: None
        return app

    def test_default_history_guard_settings(self):
        self.assertEqual(otp.DEFAULT_CONFIG["baseline_settle_seconds"], 5.0)
        self.assertEqual(otp.DEFAULT_CONFIG["detected_code_cooldown_seconds"], 300.0)

    def test_baseline_absorbs_historical_codes_without_pending_fill(self):
        app = self.make_app()
        text = "【OPPO】验证码 123456"

        with patch.object(otp.time, "monotonic", return_value=100.0):
            app._absorb_baseline([text])

        self.assertIn(text, app.seen_texts)
        self.assertEqual(app.observed_codes["123456"], 100.0)
        self.assertIsNone(app.pending)

    def test_settle_period_absorbs_late_ui_nodes_without_detection(self):
        app = self.make_app()
        app.baseline_settle_until = 105.0
        text = "短信验证码 123456"

        with patch.object(otp.time, "monotonic", return_value=101.0):
            app._process_text_snapshot([text])

        self.assertIn(text, app.seen_texts)
        self.assertIn("123456", app.observed_codes)
        self.assertIsNone(app.pending)

    def test_different_text_node_with_recent_observed_code_is_ignored(self):
        app = self.make_app()
        app.observed_codes["123456"] = 100.0

        with patch.object(otp.time, "monotonic", return_value=110.0):
            app._handle_new_text("短信验证码 123456")

        self.assertIsNone(app.pending)

    def test_observed_code_is_eligible_after_history_cooldown(self):
        app = self.make_app()
        app.observed_codes["123456"] = 100.0

        with patch.object(otp.time, "monotonic", return_value=400.0):
            app._handle_new_text("短信验证码 123456")

        self.assertEqual(app.pending[0], "123456")
        self.assertEqual(app.observed_codes["123456"], 400.0)

    def test_successful_fill_moves_code_from_observed_to_filled_history(self):
        app = self.make_app()
        app.observed_codes["123456"] = 100.0

        app._record_successful_fill("123456", filled_at=101.0)

        self.assertNotIn("123456", app.observed_codes)
        self.assertEqual(app.filled_codes["123456"], 101.0)

    def test_disconnect_clears_pending_and_window_state(self):
        app = self.make_app()
        app.pending = ("123456", 200.0, "验证码 123456")

        app._disconnect_phone_link()

        self.assertIsNone(app.phone)
        self.assertIsNone(app.phone_hwnd)
        self.assertIsNone(app.pending)
        self.assertEqual(app.baseline_settle_until, 0.0)


if __name__ == "__main__":
    unittest.main()
