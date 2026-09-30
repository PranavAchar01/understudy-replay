import json
import re
from pathlib import Path

import numpy as np
import pytest
import synth

from understudy import gates as G
from understudy.pick_expert import in_bowl
from understudy.plan import Infeasible, parse_task, variants
from understudy.retarget import reanchor, replay
from understudy.scene import CUBE_HALF, load
from understudy.track import find_events, load_track, to_robot
from understudy.units import from_lerobot_units, to_lerobot_units

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def scene():
    return load(task="pick")


def track_of(d, tmp_path):
    return load_track(synth.write(d, tmp_path / "pose.json"))


def demo_of(d, tmp_path):
    tr = track_of(d, tmp_path)
    ev = find_events(tr)
    assert ev.ok, ev.why
    bb = synth.AUDIT_OK["bowl_bbox_first"]
    return tr, ev, to_robot(tr, ev, (bb[0] + bb[2]) / 2)


# ---------- plan ----------
def test_plan_accepts_the_task_and_varies_scenes():
    t = parse_task("put the red block in the bowl")
    assert (t.color, t.obj, t.container) == ("red", "block", "bowl")
    vs = variants(t, 6)
    assert len({(v.table, v.bowl, v.lighting) for v in vs}) == 6


@pytest.mark.parametrize(
    "text,why",
    [
        ("fold the towel", "deformable"),
        ("pour water into the cup", "liquids"),
        ("use both hands to put the red block in the bowl", "two hands"),
        ("put the blue block in the bowl", "red block"),
        ("juggle three balls", "Understudy handles"),
    ],
)
def test_plan_refuses_what_a_5dof_two_finger_arm_cannot_do(text, why):
    with pytest.raises(Infeasible, match=why):
        parse_task(text)


# ---------- units ----------
def test_units_round_trip():
    q = np.array([0.3, -1.2, 1.0, 0.5, -2.0, 0.7])
    assert np.allclose(from_lerobot_units(to_lerobot_units(q)), q, atol=1e-5)


# ---------- spec ----------
def test_data_spec_doc_matches_code():
    doc = (REPO / "docs" / "DATA-SPEC.md").read_text()
    for k, v in G.SPEC.items():
        assert f"{v:g}" in doc, f"{k}={v:g} missing from docs/DATA-SPEC.md"
    for gid in re.findall(
        r'_row\(\s*"(\w+)"', (REPO / "src/understudy/gates.py").read_text()
    ):
        assert f"| {gid} |" in doc, f"gate {gid} not documented"


# ---------- tracking ----------
def test_events_and_grasp_anchoring(tmp_path):
    tr, ev, demo = demo_of(synth.clean(), tmp_path)
    assert ev.t_grasp < ev.t_lift < ev.t_release
    assert 20 <= ev.t_grasp <= 31 and 60 <= ev.t_release <= 72
    # at the grasp frame the grasp point is exactly the cube start
    assert np.allclose(demo.xyz[demo.grasp_i], demo.cube_start, atol=1e-6)
    assert demo.m_per_px == pytest.approx(0.03 / synth.BPX)
    assert demo.carry_dist == pytest.approx(360 * 0.03 / synth.BPX, rel=1e-3)


def test_clean_synthetic_clip_passes_clip_gates(tmp_path):
    tr, ev, demo = demo_of(synth.clean(), tmp_path)
    rows = G.clip_gates(tr, ev, synth.AUDIT_OK, demo)
    assert G.verdict(rows) == (True, "accepted"), rows


def test_second_red_object_is_rejected(tmp_path):
    d = synth.clean()
    for f in d["frames"]:
        f["block"]["second_ratio"] = 0.9
    tr, ev, demo = demo_of(d, tmp_path)
    ok, why = G.verdict(G.clip_gates(tr, ev, synth.AUDIT_OK, demo))
    assert not ok and "second red object" in why


def test_hand_missing_is_rejected(tmp_path):
    d = synth.clean()
    for f in d["frames"][35:50]:
        f["hand"] = None
    tr = track_of(d, tmp_path)
    ev = find_events(tr)
    ok, why = G.verdict(G.clip_gates(tr, ev, synth.AUDIT_OK, None))
    assert not ok and "hand seen on" in why


