"""
Tests for the track corner-distance override system.

Background (see docs/IRACING_TRACK_API_INVESTIGATION.md):
iRacing publishes no per-corner turn *positions* in any API or SDK — only a turn
*count* (.ibt WeekendInfo.TrackNumTurns, /data/track/get.corners_per_lap) and a
rendered SVG of the labels (/data/track/assets.track_map_layers.turns). So the
four corrupt corners in the community landmark file (barcelona gp T9, aragon gp
T10, aragon moto T10, martinsville T3) cannot be repaired from an API. They are
repaired at build time by tools/build_track_corner_overrides.py, which emits
tenths/data/track_corner_overrides.json, applied at load in track_map.py.

These tests encode the invariants that matter:
- The four known-corrupt tracks resolve their previously-dropped turn to the
  correct iRacing-standard number, asserted against the SHIPPED artifact so a
  regenerated artifact that loses a repair fails here.
- Overrides are applied BEFORE validation, so a repaired corner still runs the
  same range/length guards — a bad override cannot bypass them.
- A missing or malformed artifact degrades to today's behaviour (corner dropped),
  never crashes.
- TrackID keying is preferred over the slug and both resolve.
- The generator is deterministic (its --check mode passes on the shipped file).
"""

import json
import os

import pytest

import tenths.track_map as tm
from tenths.track_map import (
    load_track_map,
    get_turn_short,
    _load_from_landmarks,
    _apply_corner_overrides,
    _corrections_for,
    _load_overrides,
)

FIXTURE = os.path.join(os.path.dirname(__file__), 'fixtures',
                       'sample_track_corner_overrides.json')


@pytest.fixture(autouse=True)
def _reset_override_cache():
    """The override index is cached in a module global; reset around each test
    so monkeypatching _OVERRIDES_PATH takes effect and never leaks."""
    tm._overrides_cache = None
    yield
    tm._overrides_cache = None


class TestProductionArtifactRepairsTheFourCorruptTracks:
    """The invariant that matters: the four corrupt tracks resolve to correct,
    iRacing-standard turn numbers through the override path. Asserted against the
    SHIPPED artifact, per the steering rule 'encode invariants as tests'."""

    # slug -> the turn that was corrupt upstream and must now be present.
    RECOVERED = {
        'barcelona_gp': 'T9',
        'aragon_gp': 'T10',
        'aragon_moto': 'T10',
        'martinsville': 'T3',
    }

    @pytest.mark.parametrize("slug,turn", sorted(RECOVERED.items()))
    def test_previously_dropped_turn_is_present(self, slug, turn):
        zones = load_track_map(slug)
        turns = [z['turn'] for z in zones]
        assert turn in turns, (
            f"{slug} {turn} should be restored by the override artifact; "
            f"got {turns}")

    @pytest.mark.parametrize("slug,turn", sorted(RECOVERED.items()))
    def test_recovered_turn_labels_its_own_location(self, slug, turn):
        """The repaired corner must be reachable at its own centre — not just
        present in the list."""
        zones = load_track_map(slug)
        center = next(z['pct_center'] for z in zones if z['turn'] == turn)
        assert get_turn_short(zones, center) == turn

    def test_barcelona_has_a_complete_t1_to_t16_sequence(self):
        turns = [z['turn'] for z in load_track_map('barcelona_gp')]
        assert turns == [f'T{i}' for i in range(1, 17)]

    @pytest.mark.parametrize("slug,turn", sorted(RECOVERED.items()))
    def test_recovered_range_is_valid_and_in_lap(self, slug, turn):
        """A repaired corner must still satisfy the same range guarantees as any
        other zone: start <= end, both within 0..100."""
        z = next(z for z in load_track_map(slug) if z['turn'] == turn)
        lo, hi = z['pct_range']
        assert lo <= hi
        assert 0 <= lo <= 100 and 0 <= hi <= 100


