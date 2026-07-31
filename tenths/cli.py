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


def config_cli(args):
    """Show or change where Tenths looks for telemetry.

    `tenths config` answers the first two support questions on its own: which
    folder is being watched, and where the log is.
    """
    import tenths.config as cfg
    from tenths.applog import log_path

    if args and args[0] in ("-h", "--help"):
        print("Usage:\n"
              "  tenths config                              Show resolved paths\n"
              "  tenths config --telemetry-root <path>      Set the telemetry folder\n"
              "  tenths config --reset-telemetry-root       Go back to auto-detection")
        return

    if "--telemetry-root" in args:
        index = args.index("--telemetry-root")
        if index + 1 >= len(args):
            print("Error: --telemetry-root needs a path")
            return
        # Join the remainder so unquoted paths with spaces still work
        new_root = os.path.normpath(" ".join(args[index + 1:]).strip('"'))
        if not os.path.isdir(new_root):
            print(f"Error: not a folder: {new_root}")
            print("Point this at the folder iRacing writes .ibt files to.")
            return
        try:
            written = cfg.save_settings({'telemetry_root': new_root})
        except OSError as exc:
            print(f"Error: could not write settings: {exc}")
            return
        print(f"Telemetry folder set to: {new_root}")
        print(f"Saved to: {written}")
        print("Restart Tenths for this to take effect.")
        return

    if "--reset-telemetry-root" in args:
        try:
            settings = cfg.load_settings()
            settings.pop('telemetry_root', None)
            os.makedirs(os.path.dirname(cfg.SETTINGS_PATH), exist_ok=True)
            import json
            with open(cfg.SETTINGS_PATH, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2)
        except OSError as exc:
            print(f"Error: could not write settings: {exc}")
            return
        print("Telemetry folder reset to auto-detection.")
        print(f"Auto-detected: {cfg._find_iracing_telemetry()}")
        print("Restart Tenths for this to take effect.")
        return

    # Show current state
    env_override = os.environ.get('TENTHS_TELEMETRY_ROOT')
    configured = cfg.SETTINGS.get('telemetry_root')
    if env_override:
        source = "TENTHS_TELEMETRY_ROOT environment variable"
    elif configured:
        source = f"settings file ({cfg.SETTINGS_PATH})"
    else:
        source = "auto-detected from your Documents folder"

    print("Tenths configuration")
    print(f"  Version          : {cfg.VERSION}")
    print(f"  Documents folder : {cfg._documents_dir()}")
    print(f"  iRacing folder   : {cfg.iracing_dir()}"
          f"{'' if os.path.isdir(cfg.iracing_dir()) else '   (NOT FOUND)'}")
    print(f"  Telemetry folder : {cfg.TELEMETRY_ROOT}"
          f"{'' if os.path.isdir(cfg.TELEMETRY_ROOT) else '   (NOT FOUND)'}")
    print(f"    source         : {source}")
    print(f"  Archive folder   : {cfg.ARCHIVE_DIR}")
    print(f"  Log file         : {log_path()}")
    print(f"  Settings file    : {cfg.SETTINGS_PATH}"
          f"{'' if os.path.isfile(cfg.SETTINGS_PATH) else '   (not created yet)'}")

    if os.path.isdir(cfg.TELEMETRY_ROOT):
        ibt = [f for f in os.listdir(cfg.TELEMETRY_ROOT) if f.lower().endswith('.ibt')]
        print(f"  Unprocessed .ibt : {len(ibt)}")
    else:
        print("\n  The telemetry folder was not found. If iRacing stores telemetry")
        print("  somewhere else, set it with:")
        print('    tenths config --telemetry-root "D:\\path\\to\\telemetry"')

    for warning in cfg.CONFIG_WARNINGS:
        print(f"\n  WARNING: {warning}")


def main(argv=None):
    """Dispatch a subcommand.

    `argv` is the argument list without the program name. It exists so the frozen
    tray executable can forward its own arguments here. Subcommand handlers below
    consume `sys.argv`, so an explicit argv is normalized into it rather than
    threaded through every handler.
    """
    from tenths.config import configure_console, CONFIG_WARNINGS
    from tenths.applog import configure_logging, get_logger
    if argv is not None:
        sys.argv = [sys.argv[0]] + list(argv)
    configure_console()
    # Console output plus a durable log file, so a failure is always recoverable
    configure_logging()

    # Surface configuration problems now that logging exists (config cannot log)
    if CONFIG_WARNINGS:
        log = get_logger(__name__)
        for warning in CONFIG_WARNINGS:
            log.warning(warning)

    if len(sys.argv) < 2:
        print_help()
        return

    command = sys.argv[1]

    if command == "config":
        config_cli(sys.argv[2:])

    elif command == "analyze":
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
        from tenths.incidents import main as incident_main
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        incident_main()

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

    elif command == "tray":
        from tenths.service.tray import main as tray_main
        # Explicitly empty: tray.main() forwards any arguments back to this
        # function, so passing the remaining argv would recurse.
        tray_main([])

    elif command == "index":
        from tenths.index_generator import generate_master_index
        result = generate_master_index()
        if result:
            print(f"Index generated: {result}")
            import webbrowser
            webbrowser.open(f'file:///{result.replace(os.sep, "/")}')
        else:
            print("No sessions found.")

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
  config                          Show resolved paths (telemetry, log, settings)
  config --telemetry-root <path>  Point Tenths at a different telemetry folder
  watch                           Watch for new sessions and auto-process (Ctrl+C to stop)
  watch --open                    Watch and auto-open reports in browser
  tray                            Run as system tray app (no terminal window)
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