def test_block_moving_on_its_own_is_rejected(tmp_path):
    d = synth.clean()
    for i, f in enumerate(d["frames"][31:66], start=31):
        f["block"]["c"] = [
            500 + (i - 31) * 10.0,
            440.0,
        ]  # slides along the table while the hand lifts: not carried
    tr, ev, demo = demo_of(d, tmp_path)
    ok, why = G.verdict(G.clip_gates(tr, ev, synth.AUDIT_OK, demo))
    assert not ok and "block widths" in why


def test_claude_count_rejects(tmp_path):
    tr, ev, demo = demo_of(synth.clean(), tmp_path)
    ok, why = G.verdict(
        G.clip_gates(tr, ev, {**synth.AUDIT_OK, "red_blocks_first": 2}, demo)
    )
    assert not ok and "2 red blocks" in why


# ---------- retarget + sim ----------
def test_synthetic_demo_replays_into_the_bowl(scene, tmp_path):
    _, _, demo = demo_of(synth.clean(), tmp_path)
    rep = replay(scene, demo)
    rows = G.robot_gates(rep)
    assert G.verdict(rows) == (True, "accepted"), [
        r for r in rows if r["passed"] is False
    ]
    assert in_bowl(rep.cube[-1]) and rep.cube[:, 2].max() > CUBE_HALF + 0.02


def test_unreachable_cube_fails_ik_gate(scene, tmp_path):
    _, _, demo = demo_of(synth.clean(), tmp_path)
    far = reanchor(demo, [0.46, -0.25])
    ok, why = G.verdict(G.robot_gates(replay(scene, far)))
    assert not ok and "joint limit" in why


def test_rushed_demo_fails_speed_gates(scene, tmp_path):
    _, _, demo = demo_of(synth.clean(), tmp_path)
    rep = replay(scene, demo, time_scale=0.04)  # 25 times faster than the human
    rows = {r["id"]: r for r in G.robot_gates(rep)}
    assert not (
        rows["vel"]["passed"] and rows["acc"]["passed"] and rows["jerk"]["passed"]
    )


def test_gripper_that_never_closes_fails(scene, tmp_path):
    _, _, demo = demo_of(synth.clean(), tmp_path)
    demo.closed[:] = False
    ok, why = G.verdict(G.robot_gates(replay(scene, demo)))
    assert not ok


# ---------- real Runway clips (skipped if their landmarks are not cached) ----------
POSE = REPO / "data" / "cache" / "pose"
AUDIT = REPO / "data" / "cache" / "audit"
REAL = {"723598ead33a3794730b": True, "0f8b1d5857c297630cbc": False}


@pytest.mark.parametrize("key,expect", REAL.items())
def test_real_clip_verdicts(scene, key, expect):
    import hashlib

    clip = REPO / "data" / "cache" / "runway" / f"{key}.mp4"
    if not clip.exists():
        pytest.skip("clip not cached")
    h = hashlib.sha256(clip.read_bytes()).hexdigest()[:20]
    pose, au = POSE / f"{h}_mediapipe_v2.json", AUDIT / f"{h}.json"
    if not (pose.exists() and au.exists()):
        pytest.skip("landmarks or audit not cached")
    au = json.loads(au.read_text())
    tr = load_track(pose)
    ev = find_events(tr)
    bb = au["bowl_bbox_first"]
    demo = to_robot(tr, ev, (bb[0] + bb[2]) / 2) if ev.ok else None
    rows = G.clip_gates(tr, ev, au, demo)
    if demo is not None:
        rows += G.robot_gates(replay(scene, demo))
    assert G.verdict(rows)[0] is expect


def test_duplicated_block_after_release_is_rejected(tmp_path):
    d = synth.clean()
    for f in d["frames"][80:100]:  # the hand leaves holding a second copy while the first rests in the bowl
        f["block"]["second_area"] = int(0.8 * synth.BPX**2)
        f["block"]["second_c"] = [300.0, 120.0]
    tr, ev, demo = demo_of(d, tmp_path)
    ok, why = G.verdict(G.clip_gates(tr, ev, synth.AUDIT_OK, demo))
    assert not ok and "duplicated" in why


def test_block_split_by_fingers_is_not_a_duplicate(tmp_path):
    d = synth.clean()
    for f in d["frames"][35:60]:  # two halves of the same block, side by side
        f["block"]["second_area"] = int(0.4 * synth.BPX**2)
        f["block"]["second_c"] = [f["block"]["c"][0] + 60, f["block"]["c"][1]]
    tr, ev, demo = demo_of(d, tmp_path)
    assert G.verdict(G.clip_gates(tr, ev, synth.AUDIT_OK, demo))[0]