class TestOverrideApplication:
    """_apply_corner_overrides transforms raw landmark records before validation."""

    def test_set_range_repairs_the_distance_pair(self):
        landmarks = [
            {'landmarkNames': ['turn1'], 'distanceRoundLapStart': 100,
             'distanceRoundLapEnd': 200},
            {'landmarkNames': ['turn2'], 'distanceRoundLapStart': 800,
             'distanceRoundLapEnd': 500},  # corrupt
        ]
        corrections = [{'names': ['turn2'], 'action': 'set_range',
                        'start': 500, 'end': 560}]
        out = _apply_corner_overrides(landmarks, corrections)
        assert out[1]['distanceRoundLapStart'] == 500
        assert out[1]['distanceRoundLapEnd'] == 560
        # Original list not mutated in place.
        assert landmarks[1]['distanceRoundLapEnd'] == 500

    def test_drop_action_leaves_record_for_the_validator(self):
        landmarks = [
            {'landmarkNames': ['turn1'], 'distanceRoundLapStart': 800,
             'distanceRoundLapEnd': 500},
        ]
        corrections = [{'names': ['turn1'], 'action': 'drop'}]
        out = _apply_corner_overrides(landmarks, corrections)
        # Unchanged — the load-time validator will drop it.
        assert out[0]['distanceRoundLapEnd'] == 500

    def test_no_corrections_returns_input_unchanged(self):
        landmarks = [{'landmarkNames': ['turn1'], 'distanceRoundLapStart': 1,
                      'distanceRoundLapEnd': 2}]
        assert _apply_corner_overrides(landmarks, []) is landmarks

    def test_unmatched_names_are_untouched(self):
        landmarks = [{'landmarkNames': ['turn1'], 'distanceRoundLapStart': 1,
                      'distanceRoundLapEnd': 2}]
        corrections = [{'names': ['turn99'], 'action': 'set_range',
                        'start': 5, 'end': 6}]
        out = _apply_corner_overrides(landmarks, corrections)
        assert out[0]['distanceRoundLapEnd'] == 2


class TestOverrideCannotBypassValidation:
    """An override is applied before validation, so a bad override that produces
    a still-corrupt range is still dropped — the guards are not weakened."""

    def test_override_producing_reversed_range_is_still_dropped(self, monkeypatch):
        entry = {
            'approximateTrackLength': 1000,
            'trackLandmarks': [
                {'landmarkNames': ['turn1'], 'distanceRoundLapStart': 100,
                 'distanceRoundLapEnd': 200},
                {'landmarkNames': ['turn2'], 'distanceRoundLapStart': 800,
                 'distanceRoundLapEnd': 500},
            ],
        }
        monkeypatch.setattr(tm, '_load_landmarks', lambda: {'fake': entry})
        # A malicious/buggy override that still reverses the range.
        monkeypatch.setattr(tm, '_load_overrides', lambda: {
            'by_slug': {'fake': [{'names': ['turn2'], 'action': 'set_range',
                                  'start': 900, 'end': 600}]},
            'by_id': {}})
        zones = _load_from_landmarks('fake')
        assert [z['turn'] for z in zones] == ['T1'], (
            "a reversed override range must still be caught by validation")

    def test_override_beyond_track_length_is_still_dropped(self, monkeypatch):
        entry = {
            'approximateTrackLength': 1000,
            'trackLandmarks': [
                {'landmarkNames': ['turn1'], 'distanceRoundLapStart': 100,
                 'distanceRoundLapEnd': 5000},
            ],
        }
        monkeypatch.setattr(tm, '_load_landmarks', lambda: {'fake': entry})
        monkeypatch.setattr(tm, '_load_overrides', lambda: {
            'by_slug': {'fake': [{'names': ['turn1'], 'action': 'set_range',
                                  'start': 100, 'end': 9000}]},
            'by_id': {}})
        assert _load_from_landmarks('fake') == []


