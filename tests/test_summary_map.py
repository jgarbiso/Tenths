"""
Tests for the Summary-tab mini-map.

The map was a fixed 280x280 square drawing every circuit at a single scale for
both axes, with corner labels at a fixed offset above their marker. On a wide
track that wasted most of the canvas, and two coached corners close together —
T12 and T13 at COTA are 4.9% of a lap apart — put their labels on top of each
other with no way to tell which belonged to which.

These are source-level assertions. The drawing itself is canvas calls inside a
JavaScript string, which Python cannot execute, so the guards pin the properties
that made the old version unreadable.
"""

import re

import pytest

from tenths.report import _get_js, _get_summary_js, _get_css, _get_summary_css


@pytest.fixture(scope="module")
def summary_js():
    return _get_summary_js()


@pytest.fixture(scope="module")
def css():
    return _get_css() + _get_summary_css()


class TestMapSizing:
    """The canvas follows the circuit's proportions instead of being square."""

    def test_height_is_computed_not_fixed(self, summary_js):
        assert "canvas.style.height" in summary_js, (
            "height must be derived from the track, not fixed in CSS")

    def test_height_is_rounded(self, summary_js):
        """A fractional CSS height leaves a blurry backing store."""
        assert re.search(r"h = Math\.round\(", summary_js)

    def test_height_is_clamped(self, summary_js):
        """An extreme aspect ratio must not produce a 20px or 3000px canvas."""
        assert re.search(r"Math\.max\(240,\s*Math\.min\(h,\s*560\)\)", summary_js)

    def test_longitude_is_scaled_by_latitude(self, summary_js):
        """A degree of longitude is shorter than a degree of latitude.

        Without this the circuit is stretched horizontally — about 16% at COTA —
        and the mini-map disagrees with the Leaflet map on the Detailed tab.
        """
        assert "Math.cos(midLat" in summary_js
        assert "lonSquash" in summary_js

    def test_canvas_markup_has_no_fixed_dimensions(self):
        """A width/height attribute pair would fight the computed sizing."""
        from tenths.report import _build_html
        html = _build_html("{}", "Car", "Track", "2026-01-01", "1:00.000", None)
        canvas = re.search(r'<canvas id="mini-map"[^>]*>', html)
        assert canvas, "mini-map canvas missing"
        assert "width=" not in canvas.group(0)
        assert "height=" not in canvas.group(0)

    def test_map_column_is_wider_than_the_old_square(self, css):
        """280px left no room for labels outside the circuit."""
        match = re.search(r"\.summary-right\s*\{[^}]*flex:\s*0 0 clamp\((\d+)px", css)
        assert match, "summary-right should size with a clamp()"
        assert int(match.group(1)) >= 360


class TestLabelPlacement:
    """Two coached corners close together must still be tellable apart."""

    def test_labels_are_separated_not_fixed_offset(self, summary_js):
        """The old code drew every label at y - 12 regardless of neighbours."""
        assert "measureText" in summary_js, "chip width must be measured"
        assert re.search(r"for \(let iter = 0; iter < \d+; iter\+\+\)", summary_js), (
            "labels need a bounded separation pass")

    def test_separation_terminates(self, summary_js):
        """A relaxation loop with no bound would hang the report."""
        match = re.search(r"for \(let iter = 0; iter < (\d+); iter\+\+\)", summary_js)
        assert match and int(match.group(1)) <= 200

    def test_labels_are_clamped_inside_the_canvas(self, summary_js):
        """Pushing a chip apart must not push it off the edge."""
        assert "Math.min(w - f.chipW / 2" in summary_js
        assert "Math.min(h - chipH / 2" in summary_js

    def test_leader_lines_connect_chip_to_marker(self, summary_js):
        """Once a label moves, it needs a line back to the corner it describes."""
        assert "moveTo(f.x, f.y)" in summary_js
        assert "lineTo(f.lx, f.ly)" in summary_js

    def test_chip_has_an_opaque_background(self, summary_js):
        """The track outline used to run straight through the label text."""
        assert "rgba(10, 10, 15, 0.94)" in summary_js

    def test_round_rect_has_a_fallback(self, summary_js):
        """A missing roundRect would throw and kill the whole summary render."""
        assert "if (ctx.roundRect)" in summary_js
        assert re.search(r"ctx\.rect\(x0, y0", summary_js)


class TestRankNumbering:
    """The number in a marker ties it to the card that explains it."""

    def test_marker_carries_its_rank(self, summary_js):
        assert "String(f.rank)" in summary_js

    def test_next_focus_is_rank_one(self, summary_js):
        assert '<span class="focus-rank">1</span>' in summary_js

    def test_cards_continue_the_numbering(self, summary_js):
        assert re.search(r'class="focus-rank">\$\{i \+ 2\}', summary_js)

    def test_ranks_come_from_the_rendered_dom(self, summary_js):
        """renderNextFocus applies its own selection rules and fallbacks, so its
        corner is not always coachingData[0]. Deriving ranks from coachingData
        order would silently mislabel the markers."""
        assert "rankByTurn" in summary_js
        assert "#focus-cards .focus-card" in summary_js
        assert "getElementById('next-focus')?.dataset?.turn" in summary_js

    def test_rank_badge_is_styled(self, css):
        assert ".focus-rank" in css
        match = re.search(r"\.focus-rank\s*\{([^}]*)\}", css)
        assert match
        body = match.group(1)
        assert "border-radius: 50%" in body, "rank badge should read as a marker"


class TestMapLegend:
    """A number with no explanation is a puzzle."""

    def test_caption_explains_the_numbering(self):
        from tenths.report import _build_html
        html = _build_html("{}", "Car", "Track", "2026-01-01", "1:00.000", None)
        assert "mini-map-caption" in html
        assert "match the cards" in html
