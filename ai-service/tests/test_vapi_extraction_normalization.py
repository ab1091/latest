import unittest

from vapi.router import _normalize_extracted_fields


class ExtractedFieldNormalizationTests(unittest.TestCase):
    def test_converts_string_nulls_to_none(self):
        result = _normalize_extracted_fields({
            "name": "null",
            "email": " NULL ",
            "service": "None",
            "date": "2026-08-03",
        })

        self.assertIsNone(result["name"])
        self.assertIsNone(result["email"])
        self.assertIsNone(result["service"])
        self.assertEqual(result["date"], "2026-08-03")

    def test_rejects_invalid_email_and_keeps_valid_email(self):
        self.assertIsNone(_normalize_extracted_fields({"email": "not provided"})["email"])
        self.assertEqual(
            _normalize_extracted_fields({"email": " lead@example.com "})["email"],
            "lead@example.com",
        )


if __name__ == "__main__":
    unittest.main()
