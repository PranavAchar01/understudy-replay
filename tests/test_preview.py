from understudy.preview import caption, parse, plan_key

CASES = {
    "put the red block in the bowl": ("pick_place", ["block", "bowl"]),
    "push the green cube onto the blue square": ("push", ["block", "pad"]),
    "stack the yellow block on the red block": ("stack", ["block", "block"]),
    "put the ball in the cup": ("pick_place", ["ball", "cup"]),
    "open a book": ("hinge_open", ["book"]),
    "close the laptop": ("hinge_close", ["book"]),
    "build a tower of three blocks": ("tower", ["block", "block", "block"]),
    "place the orange on the plate": ("pick_place", ["ball", "plate"]),
}


def test_keyword_families():
    for sentence, (family, kinds) in CASES.items():
        p = parse(sentence)
        assert p["family"] == family, sentence
        assert [o["kind"] for o in p["objects"]] == kinds, sentence


def test_colours_and_caption():
    p = parse("stack the yellow block on the red block")
    assert [o["color"] for o in p["objects"]] == ["yellow", "red"]
    assert caption(p) == "place the yellow block onto the red block"


def test_substitution_is_disclosed():
    p = parse("pick up the banana")
    assert p["family"] == "lift" and "banana" in p["note"]


def test_cache_key_ignores_wording():
    assert plan_key(parse("put the red block in the bowl")) == plan_key(
        parse("Place the red cube into the bowl.")
    )
