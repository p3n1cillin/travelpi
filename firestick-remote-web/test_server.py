"""Tests for what server.py sends to the Firestick's shell.

Run with: python3 -m unittest test_server.py (no adb or Firestick needed;
mock mode returns the shell command instead of sending it).
"""

import shlex
import unittest

from server import FirestickRemote, RemoteError


def shell_words(result):
    """Split the command the way the Firestick's shell will."""
    return shlex.split(result["stdin"])


class TextInputTest(unittest.TestCase):
    def setUp(self):
        self.remote = FirestickRemote("", mock=True, port=0)

    def test_plain_text_is_one_argument(self):
        self.assertEqual(shell_words(self.remote.text("hello world")),
                         ["input", "text", "hello%sworld"])

    def test_shell_metacharacters_stay_text(self):
        for value in ("a;reboot", "$(reboot)", "`reboot`", "a && reboot",
                      "a | sh", "it's", 'say "hi"', "> /sdcard/x"):
            with self.subTest(value=value):
                words = shell_words(self.remote.text(value))
                self.assertEqual(words[:2], ["input", "text"])
                self.assertEqual(len(words), 3, words)
                self.assertEqual(words[2].replace("%s", " "), value)

    def test_control_characters_are_refused(self):
        for value in ("a\nreboot", "a\rb", "a\x00b", "a\x1bb"):
            with self.subTest(value=repr(value)):
                with self.assertRaises(RemoteError):
                    self.remote.text(value)


class LaunchTest(unittest.TestCase):
    def setUp(self):
        self.remote = FirestickRemote("", mock=True, port=0)

    def test_real_package_names_launch(self):
        for package in ("org.jellyfin.androidtv", "com.netflix.ninja",
                        "com.amazon.amazonvideo.livingroom", "com.a_b.c1"):
            with self.subTest(package=package):
                result = self.remote.launch(package)
                self.assertIn(package, result["command"])

    def test_injected_package_names_are_refused(self):
        for package in ("com.x;reboot", "com.x $(reboot)", "com.x\nreboot",
                        "noperiod", ".com.x", "com..x", "1com.x", "com.x/y"):
            with self.subTest(package=package):
                with self.assertRaises(RemoteError):
                    self.remote.launch(package)


if __name__ == "__main__":
    unittest.main()
