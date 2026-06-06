"""
Tenths — iRacing Data Cache Setup
====================================
Pulls car and track reference data from the iRacing Data API
and saves it locally for offline use.

Usage:
    python -m tenths.setup_iracing_cache

You'll be prompted for your iRacing email and password.
Credentials are only used for this one-time pull and are NOT stored.

Requirements:
    python -m pip install iracingdataapi
"""

import json
import os
import sys
import getpass

# Output location
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")


def main():
    print("=" * 60)
    print("Tenths — iRacing Data Cache Setup")
    print("=" * 60)
    print()
    print("This will pull car and track data from the iRacing API.")
    print("Your credentials are used for this session only and are NOT stored.")
    print()

    # Check if iracingdataapi is installed
    try:
        from iracingdataapi.client import irDataClient
    except ImportError:
        print("ERROR: iracingdataapi not installed.")
        print("Run: python -m pip install iracingdataapi")
        sys.exit(1)

    # Get credentials
    email = input("iRacing email: ").strip()
    password = getpass.getpass("iRacing password: ")

    if not email or not password:
        print("ERROR: Email and password required.")
        sys.exit(1)

    print("\nConnecting to iRacing...")
    try:
        idc = irDataClient(username=email, password=password)
    except Exception as e:
        print(f"ERROR: Authentication failed: {e}")
        sys.exit(1)

    print("Authenticated successfully.\n")

    # Pull car data
    print("Fetching car data...")
    try:
        cars_raw = idc.get_cars()
        print(f"  Received {len(cars_raw)} cars")
    except Exception as e:
        print(f"  ERROR fetching cars: {e}")
        cars_raw = []

    # Pull track data
    print("Fetching track data...")
    try:
        tracks_raw = idc.get_tracks()
        print(f"  Received {len(tracks_raw)} tracks")
    except Exception as e:
        print(f"  ERROR fetching tracks: {e}")
        tracks_raw = []

    # Preview first 3 of each
    if cars_raw:
        print(f"\n  === Sample Cars (first 3) ===")
        for car in cars_raw[:3]:
            print(f"    ID:{car.get('car_id')}  Name:{car.get('car_name')}  "
                  f"Path:{car.get('car_dirpath')}  Class:{car.get('car_types', [])}")

    if tracks_raw:
        print(f"\n  === Sample Tracks (first 3) ===")
        for track in tracks_raw[:3]:
            print(f"    ID:{track.get('track_id')}  Name:{track.get('track_name')}  "
                  f"Config:{track.get('config_name')}  Turns:{track.get('corners_per_lap')}")

    # Save to cache
    os.makedirs(CACHE_DIR, exist_ok=True)

    # Cars: save a simplified version (id, name, path, class)
    cars_cache = []
    for car in cars_raw:
        cars_cache.append({
            'car_id': car.get('car_id'),
            'car_name': car.get('car_name', ''),
            'car_name_abbreviated': car.get('car_name_abbreviated', ''),
            'car_dirpath': car.get('car_dirpath', ''),  # This matches .ibt filename prefix
            'car_types': [ct.get('car_type') for ct in car.get('car_types', [])],
        })

    cars_path = os.path.join(CACHE_DIR, "cars.json")
    with open(cars_path, 'w', encoding='utf-8') as f:
        json.dump(cars_cache, f, indent=2)
    print(f"\n  Saved: {cars_path} ({len(cars_cache)} cars)")

    # Tracks: save a simplified version
    tracks_cache = []
    for track in tracks_raw:
        tracks_cache.append({
            'track_id': track.get('track_id'),
            'track_name': track.get('track_name', ''),
            'config_name': track.get('config_name', ''),
            'track_dirpath': track.get('track_dirpath', ''),
            'corners_per_lap': track.get('corners_per_lap', 0),
            'track_length_km': track.get('track_config_length', 0),
            'pit_speed_kph': track.get('pit_speed_limit', 0),
            'category': track.get('category', ''),
            'location': track.get('location', ''),
        })

    tracks_path = os.path.join(CACHE_DIR, "tracks.json")
    with open(tracks_path, 'w', encoding='utf-8') as f:
        json.dump(tracks_cache, f, indent=2)
    print(f"  Saved: {tracks_path} ({len(tracks_cache)} tracks)")

    print(f"\n{'='*60}")
    print("DONE — Cache files saved to: " + CACHE_DIR)
    print("Tenths will use these for car/track lookups.")
    print("Re-run this script after a new iRacing season to get new content.")


if __name__ == "__main__":
    main()
