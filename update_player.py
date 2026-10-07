import re

with open('/Users/ggplautomation/Desktop/911/LifeLine-Ambulance/tools/corridor_player.py', 'r') as f:
    content = f.read()

# I will replace the waypoint sections and the junctions.
# First, read the path generated in scratch.py
import subprocess
out = subprocess.check_output(['python3', '/Users/ggplautomation/Desktop/911/LifeLine-Ambulance/server/scratch.py']).decode('utf-8')
path_str = out.split('PATH = [')[1].split(']')[0]

new_route = f"""# Single continuous demo route
DEMO_ROUTE = [{path_str}]

DEMO_JUNCTIONS = ["D1", "D2", "D3", "D4", "D5", "J1"]

# Junction coordinates
JUNCTIONS = {{
    "J1": ("MMC / RGGGH junction",          13.0814162, 80.2775787),
    "D1": ("Vepery High Rd x EVK Sampath",  13.0812,    80.2548),
    "D2": ("Jothi Venkatachalam Rd",        13.0780,    80.2583),
    "D3": ("Gandhi Irwin Rd",               13.0735,    80.2588),
    "D4": ("EVR Periyar Salai x Gandhi",    13.0715,    80.2590),
    "D5": ("EVR Periyar x Pallavan",        13.0760,    80.2660),
}}
"""

# Replace the block from # ---------- route waypoints... down to JUNCTIONS = {...}
pattern = re.compile(r'# ---------- route waypoints.*?# ---------- helpers ----------', re.DOTALL)
content = pattern.sub(new_route + '\n\n# ---------- helpers ----------', content)

# Now update the main function to just run the single demo route
main_pattern = re.compile(r'    try:\n        if 1 in legs_to_play:.*?except KeyboardInterrupt:', re.DOTALL)

new_main = """    try:
        await play_leg(sio, DEMO_ROUTE, 1, DEMO_JUNCTIONS)

        # End trip
        await sio.emit("vehicle:sos", _signed({
            "device_id": DEVICE_ID,
            "active": False,
        }))
        print(f"\\n{'━' * 40}")
        print(f"  ✓ CORRIDOR RUN COMPLETE")
        print(f"  Total pings sent: {sum(_ping_counts.values())}")
        print(f"{'━' * 40}\\n")

    except KeyboardInterrupt:"""

content = main_pattern.sub(new_main, content)

with open('/Users/ggplautomation/Desktop/911/LifeLine-Ambulance/tools/corridor_player.py', 'w') as f:
    f.write(content)

print("Updated corridor_player.py")
