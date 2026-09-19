"""
Track data integrity guards for tenths/track_map.py.

The bundled trackLandmarksData.json is CrewChief's community-maintained data.
It carried four corners whose end distance precedes their start (a reversed
range), which get_turn_name could never range-match — so the stretch fell to the
nearest-neighbour fallback and was labelled with the WRONG turn. A wrong name is
worse than an absent one, and track_map.py had no validation of any kind.

_load_from_landmarks now drops any corner where end <= start or end exceeds the
track length. These tests assert against the PRODUCTION data file, so a future
CrewChief refresh that reintroduces a bad record fails the suite rather than
shipping a wrong turn name silently. They also pin two things that must NOT
change: valid but out-of-lap-order corners (montreal, nordschleife) must still
load in full, and the fuzzy tolerance must behave as a fixed distance so it means
the same thing on a bullring and the Nordschleife.
"""

import pytest

from tenths.track_map import (
    load_track_map,
    get_turn_name,
    _load_from_landmarks,
    _tolerance_pct,
    _ensure_unique_full_names,
    DEFAULT_TOLERANCE_M,
    DEFAULT_TOLERANCE_PCT,
)


def _fake_entry(landmarks, length=1000):
    """Build a minimal landmark entry dict as _load_from_landmarks expects."""
    return {
        'approximateTrackLength': length,
        'trackLandmarks': landmarks,
    }


class TestCorruptRecordsRejected:
    """A reversed or out-of-bounds corner must be dropped, not mislabelled."""

    def test_reversed_range_is_dropped(self, monkeypatch):
        import tenths.track_map as tm
        entry = _fake_entry([
            {'landmarkNames': ['turn1'], 'distanceRoundLapStart': 100,
             'distanceRoundLapEnd': 200},
            {'landmarkNames': ['turn2'], 'distanceRoundLapStart': 800,
             'distanceRoundLapEnd': 500},  # reversed
        ])
        monkeypatch.setattr(tm, '_load_landmarks', lambda: {'fake': entry})
        zones = _load_from_landmarks('fake')
        turns = [z['turn'] for z in zones]
        assert turns == ['T1'], f"reversed T2 should be dropped, got {turns}"

    def test_corner_beyond_track_length_is_dropped(self, monkeypatch):
        import tenths.track_map as tm
        entry = _fake_entry([
            {'landmarkNames': ['turn1'], 'distanceRoundLapStart': 100,
             'distanceRoundLapEnd': 200},
            {'landmarkNames': ['turn2'], 'distanceRoundLapStart': 900,
             'distanceRoundLapEnd': 1200},  # end 1200 > length 1000
        ], length=1000)
        monkeypatch.setattr(tm, '_load_landmarks', lambda: {'fake': entry})
        zones = _load_from_landmarks('fake')
        assert [z['turn'] for z in zones] == ['T1']

    def test_dropped_corner_degrades_to_percentage_not_neighbour(self, monkeypatch):
        """The stretch a dropped corner owned must NOT borrow a neighbour's
        name at its far end — it must fall back to a percentage."""
        import tenths.track_map as tm
        entry = _fake_entry([
            {'landmarkNames': ['turn1'], 'distanceRoundLapStart': 50,
             'distanceRoundLapEnd': 90},
            # turn2 would have owned the middle of the lap; it is corrupt.
            {'landmarkNames': ['turn2'], 'distanceRoundLapStart': 600,
             'distanceRoundLapEnd': 400},
            {'landmarkNames': ['turn3'], 'distanceRoundLapStart': 910,
             'distanceRoundLapEnd': 950},
        ], length=1000)
        monkeypatch.setattr(tm, '_load_landmarks', lambda: {'fake': entry})
        zones = _load_from_landmarks('fake')
        # 50% is deep in the dropped corner's territory, far from T1 (~7%) and
        # T3 (~93%). It must report a percentage, not a neighbour.
        assert get_turn_name(zones, 50.0) == '(50.0%)'


