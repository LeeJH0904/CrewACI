import unittest

from aciarena.evaluation.normalizers import (
    NORMALIZER_VERSION,
    NormalizationError,
    normalize_response,
)


class NormalizerTests(unittest.TestCase):
    def test_transport_variation_is_normalized(self):
        raw = "  \ufeff```python\r\ndef solve():\r    return 1\r\n```  \n"
        self.assertEqual(
            normalize_response(raw),
            "```python\ndef solve():\n    return 1\n```",
        )
        self.assertEqual(NORMALIZER_VERSION, "text-envelope-v1")

    def test_internal_content_and_attack_evidence_are_preserved(self):
        raw = "Reasoning  with  spacing\n\\boxed{320}-US-NEWYORK"
        self.assertEqual(normalize_response(raw), raw)

    def test_blank_is_valid_but_non_string_is_rejected(self):
        self.assertEqual(normalize_response(" \r\n "), "")
        with self.assertRaisesRegex(NormalizationError, "must be a string"):
            normalize_response(None)


if __name__ == "__main__":
    unittest.main()
