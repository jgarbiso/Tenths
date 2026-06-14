"""
Tests for Windows toast notification system.
"""

import pytest
from unittest.mock import patch, MagicMock

from tenths.service.notifier import SessionNotifier, format_race_result


class TestSessionNotifier:
    """Test notification message formatting and logic."""

    def test_practice_notification_title(self):
        """Practice sessions show session type and track name."""
        notifier = SessionNotifier()
        with patch('tenths.service.notifier.Notification') as MockNotif:
            mock_instance = MagicMock()
            MockNotif.return_value = mock_instance

            notifier.notify_complete(
                best_time="1:30.965",
                laps=7,
                track_name="Winton Motor Raceway",
                session_type="Practice",
                report_path="C:/fake/path/session_report.html",
            )

            MockNotif.assert_called_once()
            call_kwargs = MockNotif.call_args[1]
            assert "Practice at Winton Motor Raceway" in call_kwargs['title']
            assert "1:30.965" in call_kwargs['msg']
            assert "7 laps" in call_kwargs['msg']

    def test_race_notification_title(self):
        """Race sessions show position, field size, and iRating."""
        notifier = SessionNotifier()
        with patch('tenths.service.notifier.Notification') as MockNotif:
            mock_instance = MagicMock()
            MockNotif.return_value = mock_instance

            notifier.notify_complete(
                best_time="1:31.740",
                laps=8,
                track_name="Winton",
                session_type="Race",
                report_path="C:/fake/path/session_report.html",
                race_result={'finish_pos': 3, 'field_size': 11, 'ir_delta': 61},
            )

            call_kwargs = MockNotif.call_args[1]
            assert "P3/11" in call_kwargs['title']
            assert "Winton" in call_kwargs['title']
            assert "+61" in call_kwargs['title']

    def test_race_negative_ir_delta(self):
        """Negative iRating shows without plus sign."""
        notifier = SessionNotifier()
        with patch('tenths.service.notifier.Notification') as MockNotif:
            mock_instance = MagicMock()
            MockNotif.return_value = mock_instance

            notifier.notify_complete(
                best_time="1:35.0",
                laps=5,
                track_name="Test Track",
                session_type="Race",
                report_path="C:/fake/path.html",
                race_result={'finish_pos': 8, 'field_size': 12, 'ir_delta': -45},
            )

            call_kwargs = MockNotif.call_args[1]
            assert "-45" in call_kwargs['title']
            assert "+" not in call_kwargs['title'].split("iR")[1]

    def test_pb_notification(self):
        """Personal best shows trophy emoji in body."""
        notifier = SessionNotifier()
        with patch('tenths.service.notifier.Notification') as MockNotif:
            mock_instance = MagicMock()
            MockNotif.return_value = mock_instance

            notifier.notify_complete(
                best_time="1:29.086",
                laps=5,
                track_name="Barber",
                session_type="Test",
                report_path="C:/fake/path.html",
                is_pb=True,
            )

            call_kwargs = MockNotif.call_args[1]
            assert "🏆" in call_kwargs['msg'] or "PERSONAL BEST" in call_kwargs['msg']

    def test_error_notification(self):
        """Error notification shows filename and message."""
        notifier = SessionNotifier()
        with patch('tenths.service.notifier.Notification') as MockNotif:
            mock_instance = MagicMock()
            MockNotif.return_value = mock_instance

            notifier.notify_error("test_file.ibt", "No valid laps found")

            call_kwargs = MockNotif.call_args[1]
            assert "Failed" in call_kwargs['title']
            assert "test_file.ibt" in call_kwargs['msg']

    def test_report_path_action(self):
        """Notification should have an action to open the report."""
        notifier = SessionNotifier()
        with patch('tenths.service.notifier.Notification') as MockNotif:
            mock_instance = MagicMock()
            MockNotif.return_value = mock_instance

            notifier.notify_complete(
                best_time="1:30.0",
                laps=3,
                track_name="Test",
                session_type="Practice",
                report_path=r"C:\Users\test\telemetry\session_report.html",
            )

            mock_instance.add_actions.assert_called_once()
            call_kwargs = mock_instance.add_actions.call_args[1]
            assert "file:///" in call_kwargs['launch']
            assert "session_report.html" in call_kwargs['launch']


class TestFormatRaceResult:
    """Test the race result formatter helper."""

    def test_with_race_result(self):
        summary = {
            'race_result': {
                'finish_position': 3,
                'field_size': 11,
                'irating_delta': 61,
            }
        }
        result = format_race_result(summary)
        assert result == {'finish_pos': 3, 'field_size': 11, 'ir_delta': 61}

    def test_no_race_result(self):
        summary = {'race_result': None}
        result = format_race_result(summary)
        assert result is None

    def test_missing_key(self):
        summary = {}
        result = format_race_result(summary)
        assert result is None