class TestProductionDataIsClean:
    """Assert against the shipped data file so a bad refresh fails here."""

    # Track slug -> the corner (short label) that was corrupt upstream.
    KNOWN_BAD = {
        'barcelona_gp': 'T9',
        'aragon_gp': 'T10',
        'aragon_moto': 'T10',
        'martinsville': 'T3',
    }

    @pytest.mark.parametrize("slug", sorted(KNOWN_BAD))
    def test_no_reversed_ranges_survive(self, slug):
        zones = load_track_map(slug)
        assert zones, f"{slug} should load some corners"
        for z in zones:
            lo, hi = z['pct_range']
            assert lo <= hi, (
                f"{slug} has a reversed range {z['pct_range']} on {z['full']} — "
                f"validation should have dropped it")

    @pytest.mark.parametrize("slug", sorted(KNOWN_BAD))
    def test_no_range_exceeds_the_lap(self, slug):
        for z in load_track_map(slug):
            lo, hi = z['pct_range']
            assert 0 <= lo <= 100 and 0 <= hi <= 100, (
                f"{slug} {z['full']} range {z['pct_range']} out of 0-100")

    def test_no_two_zones_share_a_full_name(self):
        """report.py joins on the full name with .find(); collisions corrupt it."""
        for slug in ['barcelona_gp', 'aragon_gp', 'martinsville', 'cota_gp',
                     'roadatlanta_full', 'montreal',
                     'nurburgring_nordschleifetourist']:
            zones = load_track_map(slug)
            fulls = [z['full'] for z in zones]
            assert len(fulls) == len(set(fulls)), (
                f"{slug} has duplicate turn names: {fulls}")


class TestValidCornersPreserved:
    """Out-of-lap-order but valid corners must NOT be caught by validation."""

    def test_montreal_loads_all_corners(self):
        # montreal lists corners out of lap order but every range is valid.
        zones = load_track_map('montreal')
        assert len(zones) == 11, (
            f"montreal should keep all 11 corners, got {len(zones)}")

    def test_nordschleife_loads_all_corners(self):
        zones = load_track_map('nurburgring_nordschleifetourist')
        assert len(zones) == 41, (
            f"nordschleife should keep all 41 corners, got {len(zones)}")

    def test_only_the_four_known_bad_corners_are_dropped(self):
        """Audit the whole production file: validation must reject exactly the
        four reversed records and nothing else. A stricter rule that also
        discarded valid corners would be a regression, not a fix."""
        import json
        from tenths.track_map import _LANDMARKS_PATH, _LENGTH_GRACE_FRACTION

        with open(_LANDMARKS_PATH, encoding='utf-8') as f:
            raw = json.load(f)

        dropped = []
        for entry in raw.get('trackLandmarksData', []):
            slug = entry.get('irTrackName')
            length = entry.get('approximateTrackLength', 0)
            lms = entry.get('trackLandmarks') or []
            if not slug or not lms or length <= 0:
                continue
            for lm in lms:
                start = lm.get('distanceRoundLapStart', 0)
                end = lm.get('distanceRoundLapEnd', 0)
                if end <= start or end > length * (1 + _LENGTH_GRACE_FRACTION):
                    dropped.append((slug, ','.join(lm.get('landmarkNames') or [])))

        assert sorted(dropped) == sorted([
            ('aragon gp', 'turn10'),
            ('aragon moto', 'turn10'),
            ('barcelona gp', 'turn9'),
            ('martinsville', 'turn3'),
        ]), f"validation drops changed: {sorted(dropped)}"


class TestApproximateLengthOverrunIsClamped:
    """`approximateTrackLength` is approximate, so a corner may end a metre or
    two past it. Those are real corners and must be kept, not dropped."""

    def test_nordschleife_t13_survives_a_1m_overrun(self):
        # ends 20639 m on a track recorded as 20638 m
        zones = load_track_map('nurburgring_nordschleife')
        assert any(z['turn'] == 'T13' for z in zones), (
            "nordschleife T13 ends 1m past the approximate length and must be "
            "clamped, not dropped")

    def test_virginia_patriot_t1_survives_a_2m_overrun(self):
        zones = load_track_map('virginia_2022_patriot')
        assert any(z['turn'] == 'T1' for z in zones)

    def test_clamped_corner_stays_within_the_lap(self):
        for slug in ('nurburgring_nordschleife', 'virginia_2022_patriot'):
            for z in load_track_map(slug):
                assert z['pct_range'][1] <= 100.0

    def test_a_wild_overrun_is_still_dropped(self, monkeypatch):
        """The grace margin must not swallow genuinely corrupt data."""
        import tenths.track_map as tm
        entry = _fake_entry([
            {'landmarkNames': ['turn1'], 'distanceRoundLapStart': 100,
             'distanceRoundLapEnd': 200},
            {'landmarkNames': ['turn2'], 'distanceRoundLapStart': 900,
             'distanceRoundLapEnd': 5000},  # 5x the track length
        ], length=1000)
        monkeypatch.setattr(tm, '_load_landmarks', lambda: {'fake': entry})
        assert [z['turn'] for z in _load_from_landmarks('fake')] == ['T1']


