"""
Tests for the track map system (tenths/track_map.py).

Covers:
- Landmark data loading from bundled trackLandmarksData.json
- Slug conversion (underscore -> space)
- Distance-to-percentage conversion
- Landmark name formatting (turnX -> TX, named corners, esses)
- get_turn_name range-contains matching + tolerance fallback
- get_turn_short
- Fallback to .md files when landmark data is absent
"""

import pytest

from tenths.track_map import (
    load_track_map,
    get_turn_name,
    get_turn_short,
    _format_landmark_name,
    _load_from_landmarks,
    _load_landmarks,
)


class TestLandmarkLoading:
    """Tests for loading track data from the bundled landmark JSON."""

    def test_landmarks_file_loads(self):
        """The bundled landmark data loads and contains iRacing tracks."""
        landmarks = _load_landmarks()
        assert isinstance(landmarks, dict)
        assert len(landmarks) > 400, "Expected 450+ iRacing tracks in bundled data"

    def test_roadatlanta_loads_by_slug(self):
        """Road Atlanta loads from the underscore slug (roadatlanta_full)."""
        zones = load_track_map('roadatlanta_full')
        assert len(zones) == 13
        # All zones should have the required schema fields
        for z in zones:
            assert 'pct_center' in z
            assert 'pct_range' in z
            assert 'turn' in z
            assert 'full' in z

    def test_coronado_loads(self):
        """Coronado loads with 18 zones."""
        zones = load_track_map('coronado')
        assert len(zones) == 18

    def test_slug_underscore_to_space_conversion(self):
        """Underscore slug matches space-separated CrewChief key.

        'roadatlanta_full' (iRacing .ibt slug) -> 'roadatlanta full' (CrewChief key).
        """
        zones = _load_from_landmarks('roadatlanta_full')
        assert len(zones) > 0, "Underscore slug should match space-separated CrewChief key"

    def test_track_with_empty_landmarks_returns_empty(self):
        """A track present in the data but with no mapped corners returns empty.

        'summit summit raceway' exists in CrewChief data but has an empty
        trackLandmarks array — should return [] so load_track_map falls back to .md.
        """
        zones = _load_from_landmarks('summit_summit_raceway')
        assert zones == []

    def test_unknown_track_returns_empty(self):
        """A track not in the landmark data returns empty from landmarks."""
        zones = _load_from_landmarks('nonexistent_track_xyz')
        assert zones == []

    def test_distance_converted_to_percentage(self):
        """Distances in meters are converted to 0-100 percentages."""
        zones = load_track_map('roadatlanta_full')
        for z in zones:
            lo, hi = z['pct_range']
            assert 0 <= lo <= 100
            assert 0 <= hi <= 100
            assert lo <= hi

    def test_dist_range_present_for_landmarks(self):
        """Landmark-sourced zones carry the original distance range."""
        zones = load_track_map('roadatlanta_full')
        for z in zones:
            assert z['dist_range'] is not None
            assert len(z['dist_range']) == 2


class TestLandmarkNameFormatting:
    """Tests for _format_landmark_name."""

    def test_plain_turn_number(self):
        """'turn5' -> ('T5', '', 'T5')"""
        turn, name, full = _format_landmark_name(['turn5'])
        assert turn == 'T5'
        assert full == 'T5'

    def test_turn_with_letter_suffix(self):
        """'turn10a' -> 'T10A'"""
        turn, name, full = _format_landmark_name(['turn10a'])
        assert turn == 'T10A'

    def test_named_corner(self):
        """'canada_corner' -> ('Canada Corner', 'Canada Corner', 'Canada Corner')"""
        turn, name, full = _format_landmark_name(['canada_corner'])
        assert name == 'Canada Corner'
        assert full == 'Canada Corner'

    def test_turn_number_and_name_combined(self):
        """['the_esses', 'turn5'] -> 'T5 Esses' (turn number found in position 1)."""
        turn, name, full = _format_landmark_name(['the_esses', 'turn5'])
        assert turn == 'T5'
        assert full == 'T5 Esses'

    def test_the_prefix_stripped(self):
        """'the_esses' -> 'Esses' (leading 'The ' removed)."""
        turn, name, full = _format_landmark_name(['the_esses'])
        assert name == 'Esses'

    def test_the_prefix_only_stripped_at_start(self):
        """'theatre_corner' should NOT become 'atre Corner' (substring bug guard)."""
        turn, name, full = _format_landmark_name(['theatre_corner'])
        assert 'atre' not in full.lower() or full.lower().startswith('theatre')
        assert full == 'Theatre Corner'

    def test_empty_names(self):
        """Empty list returns placeholder."""
        turn, name, full = _format_landmark_name([])
        assert turn == '?'


