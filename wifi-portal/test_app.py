"""Cross-site protection on the WiFi portal.

Run with: python3 -m unittest test_app.py (needs Flask; nmcli is stubbed, so
no WiFi hardware is touched).
"""

import unittest

import app as portal


class CrossSiteTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self._nmcli = portal.nmcli
        portal.nmcli = lambda *args, **kwargs: (self.calls.append(args), (0, "", ""))[1]
        self.client = portal.app.test_client()

    def tearDown(self):
        portal.nmcli = self._nmcli

    def test_disconnect_without_the_header_is_refused(self):
        # What a form or fetch() on another site can send.
        response = self.client.post("/api/disconnect", headers={"Host": "192.168.50.1"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.calls, [])

    def test_connect_with_a_form_body_is_refused(self):
        response = self.client.post("/api/connect", data='{"ssid":"evil"}',
                                    content_type="text/plain", headers={"Host": "192.168.50.1"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.calls, [])

    def test_the_page_and_its_own_calls_work(self):
        self.assertEqual(self.client.get("/", headers={"Host": "192.168.50.1"}).status_code, 200)
        response = self.client.post("/api/disconnect",
                                    headers={"Host": "192.168.50.1", "X-TravelPi": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.calls, [("dev", "disconnect", "wlan1")])

    def test_rebound_host_is_refused(self):
        response = self.client.get("/api/status", headers={"Host": "evil.example"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
