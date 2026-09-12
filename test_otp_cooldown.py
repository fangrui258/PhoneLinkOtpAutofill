import unittest
from unittest.mock import patch

import PhoneLinkOtpAutofill as otp


class OtpCooldownTests(unittest.TestCase):
    def make_app(self):
        app = object.__new__(otp.OtpAutofillApp)
        app.config = {
            "otp_cooldown_seconds": 120.0,
            "pending_seconds": 15.0,
            "autofill_enabled": True,
            "strict_input_focus": False,
            "smart_focus_guard": True,
            "notify_on_fill": False,
        }
        app.filled_codes = {}
        app.pending = None
        app.paused_until = 0.0
        app._set_status = lambda _status: None
        app._notify = lambda _message: None
        app._is_browser = lambda _info: True
        return app

    def test_default_cooldown_is_120_seconds(self):
        self.assertEqual(otp.DEFAULT_CONFIG["otp_cooldown_seconds"], 120.0)

    def test_recently_filled_code_is_rejected_during_cooldown(self):
        app = self.make_app()
        app.filled_codes["123456"] = 100.0

        with patch.object(otp.time, "monotonic", return_value=150.0):
            duplicate, elapsed = app._recently_filled("123456")

        self.assertTrue(duplicate)
        self.assertEqual(elapsed, 50.0)

    def test_expired_code_is_accepted_and_removed(self):
        app = self.make_app()
        app.filled_codes["123456"] = 100.0

        with patch.object(otp.time, "monotonic", return_value=220.0):
            duplicate, elapsed = app._recently_filled("123456")

        self.assertFalse(duplicate)
        self.assertEqual(elapsed, 120.0)
        self.assertNotIn("123456", app.filled_codes)

    def test_timed_out_code_can_be_detected_again_from_a_different_text_node(self):
        app = self.make_app()
        app.pending = ("123456", 100.0, "验证码 123456")

        with patch.object(otp.time, "time", return_value=101.0):
            app._try_fill_pending()

        self.assertIsNone(app.pending)
        app._handle_new_text("【测试】您的验证码为123456")
        self.assertEqual(app.pending[0], "123456")

    def test_zero_cooldown_disables_duplicate_filter(self):
        app = self.make_app()
        app.config["otp_cooldown_seconds"] = 0.0
        app.filled_codes["123456"] = 100.0

        with patch.object(otp.time, "monotonic", return_value=101.0):
            duplicate, elapsed = app._recently_filled("123456")

        self.assertFalse(duplicate)
        self.assertEqual(elapsed, 1.0)
        self.assertNotIn("123456", app.filled_codes)

    def test_detection_without_input_does_not_start_cooldown(self):
        app = self.make_app()

        app._handle_new_text("【测试】您的验证码为123456，5分钟内有效")

        self.assertEqual(app.pending[0], "123456")
        self.assertEqual(app.filled_codes, {})

    def test_handle_new_text_ignores_code_already_filled(self):
        app = self.make_app()
        app.filled_codes["123456"] = 100.0

        with patch.object(otp.time, "monotonic", return_value=101.0):
            app._handle_new_text("验证码 123456")

        self.assertIsNone(app.pending)

    def test_successful_input_records_code_and_second_guard_blocks_repeat(self):
        app = self.make_app()
        source = "【测试】验证码 123456"
        app.pending = ("123456", 2000.0, source)

        with (
            patch.object(otp, "foreground_app_info", return_value={"process": "msedge.exe"}),
            patch.object(otp, "focused_control_state", return_value=(True, "EditControl")),
            patch.object(otp, "type_digits") as type_digits,
            patch.object(otp.time, "time", return_value=1000.0),
            patch.object(otp.time, "sleep"),
            patch.object(otp.time, "monotonic", side_effect=[500.0, 501.0]),
        ):
            app._try_fill_pending()

        type_digits.assert_called_once_with("123456")
        self.assertEqual(app.filled_codes["123456"], 501.0)
        self.assertIsNone(app.pending)

        app.pending = ("123456", 2000.0, source)
        with (
            patch.object(otp, "foreground_app_info", return_value={"process": "msedge.exe"}),
            patch.object(otp, "focused_control_state", return_value=(True, "EditControl")),
            patch.object(otp, "type_digits") as repeated_type_digits,
            patch.object(otp.time, "time", return_value=1000.0),
            patch.object(otp.time, "sleep"),
            patch.object(otp.time, "monotonic", return_value=502.0),
        ):
            app._try_fill_pending()

        repeated_type_digits.assert_not_called()
        self.assertIsNone(app.pending)

    def test_failed_input_does_not_start_cooldown(self):
        app = self.make_app()
        app.pending = ("123456", 2000.0, "验证码 123456")

        with (
            patch.object(otp, "foreground_app_info", return_value={"process": "msedge.exe"}),
            patch.object(otp, "focused_control_state", return_value=(True, "EditControl")),
            patch.object(otp, "type_digits", side_effect=RuntimeError("input failed")),
            patch.object(otp.time, "time", return_value=1000.0),
            patch.object(otp.time, "sleep"),
            patch.object(otp.time, "monotonic", return_value=500.0),
        ):
            with self.assertRaisesRegex(RuntimeError, "input failed"):
                app._try_fill_pending()

        self.assertNotIn("123456", app.filled_codes)


if __name__ == "__main__":
    unittest.main()
