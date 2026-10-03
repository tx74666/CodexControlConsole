"""QR connection checks use generated local state, never a real pairing."""
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
import phone_connection_qr as qr


class ConnectionQrChecks(unittest.TestCase):
    def test_rendered_png_is_bounded_and_scan_target_has_no_credentials(self):
        constructor = qr.qrcode.QRCode
        codes = []
        def create(**kwargs):
            code = constructor(**kwargs)
            codes.append(code)
            return code
        with patch.object(qr.qrcode, "QRCode", create):
            data = qr.connection_qr_png({"enabled": True, "url": "http://192.168.1.20:8899/", "pairingCode": "123456"})
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertLessEqual(max(image.size), 400)
        self.assertLess(len(data), 16384)
        encoded = b"".join(item.data for item in codes[0].data_list)
        self.assertEqual(encoded, b"http://192.168.1.20:8899/?tab=transfer")

    def test_closed_connection_has_no_qr(self):
        with self.assertRaises(ValueError):
            qr.connection_qr_png({"enabled": False, "url": "http://192.168.1.20:8899/"})

    def test_only_valid_private_network_addresses_are_encoded(self):
        for target in ("https://192.168.1.20:8899/", "http://example.com:8899/", "http://127.0.0.1:8899/",
                       "http://user:pass@192.168.1.20:8899/", "http://192.168.1.20:8899/?code=123456",
                       "http://192.168.1.20:8899/#code", "http://192.168.1.20:8899/other", "http://192.168.1.20/"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                qr.connection_qr_png({"enabled": True, "url": target})
        for target in ("http://10.2.3.4:8899/", "http://172.16.1.2:8899/mobile.html"):
            self.assertTrue(qr.connection_qr_png({"enabled": True, "url": target}).startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
