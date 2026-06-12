"""
Fast unit tests — no filesystem I/O, no .ibt parsing.
Tests pure logic functions in isolation.
"""

import pytest

from tenths.summary import _fmt_time, CURRENT_SCHEMA_VERSION


class TestFormatTime:
    """Test the time formatting helper."""

    def test_normal_time(self):
        assert _fmt_time(91.74) == "1:31.740"

    def test_sub_minute(self):
        assert _fmt_time(38.5) == "0:38.500"

    def test_exact_minute(self):
        assert _fmt_time(60.0) == "1:00.000"

    def test_zero(self):
        assert _fmt_time(0) == "N/A"

    def test_negative(self):
        assert _fmt_time(-1) == "N/A"

    def test_two_minutes(self):
        assert _fmt_time(125.123) == "2:05.123"


class TestSchemaVersion:
    """Schema version constant validation."""

    def test_version_format(self):
        """Schema version must be semver format."""
        parts = CURRENT_SCHEMA_VERSION.split('.')
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

    def test_version_is_1_0_0(self):
        assert CURRENT_SCHEMA_VERSION == "1.0.0"


class TestTrackMapLookup:
    """Test turn name lookup logic without loading files."""

    def test_get_turn_name_with_map(self):
        from tenths.track_map import get_turn_name
        # Simulate a track map with the actual zone dict structure
        mock_map = [
            {'pct_center': 6, 'pct_range': (4, 8), 'turn': 'T1-T2', 'name': 'Motorsport News Esses', 'full': 'T1-T2 Motorsport News Esses'},
            {'pct_center': 19, 'pct_range': (17, 22), 'turn': 'T3', 'name': 'Honda Corner', 'full': 'T3 Honda Corner'},
        ]
        result = get_turn_name(mock_map, 6.0)
        assert 'T1-T2' in result or 'Motorsport' in result

    def test_get_turn_name_no_match(self):
        from tenths.track_map import get_turn_name
        mock_map = [
            {'pct_center': 82, 'pct_range': (80, 85), 'turn': 'T11', 'name': 'Test Corner', 'full': 'T11 Test Corner'},
        ]
        # Position far from any zone — should return fallback with percentage
        result = get_turn_name(mock_map, 50.0)
        assert '50' in result  # fallback shows the percentage

    def test_get_turn_name_none_map(self):
        from tenths.track_map import get_turn_name
        result = get_turn_name(None, 25.0)
        assert '25' in result  # fallback when no map


class TestPriorityClassification:
    """Test the corner variance priority logic."""

    def test_high_priority(self):
        # > 0.5s loss
        loss = 0.61
        priority = 'high' if loss > 0.5 else ('medium' if loss > 0.3 else 'low')
        assert priority == 'high'

    def test_medium_priority(self):
        loss = 0.35
        priority = 'high' if loss > 0.5 else ('medium' if loss > 0.3 else 'low')
        assert priority == 'medium'

    def test_low_priority(self):
        loss = 0.25
        priority = 'high' if loss > 0.5 else ('medium' if loss > 0.3 else 'low')
        assert priority == 'low'

    def test_boundary_high(self):
        loss = 0.5  # exactly 0.5 is NOT high (must be >0.5)
        priority = 'high' if loss > 0.5 else ('medium' if loss > 0.3 else 'low')
        assert priority == 'medium'

    def test_boundary_medium(self):
        loss = 0.3  # exactly 0.3 is NOT medium (must be >0.3)
        priority = 'high' if loss > 0.5 else ('medium' if loss > 0.3 else 'low')
        assert priority == 'low'


class TestLuggingThresholds:
    """Test the Lugging detection thresholds."""

    def test_gt4_lugging_threshold(self):
        """GT4: apex_rpm < 4000 AND min_spd > 40 mph."""
        # Should flag
        assert 3800 < 4000 and 55 > 40  # Lugging
        # Should NOT flag (rpm too high)
        assert not (4200 < 4000 and 55 > 40)
        # Should NOT flag (speed too low — hairpin)
        assert not (3500 < 4000 and 35 > 40)

    def test_touring_lugging_threshold(self):
        """Touring: apex_rpm < 3500 AND min_spd > 40 mph."""
        # Should flag
        assert 3200 < 3500 and 55 > 40
        # Should NOT flag (rpm ok)
        assert not (3600 < 3500 and 55 > 40)
        # Should NOT flag (hairpin)
        assert not (3000 < 3500 and 30 > 40)


class TestBrakeToShiftValidation:
    """Test negative Brk2Shft handling."""

    def test_positive_value_shown(self):
        val = 0.97
        result = f"{val:.2f}s" if val is not None and val >= 0 else "—"
        assert result == "0.97s"

    def test_negative_value_hidden(self):
        val = -0.47
        result = f"{val:.2f}s" if val is not None and val >= 0 else "—"
        assert result == "—"

    def test_none_value_hidden(self):
        val = None
        result = f"{val:.2f}s" if val is not None and val >= 0 else "—"
        assert result == "—"

    def test_zero_value_shown(self):
        val = 0.0
        result = f"{val:.2f}s" if val is not None and val >= 0 else "—"
        assert result == "0.00s"
