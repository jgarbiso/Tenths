# Tenths

*Find your tenths.*

A telemetry analysis and coaching tool for iRacing. Parses `.ibt` files, generates session notes with braking diagnostics, GPS track mapping, corner variance analysis, and driver progression tracking.

## Features

- **Physics-aware braking analysis** — GT4 vs Touring car detection with class-specific diagnostics
- **5 Stages of Braking metrics** — T2Peak, Coast Time, Turn-In Brake %, Apex Brake %
- **GPS track mapping** — real coordinates for every braking zone
- **Corner variance & time loss** — identifies priority corners automatically
- **Track map integration** — maps telemetry percentages to actual turn names
- **Session notes generation** — complete markdown coaching reports, zero AI tokens
- **Incident forensics** — spin detection, contact evidence, GPS location
- **Race result parsing** — iRacing CSV/JSON event results

## Quick Start

```cmd
cd c:\Users\justi\Documents\iRacing\telemetry
python path\to\tenths\analyze.py "file.ibt"
python path\to\tenths\process.py
```

## Requirements

- Python 3.10+
- pyirsdk (`python -m pip install pyirsdk`)
- pandas (`python -m pip install pandas`)
- numpy (installed with pandas)

## Project Status

Active development. Currently used for personal iRacing coaching (BMW M4 EVO GT4, GT4 Challenge by Falken Tyre series).

## License

MIT
