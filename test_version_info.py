import re
import unittest
from pathlib import Path

import PhoneLinkOtpAutofill as otp
from release_metadata import EXECUTABLE_NAME


class VersionInfoTests(unittest.TestCase):
    def test_windows_executable_metadata_matches_app_version(self):
        version_file = Path(__file__).with_name("version_info.txt")
        contents = version_file.read_text(encoding="utf-8")
        numeric = tuple(int(part) for part in otp.VERSION.split(".")) + (0,)

        self.assertIn(f"filevers={numeric}", contents)
        self.assertIn(f"prodvers={numeric}", contents)
        self.assertRegex(
            contents,
            rf"StringStruct\('FileVersion',\s*'{re.escape(otp.VERSION)}'\)",
        )
        self.assertRegex(
            contents,
            rf"StringStruct\('ProductVersion',\s*'{re.escape(otp.VERSION)}'\)",
        )
        self.assertIn(
            f"StringStruct('OriginalFilename', '{EXECUTABLE_NAME}')",
            contents,
        )


if __name__ == "__main__":
    unittest.main()
