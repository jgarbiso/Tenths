"""Quick script to extract race results from iRacing JSON."""
import json
import sys

filepath = sys.argv[1] if len(sys.argv) > 1 else r'c:\Users\justi\Downloads\eventresult-86172865.json'
my_id = 1434150

data = json.load(open(filepath, encoding='utf-8'))
race_sessions = [s for s in data['data']['session_results'] if s['simsession_name'] == 'RACE']
if not race_sessions:
    print("No RACE session found")
    sys.exit(1)

race = race_sessions[0]
results = sorted(race['results'], key=lambda x: x['finish_position'])

# Find me
me = [r for r in results if r['cust_id'] == my_id]
if me:
    me = me[0]
    print(f"=== YOUR RESULT ===")
    print(f"  Finish: P{me['finish_position']+1}/{len(results)}")
    print(f"  Start: P{me['starting_position']+1}")
    print(f"  Laps: {me['laps_complete']}")
    print(f"  Incidents: {me['incidents']}")
    best = me['best_lap_time']
    avg = me['average_lap']
    print(f"  Best lap: {best/10000:.3f}s" if best > 0 else "  Best lap: N/A")
    print(f"  Avg lap: {avg/10000:.3f}s" if avg > 0 else "  Avg lap: N/A")
    print(f"  iRating: {me['oldi_rating']} -> {me['newi_rating']} ({me['newi_rating']-me['oldi_rating']:+d})")
    print(f"  License: {me['old_license_level']}/{me['old_sub_level']} -> {me['new_license_level']}/{me['new_sub_level']}")
    print(f"  Reason out: {me['reason_out']}")

print(f"\n=== RACE SUMMARY ===")
print(f"  SOF: {data['data']['event_strength_of_field']}")
print(f"  Laps: {data['data']['event_laps_complete']}")
print(f"  Entries: {len(results)}")

print(f"\n=== FULL RESULTS ===")
print(f"  {'Pos':>3} {'Name':<25} {'Car':<22} {'Avg':>8} {'Best':>8} {'Inc':>4} {'iR':>5}")
for r in results:
    avg_str = f"{r['average_lap']/10000:.3f}" if r['average_lap'] > 0 else "N/A"
    best_str = f"{r['best_lap_time']/10000:.3f}" if r['best_lap_time'] > 0 else "N/A"
    marker = " <-- YOU" if r['cust_id'] == my_id else ""
    print(f"  P{r['finish_position']+1:>2} {r['display_name'][:24]:<25} {r['car_name'][:21]:<22} {avg_str:>8} {best_str:>8} {r['incidents']:>4} {r['newi_rating']:>5}{marker}")
