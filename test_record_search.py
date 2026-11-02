import unittest

from record_search import match_spans


class MatchSpanTests(unittest.TestCase):
    def test_literal_nonoverlapping_and_empty_queries(self):
        self.assertEqual(match_spans("aaaa .[x] .[X]", "aa"), [(0, 2), (2, 4)])
        self.assertEqual(match_spans("a .* b .*", ".*"), [(2, 4), (7, 9)])
        self.assertEqual(match_spans("anything", ""), [])
        self.assertEqual(match_spans("anything", "missing"), [])

    def test_case_expansions_map_to_original_characters_once(self):
        self.assertEqual(match_spans("🙂Straße STRASSE", "strasse"), [(1, 7), (8, 15)])
        self.assertEqual(match_spans("ßß", "s"), [(0, 1), (1, 2)])
        self.assertEqual(match_spans("İ猫🙂", "i"), [(0, 1)])
        self.assertEqual(match_spans("İ猫🙂", "🙂"), [(2, 3)])


if __name__ == "__main__":
    unittest.main()
