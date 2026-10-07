import asyncio
import live_signals

async def main():
    # Waypoints
    wps = [
        (13.0838, 80.2543), # Start (Flosil)
        (13.0782, 80.2539), # Turn onto Jothi Venkatachalam
        (13.0735, 80.2588), # Commissioner office
        (13.0715, 80.2590), # Onto EVR Periyar
        (13.0814, 80.2776), # RGGGH
    ]
    path = []
    for i in range(len(wps)-1):
        sig, p = await live_signals.route_and_signals(wps[i][0], wps[i][1], wps[i+1][0], wps[i+1][1])
        if not path:
            path.extend(p)
        else:
            path.extend(p[1:])
    
    print(f"Total path points: {len(path)}")
    print("PATH = [")
    for pt in path:
        print(f"    ({pt['lat']}, {pt['lng']}),")
    print("]")

asyncio.run(main())
