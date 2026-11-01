"""Reading the demo drawing, examples/demo_apartment.dxf.

In the studio these tests ran against four real client drawings (not in this
repository). The demo drawing is built in code to carry the same traps, so the
same rules are checked here: fixture kinds, annotation layers that hold no
fixtures, dimension arrowheads, a legend drawn far from the building, declared
extents that lie, and Hebrew/reversed text.
"""
import collections
import functools
import os

import pytest

import dxf_read
import framing

DEMO = os.path.join(os.path.dirname(__file__), "..", "examples", "demo_apartment.dxf")


@functools.lru_cache(maxsize=None)
def surveyed():
    if not os.path.exists(DEMO):
        pytest.skip("run examples/make_demo_dxf.py")
    return dxf_read.survey(DEMO)


def test_fixture_counts_by_kind_and_architecture():
    s = surveyed()
    kinds = collections.Counter(f.kind for f in s.fixtures)
    # 66 in the flat + 6 in the legend; 5 LED strips; 1 large pendant
    assert kinds["point"] == 72
    assert kinds["line"] == 5
    assert kinds["circle"] == 1
    assert s.has_architecture, s.arch_total


def test_geometry_fixtures_come_last():
    """`slide.picks` stores indexes into this list. Appending strips and
    circles in the middle would shift every saved manual pick."""
    kinds = [f.kind for f in surveyed().fixtures]
    first_geom = next((i for i, k in enumerate(kinds) if k != "point"), len(kinds))
    assert all(k == "point" for k in kinds[:first_geom])
    assert all(k != "point" for k in kinds[first_geom:])


def test_linear_fixtures_carry_their_run():
    for f in surveyed().fixtures:
        if f.kind == "line":
            assert len(f.pts) >= 2, f.layer
        if f.kind == "circle":
            assert f.radius > 0, f.layer


def test_annotation_layers_never_yield_fixtures():
    bad = {f.layer.lower() for f in surveyed().fixtures} & {
        "light text", "light dim", "light connectios", "strip text"}
    assert not bad, bad


def test_no_dimension_arrowheads_as_fixtures():
    s = surveyed()
    assert not any(f.code.startswith(("_", "*")) for f in s.fixtures)
    assert s.skipped_blocks.get("_ArchTick"), "the demo has tick marks to skip"


def test_declared_extents_lie_and_are_never_used():
    """$EXTMIN/$EXTMAX in real drawings were off by up to 128x."""
    import ezdxf
    doc = ezdxf.readfile(DEMO)
    declared = doc.header["$EXTMAX"][0] - doc.header["$EXTMIN"][0]
    s = surveyed()
    body, _ = framing.main_body([(f.x, f.y) for f in s.fixtures])
    real = max(p[0] for p in body) - min(p[0] for p in body)
    assert declared / real > 1000


def test_the_far_legend_is_separated_from_the_building():
    """The legend is 6 of 78 fixtures (7.7%), so 2–98% percentiles keep it."""
    pts = [(f.x, f.y) for f in surveyed().fixtures]
    assert surveyed().bounds()[0] < -20_000          # percentiles fall for it
    body, rest = framing.main_body(pts)
    assert min(p[0] for p in body) > -100            # main_body does not
    assert len(rest) == 6


def test_reversed_and_shx_text_is_decoded():
    texts = {a.text for a in surveyed().annotations}
    assert "הכנה לתאורה בארונות" in texts     # Hebrew stored as Latin keystrokes
    assert "WALL LIGHT" in texts             # typed right-to-left: "THGIL LLAW"
