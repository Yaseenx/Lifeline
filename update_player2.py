import json
import re

with open('/Users/ggplautomation/Desktop/911/LifeLine-Ambulance/server/new_route.json', 'r') as f:
    route_points = json.load(f)

path_str = ",\n".join(f"    ({pt['lat']}, {pt['lng']})" for pt in route_points)

with open('/Users/ggplautomation/Desktop/911/LifeLine-Ambulance/tools/corridor_player.py', 'r') as f:
    content = f.read()

pattern = re.compile(r'DEMO_ROUTE = \[.*?\]\n', re.DOTALL)
new_route = f"DEMO_ROUTE = [\n{path_str}\n]\n"
content = pattern.sub(new_route, content)

with open('/Users/ggplautomation/Desktop/911/LifeLine-Ambulance/tools/corridor_player.py', 'w') as f:
    f.write(content)

print("Updated corridor_player.py with new route points!")
