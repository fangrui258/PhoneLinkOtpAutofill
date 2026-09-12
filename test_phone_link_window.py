import unittest

from PhoneLinkOtpAutofill import select_phone_link_window


class SelectPhoneLinkWindowTests(unittest.TestCase):
    def test_prefers_phone_experience_host_over_edge_title_match(self):
        windows = [
            (
                0x1001,
                "Release Phone Link OTP Autofill v1.0.0 · GitHub - Microsoft Edge",
                "msedge.exe",
            ),
            (0x1002, "手机连接", "phoneexperiencehost.exe"),
        ]

        self.assertEqual(
            select_phone_link_window(windows),
            (0x1002, "手机连接"),
        )

    def test_accepts_phone_experience_host_with_localized_title(self):
        windows = [
            (0x2001, "Lien avec Windows", "phoneexperiencehost.exe"),
        ]

        self.assertEqual(
            select_phone_link_window(windows),
            (0x2001, "Lien avec Windows"),
        )

    def test_accepts_exact_legacy_application_frame_title(self):
        windows = [
            (0x3001, "Phone Link", "applicationframehost.exe"),
        ]

        self.assertEqual(
            select_phone_link_window(windows),
            (0x3001, "Phone Link"),
        )

    def test_rejects_browser_title_containing_phone_link(self):
        windows = [
            (
                0x4001,
                "Release Phone Link OTP Autofill v1.0.0 · GitHub - Microsoft Edge",
                "msedge.exe",
            ),
        ]

        self.assertEqual(select_phone_link_window(windows), (None, None))

    def test_rejects_phone_link_splash_screen(self):
        windows = [
            (0x4002, "SplashScreen loading", "phoneexperiencehost.exe"),
        ]

        self.assertEqual(select_phone_link_window(windows), (None, None))

    def test_returns_none_when_no_phone_link_window_exists(self):
        windows = [
            (0x5001, "招聘网站", "chrome.exe"),
            (0x5002, "文件资源管理器", "explorer.exe"),
        ]

        self.assertEqual(select_phone_link_window(windows), (None, None))


if __name__ == "__main__":
    unittest.main()
