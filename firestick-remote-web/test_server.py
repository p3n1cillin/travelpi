"""Tests for what server.py sends to the Firestick's shell.

Run with: python3 -m unittest test_server.py (no adb or Firestick needed;
mock mode returns the shell command instead of sending it).
"""

import http.client
import shlex
import threading
import unittest

from server import FirestickRemote, RemoteError, build_server, host_allowed


def shell_words(result):
    """Split the command the way the Firestick's shell will."""
    return shlex.split(result["stdin"])


def android_types(arg):
    """What Android's `input text <arg>` types: "%s" becomes a space and every
    other character, "%" included, is typed as-is (InputShellCommand.sendText)."""
    out, i = [], 0
    while i < len(arg):
        if arg[i] == "%" and i + 1 < len(arg) and arg[i + 1] == "s":
            out.append(" ")
            i += 2
        else:
            out.append(arg[i])
            i += 1
    return "".join(out)


def typed(result):
    """Everything the Firestick ends up typing for one text() call."""
    text = ""
    for command in result["stdin"].split(" && "):
        words = shlex.split(command)
        assert words[:2] == ["input", "text"] and len(words) == 3, words
        text += android_types(words[2])
    return text


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

    def test_percent_signs_are_typed_as_entered(self):
        # The old "%" -> "%25" escaping typed "50%" as "50%25".
        for value in ("50%", "100% sure", "a%sb", "%s", "% s", "%%s", "50%25"):
            with self.subTest(value=value):
                self.assertEqual(typed(self.remote.text(value)), value)

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


class HostAllowedTest(unittest.TestCase):
    def test_names_the_pi_is_reached_by(self):
        for host in ("192.168.50.1", "192.168.50.1:8787", "100.119.216.79:8787",
                     "[fd7a::1]:8787", "localhost:8787", "travelpi", "travelpi.local:8787",
                     "travelpi.tail1234.ts.net"):
            with self.subTest(host=host):
                self.assertTrue(host_allowed(host))

    def test_rebinding_names_are_refused(self):
        for host in (None, "", "evil.example", "evil.example:8787", "192.168.50.1.nip.io",
                     "travelpi.local.evil.example"):
            with self.subTest(host=host):
                self.assertFalse(host_allowed(host))


class CrossSiteRequestTest(unittest.TestCase):
    """Real HTTP requests against the server in mock mode."""

    @classmethod
    def setUpClass(cls):
        cls.server = build_server("127.0.0.1", 0, FirestickRemote("", mock=True, port=0))
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, method, path, headers=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        response.read()
        conn.close()
        return response.status

    def test_page_and_health_need_no_header(self):
        self.assertEqual(self.request("GET", "/"), 200)
        self.assertEqual(self.request("GET", "/api/health"), 200)

    def test_state_changes_without_the_header_are_refused(self):
        # What a form or <img> on another site can send.
        self.assertEqual(self.request("GET", "/k/home"), 403)
        self.assertEqual(self.request("POST", "/api/text", {"Content-Type": "text/plain"},
                                      '{"text":"x"}'), 403)

    def test_state_changes_with_the_header_are_served(self):
        self.assertEqual(self.request("GET", "/k/home", {"X-TravelPi": "1"}), 204)
        self.assertEqual(self.request("POST", "/api/text", {"X-TravelPi": "1"}, '{"text":"x"}'), 200)

    def test_rebound_host_is_refused_even_with_the_header(self):
        self.assertEqual(self.request("GET", "/api/health", {"Host": "evil.example"}), 403)
        self.assertEqual(self.request("GET", "/k/home", {"Host": "evil.example", "X-TravelPi": "1"}), 403)


if __name__ == "__main__":
    unittest.main()
