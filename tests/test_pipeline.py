import numpy as np

from tokenopt.adapters.claude import build_payload
from tokenopt.ds.hash_table import hamming
from tokenopt.image_opt import optimize_image, render_leaves, uniform_at_budget
from tokenopt.metrics import psnr
from tokenopt.phash import phash
from tokenopt.synth import make_dense, make_document, make_ui
from tokenopt.video_opt import optimize_video


def test_phash_is_robust_to_noise_but_separates_content():
    doc, ui = make_document(), make_ui()
    noisy = np.clip(doc.astype(int) + np.random.default_rng(0).integers(-6, 7, doc.shape), 0, 255).astype(np.uint8)
    assert hamming(phash(doc), phash(noisy)) <= 4
    assert hamming(phash(doc), phash(ui)) > 10


def test_structured_image_saves_tokens_and_beats_uniform():
    img = make_ui()
    res = optimize_image(img)
    assert res.tokens < 0.5 * res.baseline_tokens
    uni, _ = uniform_at_budget(img, res.tokens, res.patch)
    assert psnr(img, render_leaves(img, res.leaves, res.patch)) > psnr(img, uni)


def test_dense_texture_is_not_compressed():
    res = optimize_image(make_dense(256, 256))
    assert res.tokens == res.baseline_tokens


def test_claude_adapter_never_costs_more_than_original():
    for img in (make_ui(), make_dense(256, 256), make_document()):
        pay = build_payload(optimize_image(img))
        assert pay.payload_tokens_est <= pay.full_tokens_est
        assert pay.content[-1]["type"] == "text"


def test_video_duplicates_scenes_and_deltas():
    rng = np.random.default_rng(1)
    a = np.full((128, 192, 3), 230, np.uint8)
    a[20:60, 20:100] = rng.integers(0, 256, (40, 80, 3))
    b = np.full((128, 192, 3), 30, np.uint8)
    b[60:110, 100:180] = rng.integers(0, 256, (50, 80, 3))
    a2 = a.copy()
    a2[90:106, 150:166] = 0  # small change inside scene A
    frames = [a, a.copy(), a2, b, b.copy(), a.copy()]
    res = optimize_video(frames, patch=16)
    roles = [f.role for f in res.frames]
    assert roles[0] == "key" and roles[1] == "duplicate" and roles[3] == "key"
    assert roles[2] == "delta" and 0 < res.frames[2].tokens <= 4
    assert roles[4] == "duplicate" and roles[5] == "duplicate"
    assert res.frames[5].ref == 0  # cut back to an earlier scene is caught by the hash index
    assert res.tokens < res.baseline_tokens / 3
    assert min(f.psnr for f in res.frames) > 30
