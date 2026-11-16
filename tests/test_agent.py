"""Agent-screenshot compression: causal encoding never looks ahead."""
from tokenopt.agent import encode_causal, make_session
from tokenopt.video_opt import optimize_video


def test_session_shape():
    session = make_session()
    assert len(session) == 20
    assert all(f.shape == (800, 1280, 3) for _, f in session)


def test_causal_encoding_ignores_future_frames():
    frames = [f for _, f in make_session()[:5]]
    enc = encode_causal(frames)
    assert enc[0]["role"] == "key"
    # Turn 4 ("wait for page") repeats turn 3 exactly: nothing new to send.
    assert enc[3]["role"] == "duplicate" and enc[3]["tokens"] == 0
    # Encoding all five at once (non-causal) would be allowed to differ; the
    # causal encoder must match the prefix encoding for the last turn exactly.
    last = optimize_video(frames, patch=16).frames[-1]
    assert (last.role, last.tokens) == (enc[-1]["role"], enc[-1]["tokens"])
    # Small UI changes (hover) cost a tiny fraction of the 4000-token full frame.
    assert enc[4]["role"] == "delta" and enc[4]["tokens"] < 200
