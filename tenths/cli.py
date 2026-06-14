"""
Tenths CLI — Command-line interface for telemetry processing.

Usage:
    tenths analyze "path/to/file.ibt"       # Full coaching report
    tenths process                           # Process all pending .ibt files
    tenths process --dry-run                 # Preview without writing
    tenths incident "path/to/file.ibt" 2,3   # Incident forensics on laps 2,3
    tenths results "path/to/result.json"     # Parse race results
"""

import sys
import os


def main():
    if len(sys.argv) < 2:
        print_help()
        return

    command = sys.argv[1]

    if command == "analyze":
        from tenths.analyzer import main as analyze_main
        # Pass remaining args
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        analyze_main()

    elif command == "process":
        from tenths.process import main as process_main
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        process_main()

    elif command == "incident":
        # incident_check expects: filepath [laps]
        if len(sys.argv) < 3:
            print("Usage: tenths incident <file.ibt> [lap1,lap2,...]")
            return
        # Re-route to incidents module
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        exec(open(os.path.join(os.path.dirname(__file__), "incidents.py")).read())

    elif command == "results":
        from tenths.results import main as results_main
        if len(sys.argv) > 2:
            sys.argv = [sys.argv[0]] + sys.argv[2:]
        results_main() if hasattr(sys.modules.get('tenths.results', None), 'main') else None

    elif command == "report":
        from tenths.report import generate_report_cli
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        generate_report_cli()

    elif command == "watch":
        from tenths.service.watcher import TelemetryWatcher
        # --open flag to auto-open browser (default: notification only)
        auto_open = '--open' in sys.argv
        watcher = TelemetryWatcher(auto_open=auto_open)
        watcher.start()

    elif command == "summary":
        from tenths.summary import generate_summary_cli
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        generate_summary_cli()

    elif command == "migrate":
        from tenths.summary import migrate_cli
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        migrate_cli()

    elif command in ("--help", "-h", "help"):
        print_help()

    elif command == "--version":
        from tenths import __version__
        print(f"tenths {__version__}")

    else:
        print(f"Unknown command: {command}")
        print_help()


def print_help():
    print("""
Tenths — Find your tenths.
iRacing telemetry analysis and coaching tool.

Commands:
  watch                           Watch for new sessions and auto-process (Ctrl+C to stop)
  watch --open                    Watch and auto-open reports in browser
  analyze <file.ibt>              Full coaching report (prints to stdout)
  process                         Process all pending .ibt files → session notes
  process --dry-run               Preview without writing files
  process <file.ibt>              Process a specific file
  report <file.ibt>               Generate HTML visual report for a session
  summary <file.ibt>              Generate session_summary.json for a session
  migrate [path]                  Upgrade all session_summary.json to current schema
  incident <file.ibt> [laps]      Incident forensics (e.g., 2,3,4)
  results <file.json|csv>         Parse iRacing race results

Options:
  --help, -h                      Show this help
  --version                       Show version
""")


if __name__ == "__main__":
    main()
