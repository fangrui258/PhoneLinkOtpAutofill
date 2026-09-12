import unittest

from release_metadata import EXECUTABLE_NAME, EXECUTABLE_STEM, VERSION


class ReleaseMetadataTests(unittest.TestCase):
    def test_v1_0_4_executable_name_contains_version(self):
        self.assertEqual(VERSION, "1.0.4")
        self.assertEqual(EXECUTABLE_STEM, "PhoneLinkOtpAutofill-v1.0.4")
        self.assertEqual(EXECUTABLE_NAME, "PhoneLinkOtpAutofill-v1.0.4.exe")


if __name__ == "__main__":
    unittest.main()
