import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import PhoneLinkOtpAutofill as otp


class ImmediateDetectionTests(unittest.TestCase):
    def make_app(self):
        app = object.__new__(otp.OtpAutofillApp)
        app.config = {
            "ignore_existing_on_start": True,
            "otp_cooldown_seconds": 120.0,
            "pending_seconds": 15.0,
        }
        app.phone = object()
        app.phone_hwnd = 123
        app.seen_texts = set()
        app.filled_codes = {}
        app.pending = None
        app._set_status = lambda _status: None
        return app

    def test_delayed_detection_guards_are_not_in_default_config(self):
        self.assertNotIn("baseline_settle_seconds", otp.DEFAULT_CONFIG)
        self.assertNotIn("detected_code_cooldown_seconds", otp.DEFAULT_CONFIG)

    def test_load_config_removes_obsolete_delay_settings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            config_path = data_dir / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "baseline_settle_seconds": 5.0,
                        "detected_code_cooldown_seconds": 300.0,
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(otp, "DATA_DIR", data_dir),
                patch.object(otp, "CONFIG_PATH", config_path),
            ):
                config = otp.load_config()

            persisted = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertNotIn("baseline_settle_seconds", config)
            self.assertNotIn("detected_code_cooldown_seconds", config)
            self.assertNotIn("baseline_settle_seconds", persisted)
            self.assertNotIn("detected_code_cooldown_seconds", persisted)

    def test_initial_snapshot_is_baselined_without_pending_fill(self):
        app = self.make_app()
        old_text = "【OPPO】验证码 123456"

        with patch.object(otp, "collect_texts", return_value=[old_text]):
            app._establish_baseline()

        self.assertIn(old_text, app.seen_texts)
        self.assertIsNone(app.pending)

    def test_new_text_after_baseline_is_processed_immediately(self):
        app = self.make_app()
        old_text = "【OPPO】验证码 123456"
        new_text = "【测试】验证码 654321"
        app.seen_texts.add(old_text)

        app._process_text_snapshot([old_text, new_text])

        self.assertEqual(app.pending[0], "654321")
        self.assertIn(new_text, app.seen_texts)

    def test_disconnect_clears_pending_and_window_state(self):
        app = self.make_app()
        app.pending = ("123456", 200.0, "验证码 123456")

        app._disconnect_phone_link()

        self.assertIsNone(app.phone)
        self.assertIsNone(app.phone_hwnd)
        self.assertIsNone(app.pending)


if __name__ == "__main__":
    unittest.main()
