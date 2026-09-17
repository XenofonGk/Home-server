import unittest

from bridge.text import split_message, truncate_for_log


class TestSplitMessage(unittest.TestCase):
    def test_empty_returns_no_chunks(self):
        self.assertEqual(split_message(""), [])

    def test_short_text_is_one_chunk(self):
        self.assertEqual(split_message("hello"), ["hello"])

    def test_text_at_exactly_the_limit_is_not_split(self):
        text = "a" * 4096
        self.assertEqual(split_message(text), [text])

    def test_long_text_is_split_within_limit(self):
        text = ("word " * 3000).strip()
        chunks = split_message(text, limit=100)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 100)

    def test_split_prefers_paragraph_boundaries(self):
        text = "first para\n\nsecond para"
        chunks = split_message(text, limit=15)
        self.assertEqual(chunks[0], "first para")

    def test_split_does_not_break_mid_word(self):
        text = "alpha bravo charlie delta echo foxtrot"
        for chunk in split_message(text, limit=12):
            self.assertFalse(chunk.startswith(" "))
            self.assertFalse(chunk.endswith(" "))

    def test_unbreakable_blob_is_hard_cut_not_dropped(self):
        text = "x" * 250
        chunks = split_message(text, limit=100)
        self.assertEqual(len(chunks), 3)
        self.assertEqual("".join(chunks), text)

    def test_no_content_is_lost(self):
        text = "alpha bravo charlie delta echo foxtrot golf hotel india"
        rejoined = " ".join(split_message(text, limit=20))
        self.assertEqual(rejoined.split(), text.split())

    def test_zero_limit_rejected(self):
        with self.assertRaises(ValueError):
            split_message("x", limit=0)


class TestTruncateForLog(unittest.TestCase):
    def test_collapses_whitespace(self):
        self.assertEqual(truncate_for_log("a\n\n  b"), "a b")

    def test_truncates_long_text(self):
        self.assertEqual(len(truncate_for_log("x" * 500, limit=50)), 50)


if __name__ == "__main__":
    unittest.main()
