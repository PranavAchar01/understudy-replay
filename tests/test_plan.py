"""The prompt planner (plan.py): PhyT2V-style prompts, the refine step, and the cache-preserving v1 path.

Nothing here calls Runway. Whether the new prompts give fewer rejected clips is not measured yet."""

import itertools
import json
from pathlib import Path

import pytest

from understudy.generate import frame_body, video_body
from understudy.plan import (
    MISMATCH_RULES,
    PROMPT_MAX_CHARS,
    mismatches,
    parse_task,
    prompt_version_for,
    refine_fixes,
    scene_spec,
    variants,
)

V1 = json.loads((Path(__file__).parent / "data" / "prompts_v1.json").read_text())
NEW = parse_task("put a red block into a bowl")
# the real rejection reasons of the v5 live take (data/web-runs/put-a-red-block-into-a-bowl/data.json)
V5_REJECTIONS = [
    {
        "clip_id": "v01",
        "accepted": False,
        "reason": "hand + wrist visible: hand seen on 82% of the demonstration frames",
    },
    {
        "clip_id": "v02",
        "accepted": False,
        "reason": "one red object (pixels): a second red object 41% the size of the block; which one is the target?",
    },
    {
        "clip_id": "v03",
        "accepted": False,
        "reason": "scene audit (Claude): Claude counts 2 red blocks, 1 bowls, 1 hands in the first frame",
    },
    {
        "clip_id": "v04",
        "accepted": False,
        "reason": "scene audit (Claude): Claude counts 1 red blocks, 2 bowls, 1 hands in the first frame",
    },
    {
        "clip_id": "v05",
        "accepted": False,
        "reason": "scene audit (Claude): Claude counts 2 red blocks, 1 bowls, 1 hands in the first frame",
    },
]
DUP = "no second red object appears: a second red block appears on 10 frames (first at 3.3 s): the video duplicated the object"


@pytest.fixture(autouse=True)
def no_image_reads(monkeypatch):
    import understudy.runway as rw

    monkeypatch.setattr(rw, "image_data_uri", lambda p: "data:image/png;base64,")


@pytest.mark.parametrize("sentence", sorted(V1))
def test_first_run_keeps_its_v1_prompts_byte_for_byte(sentence):
    """The first run's cached clips are keyed on these exact prompts; a change would spend credits."""
    t = parse_task(sentence)
    if sentence != "put the red block in the bowl":
        assert prompt_version_for(t) == 2
        return
    assert prompt_version_for(t) == 1
    for i, v in enumerate(variants(t, 7)):
        old = V1[sentence][i]
        assert (v.image_prompt, v.video_prompt) == (
            old["image_prompt"],
            old["video_prompt"],
        )
        if i:
            assert frame_body(v, Path("x"), 0)["promptText"] == old["restyle_prompt"]
    # a refined retake of the first run moves to the current prompts (it is new footage anyway)
    ref = variants(t, 7, {"*": mismatches([DUP], t)})
    assert {v.prompt_version for v in ref} == {2}
    assert ref[1].video_prompt.startswith("Exactly one red block exists in the whole video")
    assert variants(t, 7, {"*": []}) == variants(t, 7)


def test_step1_inventory_has_exact_counts_and_rules():
    v = variants(NEW, 3)
    spec = scene_spec(NEW, v[0].bowl)
    assert [n for n, _ in spec.inventory] == [1, 1, 1]
    img, vid, rst = v[1].image_prompt, v[1].video_prompt, v[1].restyle_prompt
    assert "exactly three things: one small red wooden toy block" in img
    assert "one person's right hand" in img
    assert "the only red object" in img and "the only red object" in rst
    assert "exactly three things: one red block, one empty bowl, one hand" in rst
    for _, rule in spec.rules:
        assert rule in vid
    assert "Exactly one red block exists in every frame" in vid
    assert "falls into the bowl and rests there" in vid


def test_new_prompts_are_positive_phrasing():
    """Runway's Gen-4 guide: negative phrasing is not supported and may give the opposite."""
    for v in variants(NEW, 6, refine_fixes(V5_REJECTIONS, NEW)):
        for p in (v.image_prompt, v.video_prompt, v.restyle_prompt):
            low = p.lower()
            for neg in (" no ", "nothing", " not ", "never", "without", "don't"):
                assert neg not in f" {low} ", (neg, p)


def test_step2_reads_mismatches_off_the_real_rejection_reasons():
    got = {
        r["clip_id"]: [m.key for m in mismatches([r["reason"]], NEW)]
        for r in V5_REJECTIONS
    }
    assert got == {
        "v01": ["hand_out_of_frame"],
        "v02": ["second_red_object"],
        "v03": ["duplicate_block"],
        "v04": ["extra_container"],
        "v05": ["duplicate_block"],
    }
    assert [m.key for m in mismatches([DUP], NEW)] == ["duplicate_block"]
    # reasons a prompt cannot fix are skipped
    assert mismatches(["frame rate: 12 fps", "accepted"], NEW) == []


def test_step3_puts_each_fix_first_in_the_prompt_that_caused_it():
    fx = refine_fixes(V5_REJECTIONS, NEW)
    assert next(m.key for m in fx["v04"]) == "extra_container"
    vs = {v.clip_id: v for v in variants(NEW, 5, fx)}
    v4 = vs["v04"]
    assert v4.image_prompt.startswith("Exactly one bowl stands on the table")
    assert v4.restyle_prompt.startswith("Exactly one bowl stands on the table")
    # a first-frame fix does not go into the motion prompt; a both-ways fix does
    assert "Exactly one bowl stands" not in v4.video_prompt
    assert "Exactly one red block exists in the whole video" in v4.video_prompt
    # the replaced base sentence is gone, not repeated
    assert "Exactly one red block exists in every frame" not in v4.video_prompt
    assert v4.fixes[0] == "extra_container" and set(v4.fixes) == {
        r[0] for r in MISMATCH_RULES
    }
    # an accepted run gives no fixes: prompts are the plain v2 ones
    ok = [{"clip_id": "v01", "accepted": True, "reason": "accepted"}]
    assert variants(NEW, 3, refine_fixes(ok, NEW)) == variants(NEW, 3)


def test_refined_prompts_change_the_request_so_the_next_take_is_new_footage():
    base = variants(NEW, 2)[1]
    ref = variants(NEW, 2, {"*": mismatches([DUP], NEW)})[1]
    assert (
        video_body(base, Path("x"), 5)["promptText"]
        != video_body(ref, Path("x"), 5)["promptText"]
    )


def test_every_prompt_fits_runways_limit_under_any_combination_of_fixes():
    keys = [r[1] for r in MISMATCH_RULES]
    samples = [
        "Claude counts 1 red blocks, 2 bowls, 1 hands",
        DUP,
        "one red object (pixels): a second red object 41%",
        "hand + wrist visible: hand seen on 82%",
    ]
    assert len(samples) == len(keys)
    for r in range(len(samples) + 1):
        for combo in itertools.combinations(samples, r):
            for v in variants(NEW, 7, {"*": mismatches(list(combo), NEW)}):
                for p in (v.image_prompt, v.video_prompt, v.restyle_prompt):
                    assert 0 < len(p) <= PROMPT_MAX_CHARS
