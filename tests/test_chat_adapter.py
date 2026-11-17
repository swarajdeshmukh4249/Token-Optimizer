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


def test_right_size_saves_on_retina_and_refuses_when_quality_would_drop():
    import cv2
    import numpy as np
    from tokenopt.adapters.chat import PROVIDERS, right_size
    ui = make_session()[0][1]
    retina = cv2.resize(ui, (ui.shape[1] * 2, ui.shape[0] * 2), interpolation=cv2.INTER_CUBIC)
    for prov in ("claude", "openai"):
        cost = PROVIDERS[prov][1]
        small, did = right_size(retina, prov, dpr=2.0)
        if did:
            assert cost(small.shape[1], small.shape[0]) <= 0.9 * cost(retina.shape[1], retina.shape[0])
            assert max(small.shape[:2]) >= 0.66 * max(retina.shape[:2]) / 2
    assert right_size(retina, "claude", dpr=2.0)[1]            # Claude bills by area: always a win
    noise = np.random.default_rng(0).integers(0, 255, (1600, 1600, 3), dtype=np.uint8)
    kept, did = right_size(noise, "claude", dpr=2.0)             # needs every pixel: untouched
    assert not did and kept is noise
    crop = ui[:600, :900]
    same, did = right_size(crop, "claude", dpr=1.0)              # already small: untouched
    assert not did and same is crop
