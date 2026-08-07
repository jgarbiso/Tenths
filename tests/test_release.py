"""
Tests for the release pipeline preflight.

`release.py` publishes a public GitHub release, so a preflight hole is expensive:
it is discovered by testers, not by us. These tests pin the sync check that used
to only look one way.
"""

import importlib.util
import os
import re

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELEASE_PATH = os.path.join(PROJECT_ROOT, "release.py")


def _load_release():
    """Import release.py by path — it lives at the repo root, not in the package."""
    spec = importlib.util.spec_from_file_location("release_script", RELEASE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def release():
    return _load_release()


class TestSyncCheck:
    """The release must refuse to publish anything origin/main does not have."""

    def test_in_sync_passes(self, release):
        assert release.sync_error(0, 0) is None

    def test_ahead_is_refused(self, release):
        """The case that was previously unchecked: releasing unpushed commits."""
        problem = release.sync_error(4, 0)
        assert problem is not None
        assert "ahead" in problem
        assert "git push origin main" in problem

    def test_behind_is_refused(self, release):
        problem = release.sync_error(0, 2)
        assert problem is not None
        assert "behind" in problem
        assert "git pull origin main" in problem

    def test_diverged_is_refused(self, release):
        assert release.sync_error(3, 5) is not None

    def test_counts_appear_in_the_message(self, release):
        """A bare refusal makes the operator guess how far off they are."""
        assert "7" in release.sync_error(7, 0)
        assert "9" in release.sync_error(0, 9)


class TestPreflightUsesBothDirections:
    """Guard the call sites, not just the pure function.

    `sync_error` being correct is useless if `main()` only feeds it one number.
    """

    def test_main_measures_both_directions(self):
        source = open(RELEASE_PATH, encoding="utf-8").read()
        assert "git rev-list HEAD..origin/main --count" in source, "behind count missing"
        assert "git rev-list origin/main..HEAD --count" in source, "ahead count missing"

    def test_main_routes_through_sync_error(self):
        source = open(RELEASE_PATH, encoding="utf-8").read()
        assert re.search(r"sync_error\(\s*ahead\s*,\s*behind\s*\)", source), (
            "preflight must call sync_error(ahead, behind)")

    def test_preflight_still_guards_the_other_conditions(self):
        """These were already in place; keep them from being dropped."""
        source = open(RELEASE_PATH, encoding="utf-8").read()
        assert "git status --porcelain" in source, "clean-tree check missing"
        assert "git branch --show-current" in source, "branch check missing"
        assert "gh auth status" in source, "gh auth check missing"


class TestTagSequencing:
    """Beta tags increment; a duplicate tag would fail mid-release."""

    def test_version_prefix_is_semver_beta(self, release):
        assert re.fullmatch(r"v\d+\.\d+\.\d+-beta", release.VERSION_PREFIX)

    def test_next_tag_follows_the_prefix(self, release):
        tag = release.get_next_tag()
        assert tag.startswith(release.VERSION_PREFIX + ".")
        assert re.fullmatch(r"v\d+\.\d+\.\d+-beta\.\d+", tag)


class TestChangelog:
    """A public release with no changelog entry is a release nobody can review.

    The pipeline generates tag notes from a one-line description, so CHANGELOG.md
    is the only durable record of what shipped.
    """

    CHANGELOG = os.path.join(PROJECT_ROOT, "CHANGELOG.md")

    def _text(self):
        return open(self.CHANGELOG, encoding="utf-8").read()

    def test_changelog_exists(self):
        assert os.path.exists(self.CHANGELOG)

    def test_has_an_unreleased_section(self):
        """Somewhere to record work before the next tag is cut."""
        assert re.search(r"^## \[Unreleased\]", self._text(), re.M)

    def test_every_released_tag_has_an_entry(self, release):
        """A tag with no changelog section is a release with no notes."""
        result = release.run(f'git tag --list "{release.VERSION_PREFIX}.*"',
                             capture=True)
        tags = [t.strip() for t in result.stdout.splitlines() if t.strip()]
        text = self._text()
        missing = [t for t in tags if f"## [{t}]" not in text]
        assert not missing, f"tags with no CHANGELOG entry: {missing}"

    def test_entries_are_newest_first(self):
        """Reverse-chronological, per Keep a Changelog."""
        versions = re.findall(r"^## \[v0\.9\.0-beta\.(\d+)\]", self._text(), re.M)
        numbers = [int(v) for v in versions]
        assert numbers == sorted(numbers, reverse=True), (
            f"CHANGELOG entries out of order: {numbers}")

    def test_documents_the_beta_versioning_scheme(self):
        """The internal version stays 0.9.0 through beta; readers need to know."""
        text = self._text()
        assert "0.9.0" in text
        assert "beta" in text.lower()
