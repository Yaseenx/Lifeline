import math
import re

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

with open('/Users/ggplautomation/Desktop/911/LifeLine-Ambulance/tools/corridor_player.py', 'r') as f:
    content = f.read()

# Extract the current DEMO_ROUTE
pattern = re.compile(r'DEMO_ROUTE = \[.*?\]\n', re.DOTALL)
match = pattern.search(content)
if not match:
    print("DEMO_ROUTE not found")
    exit(1)

route_str = match.group(0)
# Extract just the floats
lines = route_str.split('\n')
raw_points = []
for line in lines:
    if '(' in line and ')' in line:
        parts = line.strip(' ,()').split(',')
        if len(parts) == 2:
            raw_points.append((float(parts[0]), float(parts[1])))

print(f"Read {len(raw_points)} raw points")

# Interpolate
target_dist_m = (40 / 3.6) / 2.0  # ~5.55m
dense_points = [raw_points[0]]

for i in range(len(raw_points) - 1):
    p1 = raw_points[i]
    p2 = raw_points[i+1]
    dist = haversine(p1[0], p1[1], p2[0], p2[1])
    
    if dist <= target_dist_m:
        dense_points.append(p2)
        continue
        
    num_segments = int(math.ceil(dist / target_dist_m))
    for j in range(1, num_segments + 1):
        frac = j / num_segments
        ilat = p1[0] + (p2[0] - p1[0]) * frac
        ilng = p1[1] + (p2[1] - p1[1]) * frac
        dense_points.append((ilat, ilng))

print(f"Interpolated into {len(dense_points)} dense points")

path_str = ",\n".join(f"    ({pt[0]:.6f}, {pt[1]:.6f})" for pt in dense_points)
new_route = f"DEMO_ROUTE = [\n{path_str}\n]\n"
content = pattern.sub(new_route, content)

with open('/Users/ggplautomation/Desktop/911/LifeLine-Ambulance/tools/corridor_player.py', 'w') as f:
    f.write(content)

print("Updated corridor_player.py with DENSE route points!")
