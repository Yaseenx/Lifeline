import asyncio
import live_signals
import json

async def main():
    # Waypoints matching Google Maps
    # Start: Flosil / Busy to Tally (approx 13.0850, 80.2560)
    # Turn left Jothi Venkatachalam (13.0782, 80.2539)
    # Turn right Gandhi Irwin (13.0780, 80.2583)
    # Commissioner (13.0735, 80.2588)
    # EVR Periyar (13.0715, 80.2590)
    # RGGGH (13.0814, 80.2776)
    
    wps = [
        (13.0850, 80.2560), # Start near Vepery
        (13.0782, 80.2539), # EVK Sampath -> Jothi
        (13.0780, 80.2583), # Jothi -> Gandhi Irwin
        (13.0735, 80.2588), # Commissioner
        (13.0715, 80.2590), # EVR Periyar
        (13.0814, 80.2776), # RGGGH
    ]
    
    full_path = []
    for i in range(len(wps)-1):
        print(f"Routing {wps[i]} to {wps[i+1]}")
        sig, p = await live_signals.route_and_signals(wps[i][0], wps[i][1], wps[i+1][0], wps[i+1][1])
        print(f"Segment {i} points: {len(p)}")
        if not full_path:
            full_path.extend(p)
        else:
            full_path.extend(p[1:])
    
    print(f"Total points: {len(full_path)}")
    print(f"First 5: {full_path[:5]}")
    print(f"Last 5: {full_path[-5:]}")
    
    with open("new_route.json", "w") as f:
        json.dump(full_path, f, indent=2)

asyncio.run(main())
