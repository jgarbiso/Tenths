"""
Tests for schema versioning and migration system.
"""

import json
import os
import tempfile

import pytest

from tenths.summary import (
    CURRENT_SCHEMA_VERSION,
    SCHEMA_VERSIONS,
    migrate_summary,
    migrate_directory,
)


class TestMigrationSystem:
    """Test the schema migration infrastructure."""

    def test_current_version_no_migration(self):
        """Files already at current version should not be modified."""
        summary = {
            'schema_version': CURRENT_SCHEMA_VERSION,
            'car': {'name': 'Test Car'},
            'best_lap': {'time_seconds': 90.0},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, 'session_summary.json')
            with open(filepath, 'w') as f:
                json.dump(summary, f)

            migrated, from_v, to_v = migrate_summary(filepath)
            assert migrated is False
            assert from_v == CURRENT_SCHEMA_VERSION
            assert to_v == CURRENT_SCHEMA_VERSION

    def test_old_version_gets_stamped(self):
        """Files with older versions get stamped to current even without explicit migration."""
        summary = {
            'schema_version': '0.9.0',
            'car': {'name': 'Test Car'},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, 'session_summary.json')
            with open(filepath, 'w') as f:
                json.dump(summary, f)

            migrated, from_v, to_v = migrate_summary(filepath)
            assert migrated is True
            assert from_v == '0.9.0'
            assert to_v == CURRENT_SCHEMA_VERSION

            # Verify file was updated
            with open(filepath, 'r') as f:
                result = json.load(f)
            assert result['schema_version'] == CURRENT_SCHEMA_VERSION

    def test_missing_version_treated_as_old(self):
        """Files without schema_version get version '0.0.0' and are migrated."""
        summary = {'car': {'name': 'Test Car'}}  # no schema_version key
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, 'session_summary.json')
            with open(filepath, 'w') as f:
                json.dump(summary, f)

            migrated, from_v, to_v = migrate_summary(filepath)
            assert migrated is True
            assert from_v == '0.0.0'
            assert to_v == CURRENT_SCHEMA_VERSION

    def test_migrate_directory_finds_files(self):
        """migrate_directory should find nested session_summary.json files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested structure
            sub1 = os.path.join(tmpdir, 'car', 'track', '2026-01-01')
            sub2 = os.path.join(tmpdir, 'car', 'track', '2026-01-02')
            os.makedirs(sub1)
            os.makedirs(sub2)

            for d in [sub1, sub2]:
                with open(os.path.join(d, 'session_summary.json'), 'w') as f:
                    json.dump({'schema_version': '0.8.0', 'data': 'test'}, f)

            results = migrate_directory(tmpdir)
            assert len(results) == 2
            assert all(m for _, m, _, _ in results)  # both migrated

    def test_migrate_preserves_data(self):
        """Migration should preserve all existing data fields."""
        summary = {
            'schema_version': '0.5.0',
            'car': {'name': 'BMW M2 CS Racing', 'class': 'Touring'},
            'best_lap': {'time_seconds': 91.74, 'number': 4},
            'laps': [{'number': 4, 'time_seconds': 91.74}],
            'custom_field': 'should_survive',
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, 'session_summary.json')
            with open(filepath, 'w') as f:
                json.dump(summary, f)

            migrate_summary(filepath)

            with open(filepath, 'r') as f:
                result = json.load(f)

            assert result['schema_version'] == CURRENT_SCHEMA_VERSION
            assert result['car']['name'] == 'BMW M2 CS Racing'
            assert result['best_lap']['time_seconds'] == 91.74
            assert result['custom_field'] == 'should_survive'


class TestSchemaVersionList:
    """Validate the schema version registry."""

    def test_versions_ordered(self):
        """SCHEMA_VERSIONS must be in ascending order."""
        for i in range(len(SCHEMA_VERSIONS) - 1):
            assert SCHEMA_VERSIONS[i] < SCHEMA_VERSIONS[i + 1]

    def test_current_is_latest(self):
        """CURRENT_SCHEMA_VERSION must be the last entry in SCHEMA_VERSIONS."""
        assert SCHEMA_VERSIONS[-1] == CURRENT_SCHEMA_VERSION

    def test_versions_are_semver(self):
        """All versions must be valid semver format."""
        for v in SCHEMA_VERSIONS:
            parts = v.split('.')
            assert len(parts) == 3
            assert all(p.isdigit() for p in parts)
