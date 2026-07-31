"""
Tenths Session Notifier — Windows Toast Notifications
=======================================================
Sends Windows toast notifications when a session is processed.
Click action opens the session report in the default browser.

Usage:
    from tenths.service.notifier import SessionNotifier
    notifier = SessionNotifier()
    notifier.notify_complete(result)
"""

import os
import webbrowser

from winotify import Notification, audio


# App identity for Windows notification center
APP_ID = "Tenths"


class SessionNotifier:
    """Sends Windows toast notifications for processed sessions."""

    def notify_complete(self, best_time, laps, track_name, session_type,
                        report_path, race_result=None, is_pb=False):
        """Send a toast notification for a completed session.

        Args:
            best_time: formatted best lap time string (e.g., "1:30.965")
            laps: number of valid laps
            track_name: track display name
            session_type: "Practice", "Race", "Test", etc.
            report_path: absolute path to session_report.html
            race_result: optional dict with finish_pos, field_size, ir_delta
            is_pb: whether this is a new personal best
        """
        # Build title
        if race_result:
            pos = race_result.get('finish_pos', 0)
            field = race_result.get('field_size', 0)
            ir_delta = race_result.get('ir_delta', 0)
            title = f"P{pos}/{field} at {track_name}"
            if ir_delta != 0:
                sign = '+' if ir_delta > 0 else ''
                title += f" | iR {sign}{ir_delta}"
        else:
            title = f"{session_type} at {track_name}"

        # Build body
        body_parts = [f"Best: {best_time} ({laps} laps)"]
        if is_pb:
            body_parts.insert(0, "🏆 NEW PERSONAL BEST!")

        body = "\n".join(body_parts)

        # Create notification
        toast = Notification(
            app_id=APP_ID,
            title=title,
            msg=body,
            duration="short",
        )

        # Set audio
        toast.set_audio(audio.Default, loop=False)

        # Add click action — open report in browser
        report_url = f"file:///{report_path.replace(os.sep, '/')}"
        toast.add_actions(label="Open Report", launch=report_url)

        # Show the notification
        toast.show()

    def notify_info(self, title, message, action_label=None, action_target=None):
        """Send an informational toast (setup guidance, not a failure).

        Args:
            title: short heading
            message: body text
            action_label: optional button label
            action_target: URL or file path the button opens
        """
        toast = Notification(
            app_id=APP_ID,
            title=title,
            msg=message,
            duration="long",
        )
        if action_label and action_target:
            toast.add_actions(label=action_label, launch=action_target)
        toast.show()

    def notify_error(self, filename, error_msg):
        """Send an error notification when processing fails.

        Args:
            filename: the .ibt filename that failed
            error_msg: short error description
        """
        toast = Notification(
            app_id=APP_ID,
            title="Tenths — Processing Failed",
            msg=f"{filename}\n{error_msg[:100]}",
            duration="short",
        )
        toast.show()


def format_race_result(summary):
    """Extract race result info from a session summary for notification.

    Args:
        summary: dict from generate_session_summary()

    Returns:
        dict with finish_pos, field_size, ir_delta — or None if not a race.
    """
    race = summary.get('race_result')
    if not race:
        return None
    return {
        'finish_pos': race.get('finish_position', 0),
        'field_size': race.get('field_size', 0),
        'ir_delta': race.get('irating_delta', 0),
    }
