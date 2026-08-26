from __future__ import annotations

import ctypes
import os
import unittest

from ww_midi import wininput


@unittest.skipUnless(os.name == "nt", "Windows-only structure")
class WinInputTests(unittest.TestCase):
    def test_input_structure_matches_windows_abi(self) -> None:
        expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
        self.assertEqual(ctypes.sizeof(wininput.INPUT), expected)

    def test_letter_scan_codes_can_be_resolved(self) -> None:
        output = wininput.WindowsInput()
        for key in "QWERTYUASDFGHJZXCVBNM":
            self.assertGreater(output.scan_code(key), 0)

    def test_elevation_status_is_boolean(self) -> None:
        self.assertIsInstance(wininput.WindowsInput().is_elevated(), bool)


if __name__ == "__main__":
    unittest.main()