class TestDuplicateNameDisambiguation:
    """_ensure_unique_full_names must suffix collisions, not drop or reorder."""

    def test_duplicate_names_are_suffixed(self):
        zones = [
            {'full': 'T8', 'pct_center': 58.0},
            {'full': 'T8', 'pct_center': 61.0},
        ]
        _ensure_unique_full_names(zones)
        assert zones[0]['full'] == 'T8'
        assert zones[1]['full'] == 'T8 (61%)'
        assert zones[0]['full'] != zones[1]['full']


class TestDistanceBasedTolerance:
    """The fuzzy tolerance is a fixed distance, so it is consistent across
    tracks of wildly different length — the mechanism that used to turn a
    'no match' into a confidently wrong neighbour."""

    def test_long_track_gets_a_much_tighter_tolerance(self):
        """The whole point: 5% of the Nordschleife was 946 m."""
        long = load_track_map('nurburgring_nordschleifetourist')
        tol = _tolerance_pct(long, DEFAULT_TOLERANCE_M)
        assert tol < 1.0, f"expected well under 1% on a 19 km lap, got {tol:.2f}%"

    def test_metre_tolerance_matches_expected_percentage(self):
        long = load_track_map('nurburgring_nordschleifetourist')
        length = long[0]['track_length_m']
        expected = (DEFAULT_TOLERANCE_M / length) * 100.0
        assert _tolerance_pct(long, DEFAULT_TOLERANCE_M) == pytest.approx(expected)

    def test_tolerance_is_never_looser_than_the_legacy_percentage(self):
        """A pure metre tolerance overcorrects on short tracks — 150 m is 76% of
        a lap at `iowa legends` (198 m), which would name a corner from
        three-quarters of a lap away. The converted value is capped so this rule
        can only ever tighten matching, never widen it. Audited across every
        track in the production file."""
        import json
        from tenths.track_map import _LANDMARKS_PATH

        with open(_LANDMARKS_PATH, encoding='utf-8') as f:
            raw = json.load(f)

        offenders = []
        for entry in raw.get('trackLandmarksData', []):
            slug = entry.get('irTrackName')
            if not slug:
                continue
            zones = load_track_map(slug.replace(' ', '_'))
            if not zones or not zones[0].get('track_length_m'):
                continue
            tol = _tolerance_pct(zones, DEFAULT_TOLERANCE_M)
            if tol > DEFAULT_TOLERANCE_PCT + 1e-9:
                offenders.append((slug, tol))

        assert offenders == [], (
            f"{len(offenders)} tracks got a looser tolerance than the legacy "
            f"{DEFAULT_TOLERANCE_PCT}%: {offenders[:5]}")

    def test_very_short_track_caps_at_the_legacy_percentage(self):
        """198 m lap: 150 m would be 76% of the lap, so it must cap."""
        tiny = load_track_map('iowa_legends')
        if not tiny or not tiny[0].get('track_length_m'):
            pytest.skip('iowa legends has no landmark corners')
        assert _tolerance_pct(tiny, DEFAULT_TOLERANCE_M) == DEFAULT_TOLERANCE_PCT

    def test_md_map_without_length_falls_back_to_percentage(self):
        """A map carrying no track_length_m (the .md path) uses the legacy
        percentage tolerance rather than crashing or matching nothing."""
        md_like = [
            {'pct_center': 5.0, 'pct_range': (3, 7), 'turn': 'T1', 'full': 'T1'},
        ]
        assert _tolerance_pct(md_like, DEFAULT_TOLERANCE_M) == DEFAULT_TOLERANCE_PCT
        # 8.5 is 3.5% from center, inside the 5% legacy tolerance -> matches.
        assert get_turn_name(md_like, 8.5) == 'T1'
