"""Text token counts for the browser extension's per-prompt ledger.

OpenAI publishes its tokenizer: GPT-4o and later use the o200k_base encoding, which
tiktoken ships (free, runs offline once the encoding file is cached). For ChatGPT
the count is therefore exact for the text you type.

Anthropic does not publish Claude's tokenizer, so for Claude the o200k count is
used as a labelled estimate. Without tiktoken installed, both fall back to the
common ~4 characters per token rule of thumb.
"""
from __future__ import annotations

import math
from functools import lru_cache


@lru_cache(maxsize=1)
def _encoder():
    try:
        import tiktoken
        return tiktoken.get_encoding("o200k_base")
    except Exception:  # not installed, or the encoding file cannot be fetched
        return None


def count_text_tokens(text: str, provider: str = "openai") -> tuple[int, str]:
    """(tokens, method). method is 'exact', 'estimate (o200k)' or 'estimate (chars/4)'."""
    enc = _encoder()
    if enc is not None:
        n = len(enc.encode(text, disallowed_special=()))
        return n, "exact" if provider == "openai" else "estimate (o200k)"
    return math.ceil(len(text) / 4), "estimate (chars/4)"
