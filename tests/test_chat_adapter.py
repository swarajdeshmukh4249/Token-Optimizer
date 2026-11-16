"""Chat-app adapter used by the browser extension."""
from tokenopt.adapters.chat import plan_followup
from tokenopt.agent import make_session
from tokenopt.cost import openai_image_tokens


def test_openai_formula_matches_published_examples():
    assert openai_image_tokens(512, 512) == 255           # 1 tile
    assert openai_image_tokens(1024, 1024) == 765         # -> 768x768, 4 tiles
    assert openai_image_tokens(2048, 4096) == 1105        # -> 1024x2048 -> 768x1536, 6 tiles


def test_followups_send_only_changes_and_never_cost_more():
    s = make_session()
    first = plan_followup(None, s[6][1], "claude")
    assert first.mode == "new" and first.tokens <= first.full_tokens
    typed = plan_followup(s[6][1], s[7][1], "claude")     # typing 'Agent' into the field
    assert typed.mode == "delta" and 0 < typed.tokens < 0.05 * typed.full_tokens
    same = plan_followup(s[8][1], s[8][1], "openai")
    assert same.mode == "duplicate" and same.tokens == 0 and not same.images
    for prov in ("claude", "openai"):
        prev = None
        for _, f in s:
            p = plan_followup(prev, f, prov)
            assert p.tokens <= p.full_tokens
            prev = f
