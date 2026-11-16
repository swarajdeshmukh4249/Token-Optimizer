"""OCR word-recall check (skipped where Tesseract is not installed)."""
from collections import Counter

import pytest

from tokenopt.agent import _screen
from tokenopt.ocr_eval import ocr, tesseract_available, word_recall, words


def test_word_recall_is_multiset_overlap():
    assert words("Tokens per week, 3.2m tokens a") == Counter({"tokens": 2, "per": 1, "week,": 1, "3.2m": 1})
    assert word_recall(words("a b tokens tokens week"), words("tokens week")) == pytest.approx(2 / 3)
    assert word_recall(Counter(), words("anything")) == 1.0


@pytest.mark.skipif(not tesseract_available(), reason="tesseract not installed")
def test_tesseract_reads_the_synthetic_dashboard():
    text = ocr(_screen("dashboard", (700, 420))).lower()
    assert "dashboard" in text