class TestGetTurnName:
    """Tests for get_turn_name matching logic."""

    def _map(self):
        return [
            {'pct_center': 5.0, 'pct_range': (3, 7), 'dist_range': None, 'turn': 'T1', 'name': '', 'full': 'T1'},
            {'pct_center': 50.0, 'pct_range': (48, 52), 'dist_range': None, 'turn': 'T5', 'name': 'Hairpin', 'full': 'T5 Hairpin'},
            {'pct_center': 82.0, 'pct_range': (80, 84), 'dist_range': None, 'turn': 'T10', 'name': '', 'full': 'T10'},
        ]

    def test_exact_range_match(self):
        """A pct inside a zone range returns that zone."""
        assert get_turn_name(self._map(), 50.0) == 'T5 Hairpin'
        assert get_turn_name(self._map(), 5.0) == 'T1'

    def test_range_boundary_inclusive(self):
        """Range boundaries are inclusive."""
        assert get_turn_name(self._map(), 48.0) == 'T5 Hairpin'
        assert get_turn_name(self._map(), 52.0) == 'T5 Hairpin'

    def test_tolerance_fallback(self):
        """A pct just outside a range but within tolerance matches the closest."""
        # 8.5 is outside T1 (3-7) but within 5% of center (5.0)
        assert get_turn_name(self._map(), 8.5) == 'T1'

    def test_no_match_returns_percentage(self):
        """A pct far from any zone returns the percentage fallback."""
        result = get_turn_name(self._map(), 30.0)
        assert result == '(30.0%)'

    def test_empty_map_returns_percentage(self):
        """An empty map returns the percentage fallback."""
        assert get_turn_name([], 42.0) == '(42.0%)'

    def test_boundary_no_ambiguity(self):
        """Densely packed corners resolve to the correct one by range (the TM2 bug)."""
        # Two adjacent zones — a pct in the gap should pick the closer center
        dense = [
            {'pct_center': 72.0, 'pct_range': (71, 73), 'dist_range': None, 'turn': 'T11', 'name': 'Kink', 'full': 'T11 Kink'},
            {'pct_center': 82.5, 'pct_range': (76, 89), 'dist_range': None, 'turn': 'T12', 'name': 'Canada', 'full': 'T12 Canada'},
        ]
        # 76.9 is inside T12's range (76-89) -> must be T12, not T11
        assert get_turn_name(dense, 76.9) == 'T12 Canada'


class TestGetTurnShort:
    """Tests for get_turn_short."""

    def _map(self):
        return [
            {'pct_center': 50.0, 'pct_range': (48, 52), 'dist_range': None, 'turn': 'T5', 'name': 'Hairpin', 'full': 'T5 Hairpin'},
        ]

    def test_returns_turn_only(self):
        """Returns just the turn label, not the full name."""
        assert get_turn_short(self._map(), 50.0) == 'T5'

    def test_empty_map(self):
        assert get_turn_short([], 42.0) == '42.0%'


class TestMdFallback:
    """Tests for the .md file fallback path."""

    def test_winton_still_loads(self):
        """Winton National loads (either from landmarks or .md fallback)."""
        zones = load_track_map('winton_national')
        assert len(zones) > 0

    def test_all_zones_have_consistent_schema(self):
        """Both landmark and .md zones expose the same keys."""
        for slug in ['roadatlanta_full', 'winton_national']:
            zones = load_track_map(slug)
            for z in zones:
                assert set(z.keys()) >= {'pct_center', 'pct_range', 'dist_range', 'turn', 'name', 'full'}