class TestTrackIdKeying:
    """TrackID is preferred; the slug is the fallback."""

    def test_track_id_match_takes_precedence(self, monkeypatch):
        monkeypatch.setattr(tm, '_load_overrides', lambda: {
            'by_id': {439: [{'names': ['turn2'], 'action': 'set_range',
                             'start': 1, 'end': 2}]},
            'by_slug': {'other slug': [{'names': ['turn2'], 'action': 'drop'}]},
        })
        # Even with a mismatched slug, the id resolves the correction.
        got = _corrections_for('unrelated slug', 439)
        assert got and got[0]['action'] == 'set_range'

    def test_slug_fallback_when_id_unknown(self, monkeypatch):
        monkeypatch.setattr(tm, '_load_overrides', lambda: {
            'by_id': {},
            'by_slug': {'winton national': [{'names': ['turn1'],
                                             'action': 'drop'}]},
        })
        assert _corrections_for('winton national', None)
        # An id that isn't indexed still falls back to the slug.
        assert _corrections_for('winton national', 99999)

    def test_no_match_returns_empty(self, monkeypatch):
        monkeypatch.setattr(tm, '_load_overrides',
                            lambda: {'by_id': {}, 'by_slug': {}})
        assert _corrections_for('nothing', None) == []


class TestFixtureArtifactParsing:
    """A real captured-shape artifact (tests/fixtures/) parses into the index."""

    def test_sample_artifact_loads_both_indexes(self, monkeypatch):
        monkeypatch.setattr(tm, '_OVERRIDES_PATH', FIXTURE)
        idx = _load_overrides()
        assert 'sample track' in idx['by_slug']
        assert 'swap track' in idx['by_slug']
        # track_id 439 is indexed; the null-id track is not in by_id.
        assert 439 in idx['by_id']
        assert len(idx['by_id']) == 1

    def test_sample_artifact_matches_schema(self):
        with open(FIXTURE, encoding='utf-8') as f:
            data = json.load(f)
        assert data['schema_version'] == '1.0.0'
        for track in data['tracks']:
            assert 'slug' in track and 'corrections' in track
            for c in track['corrections']:
                assert c['action'] in ('set_range', 'drop')
                if c['action'] == 'set_range':
                    assert c['start'] < c['end']


class TestGracefulDegradation:
    """Missing or malformed artifact must not crash; behaves like no overrides."""

    def test_missing_file_yields_empty_index(self, monkeypatch, tmp_path):
        monkeypatch.setattr(tm, '_OVERRIDES_PATH', str(tmp_path / 'nope.json'))
        idx = _load_overrides()
        assert idx == {'by_slug': {}, 'by_id': {}}

    def test_malformed_json_yields_empty_index(self, monkeypatch, tmp_path):
        bad = tmp_path / 'bad.json'
        bad.write_text('{ not valid json', encoding='utf-8')
        monkeypatch.setattr(tm, '_OVERRIDES_PATH', str(bad))
        assert _load_overrides() == {'by_slug': {}, 'by_id': {}}

    def test_load_still_works_with_no_overrides(self, monkeypatch, tmp_path):
        """With overrides absent, a corrupt corner is dropped exactly as before
        the feature existed — proving the fallback is intact."""
        monkeypatch.setattr(tm, '_OVERRIDES_PATH', str(tmp_path / 'absent.json'))
        turns = [z['turn'] for z in load_track_map('barcelona_gp')]
        assert 'T9' not in turns  # dropped, not mislabelled
        assert 'T8' in turns and 'T10' in turns


class TestGeneratorIsUpToDate:
    """The shipped artifact must match what the generator produces, so a data
    refresh cannot silently drift from the tool that documents its provenance."""

    def test_check_mode_passes_on_shipped_artifact(self):
        from tools.build_track_corner_overrides import build_overrides, _serialise, OVERRIDES_PATH
        with open(OVERRIDES_PATH, encoding='utf-8') as f:
            current = f.read()
        # Preserve any backfilled track_ids the way --check does.
        known = {t['slug']: t['track_id']
                 for t in json.loads(current).get('tracks', [])
                 if t.get('track_id') is not None}
        assert _serialise(build_overrides(known)) == current, (
            "track_corner_overrides.json is stale; run "
            "tools/build_track_corner_overrides.py")

    def test_generator_detects_exactly_the_four_known_corruptions(self):
        from tools.build_track_corner_overrides import build_overrides
        art = build_overrides()
        found = {(t['slug'], c['names'][0])
                 for t in art['tracks'] for c in t['corrections']}
        assert found == {
            ('barcelona gp', 'turn9'),
            ('aragon gp', 'turn10'),
            ('aragon moto', 'turn10'),
            ('martinsville', 'turn3'),
        }, f"generator detections changed: {sorted(found)}"
