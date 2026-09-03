"""
Tests for corner labels on the Detailed-tab track map.

Regression guarded here: the Detailed map has two draw paths — initMap() on
first render and rebuildMap() on rotate / lap change. The "label every known
corner, not just detected braking zones" feature was originally added to
rebuildMap() only, so a freshly opened report showed labels for the two or three
detected braking zones and nothing else. All corners appeared only after the
user happened to rotate the map. See commit history around drawCornerLabels().

The fix put both label passes in one helper, drawCornerLabels(), that both draw
paths call. These are source-level assertions: the drawing is Leaflet calls
inside a JavaScript string that Python cannot execute, so the guards pin the
structure that keeps the two paths from drifting apart again, and a behavioural
check (below) confirms every landmark actually produces a label.
"""

import re

import pytest

from tenths.report import _get_js, _get_css


@pytest.fixture(scope="module")
def js():
    return _get_js()


@pytest.fixture(scope="module")
def css():
    return _get_css()


class TestSingleDrawPath:
    """Both map draw paths must route through the one shared helper."""

    def test_helper_exists(self, js):
        assert "function drawCornerLabels(rotatedTrace, rotatedBraking)" in js

    def test_initmap_calls_the_helper(self, js):
        """First render must draw all corners, not only braking zones."""
        init = _function_body(js, "initMap")
        assert "drawCornerLabels(" in init, (
            "initMap must call drawCornerLabels — this is the regression that "
            "left a freshly opened report showing only braking-zone labels")

    def test_rebuildmap_calls_the_helper(self, js):
        rebuild = _function_body(js, "rebuildMap")
        assert "drawCornerLabels(" in rebuild

    def test_neither_path_reimplements_the_label_loop(self, js):
        """The braking-label tooltip must be created in exactly one place.

        If a draw path grows its own copy of the loop again, the two paths can
        diverge — which is exactly how the passive pass ended up in only one.
        """
        init = _function_body(js, "initMap")
        rebuild = _function_body(js, "rebuildMap")
        assert "className: 'corner-label'" not in init
        assert "className: 'corner-label'" not in rebuild
        assert "className: 'landmark-label'" not in init
        assert "className: 'landmark-label'" not in rebuild


class TestPassivePass:
    """The helper draws a passive label for every non-braking corner."""

    def test_helper_reads_all_landmarks(self, js):
        body = _function_body(js, "drawCornerLabels")
        assert "DATA.track_landmarks" in body

    def test_helper_draws_both_label_classes(self, js):
        body = _function_body(js, "drawCornerLabels")
        assert "className: 'corner-label'" in body
        assert "className: 'landmark-label'" in body

    def test_dedupe_is_by_name_not_proximity(self, js):
        """A landmark is skipped only when a braking zone carries the SAME turn
        name. The old code skipped any landmark within 5% of a braking zone,
        which silently hid distinct neighbours on tightly packed sections."""
        body = _function_body(js, "drawCornerLabels")
        assert "brakingNames" in body, "dedupe must key on turn name"
        # The old proximity window must not come back.
        assert "Math.abs(z.pct - lm.pct) < 5" not in body
        assert "brakingPcts" not in body


class TestLegibility:
    """Passive labels must be readable on the near-black map."""

    def test_landmark_colour_is_not_the_old_dim_value(self, css):
        match = re.search(r"\.landmark-label\s*\{([^}]*)\}", css)
        assert match, ".landmark-label rule missing"
        body = match.group(1)
        colour = re.search(r"color:\s*(#[0-9a-fA-F]{6})", body)
        assert colour, ".landmark-label must set an explicit colour"
        assert colour.group(1).lower() != "#5a6178", (
            "the old #5a6178 vanished against the #0a0a0f map background")


class TestAllCornersRenderedBehaviourally:
    """Execute drawCornerLabels under a stubbed Leaflet and count the labels.

    A source assertion proves the code is present; this proves it produces one
    label per corner with no duplicates. Skips cleanly if Node is unavailable so
    the suite still runs on a machine without it.
    """

    def test_every_corner_gets_exactly_one_label(self, js):
        node = _which_node()
        if not node:
            pytest.skip("node not available")

        import json
        import subprocess
        import tempfile
        import os

        from tenths.report import _get_js as _  # ensure import path is exercised

        fn = _function_body(js, "drawCornerLabels", include_signature=True)

        # Two landmarks; one of them shares a braking zone's turn name and must
        # be deduped, the other is a distinct neighbour and must survive.
        data = {
            "gps_trace": [
                {"pct": p * 0.5, "lat": 33.5 + p * 1e-4, "lon": -86.6 + p * 1e-4}
                for p in range(200)
            ],
            "braking_zones": [
                {"pct": 24.0, "turn_name": "T5 Some Corner",
                 "lat": 33.51, "lon": -86.61},
            ],
            "track_landmarks": [
                {"pct": 24.0, "turn": "T5", "name": "T5 Some Corner"},
                {"pct": 60.0, "turn": "T11", "name": "T11 Another"},
            ],
        }

        harness = (
            "const DATA = " + json.dumps(data) + ";\n"
            "let labels = [];\n"
            "let map = {};\n"
            "const L = {\n"
            "  circleMarker: () => ({ addTo: () => {} }),\n"
            "  tooltip: (opts) => { const o = { content: null,\n"
            "    addTo: () => { labels.push({ cls: opts.className, content: o.content }); },\n"
            "    setContent: (c) => { o.content = c; }, setLatLng: () => {} }; return o; },\n"
            "};\n"
            + fn + "\n"
            "const rt = DATA.gps_trace.map(p => ({ ...p, rlat: p.lat, rlon: p.lon }));\n"
            "const rb = DATA.braking_zones.map(z => ({ ...z, rlat: z.lat, rlon: z.lon }));\n"
            "drawCornerLabels(rt, rb);\n"
            "const corner = labels.filter(l => l.cls === 'corner-label').map(l => l.content);\n"
            "const passive = labels.filter(l => l.cls === 'landmark-label').map(l => l.content);\n"
            "console.log(JSON.stringify({ corner, passive }));\n"
        )

        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                         encoding="utf-8") as f:
            f.write(harness)
            path = f.name
        try:
            r = subprocess.run([node, path], capture_output=True, text=True)
        finally:
            os.unlink(path)

        assert r.returncode == 0, f"node failed: {r.stderr}"
        out = json.loads(r.stdout.strip().splitlines()[-1])

        # The braking zone is labelled once.
        assert out["corner"] == ["T5 Some Corner"]
        # The distinct neighbour survives; the shared-name landmark is deduped.
        assert out["passive"] == ["T11 Another"], (
            f"expected only the distinct neighbour as a passive label, got "
            f"{out['passive']}")


def _function_body(js, name, include_signature=False):
    """Return the source of a top-level `function name(...) { ... }` block.

    Brace-matches from the function's opening brace so a nested object literal
    does not end the block early.
    """
    start = js.index(f"function {name}(")
    brace = js.index("{", start)
    depth = 0
    i = brace
    while i < len(js):
        c = js[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    body = js[brace:i + 1]
    return js[start:i + 1] if include_signature else body


def _which_node():
    import shutil
    return shutil.which("node")
