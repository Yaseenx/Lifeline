#!/usr/bin/env python3
"""Build a cross-checked Chennai traffic-signal dataset for LifeLine.

WHY: the green corridor needs the traffic signals along each route. Live Overpass
is great but not always reachable (blocked TLS, busy mirrors). This tool builds a
local, verified dataset (data/signals_chennai.geojson) that the server uses as an
offline fallback — so a route always has its signals.

CROSS-CHECK BY MULTIPLE SOURCES ("agents"): it pulls the same query from SEVERAL
independent Overpass mirrors (and/or files you export from Overpass Turbo), then:
  • unions the results by OSM node id (same id = same real signal),
  • confirms coordinates AGREE across the sources that report each signal,
  • collapses near-duplicate nodes at one junction (<= MERGE_M),
  • validates every point lies inside the Chennai bounding box,
  • records provenance (which sources confirmed each signal) + a report.

Nothing here touches the running server. It only writes files under data/.

USAGE
  # fetch + cross-check from the built-in mirrors (needs internet):
  python3 build_signals_dataset.py
  # cross-check exports you downloaded from Overpass Turbo instead of / as well as fetching:
  python3 build_signals_dataset.py --from-files chennai_a.geojson chennai_b.json
  # options:
  python3 build_signals_dataset.py --bbox 12.90 80.10 13.24 80.33 --out ../data

Requires only the Python standard library.
"""
import argparse
import csv
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

# Chennai (Greater Chennai) bounding box: south, west, north, east
BBOX = (12.83, 80.10, 13.28, 80.34)
MERGE_M = 25.0        # collapse signals clustered at one junction
COORD_TOL_M = 8.0     # sources must agree on a signal's position within this
TIMEOUT_S = 60.0

MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "http://overpass-api.de/api/interpreter",   # HTTP fallbacks for old TLS stacks
    "http://lz4.overpass-api.de/api/interpreter",
]

def _haversine(a, b):
    R = 6371000.0
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 2*R*math.asin(math.sqrt(h))

def _query(bbox):
    s, w, n, e = bbox
    return f'[out:json][timeout:50];node["highway"="traffic_signals"]({s},{w},{n},{e});out body;'

def _fetch(url, q):
    body = urllib.parse.urlencode({"data": q}).encode()
    req = urllib.request.Request(url, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "User-Agent": "LifeLine-dataset-builder/1.0 (emergency corridor)"})
    import ssl
    ctx = ssl._create_unverified_context() if hasattr(ssl, "_create_unverified_context") else None
    with urllib.request.urlopen(req, timeout=TIMEOUT_S, context=ctx) as r:
        return r.read().decode("utf-8", "replace")

def _parse_overpass_json(txt):
    out = []
    for el in json.loads(txt).get("elements", []):
        if el.get("type") == "node" and "lat" in el and "lon" in el:
            out.append((el.get("id"), float(el["lat"]), float(el["lon"]),
                        (el.get("tags") or {}).get("name", "")))
    return out

def _parse_geojson(txt):
    out = []
    for ft in json.loads(txt).get("features", []):
        g = ft.get("geometry") or {}
        if g.get("type") != "Point":
            continue
        c = g.get("coordinates") or []
        if len(c) >= 2:
            pr = ft.get("properties") or {}
            oid = pr.get("@id") or pr.get("id") or pr.get("osm_id")
            out.append((oid, float(c[1]), float(c[0]), pr.get("name", "")))
    return out

def load_source(name, txt):
    t = txt.lstrip()
    try:
        nodes = _parse_geojson(txt) if '"FeatureCollection"' in t[:200] else _parse_overpass_json(txt)
    except Exception as ex:
        print(f"  ! {name}: could not parse ({ex})"); return []
    print(f"  - {name}: {len(nodes)} signal nodes")
    return nodes

def in_bbox(lat, lng, bbox):
    s, w, n, e = bbox
    return s <= lat <= n and w <= lng <= e

def build(sources, bbox, out_dir):
    # sources: list of (source_name, [ (id,lat,lon,name), ... ])
    # 1) union by OSM id, cross-check coordinate agreement
    by_id = {}            # id -> {"lat","lng","name","srcs":set,"coords":[(lat,lng,src)]}
    anon = []             # nodes with no id (from bare geojson/csv exports)
    for sname, nodes in sources:
        for (oid, lat, lng, nm) in nodes:
            if oid is None:
                anon.append((lat, lng, nm, sname)); continue
            rec = by_id.setdefault(oid, {"lat":lat,"lng":lng,"name":nm,"srcs":set(),"coords":[]})
            rec["srcs"].add(sname); rec["coords"].append((lat,lng,sname))
            if nm and not rec["name"]: rec["name"] = nm

    disagreements = []
    for oid, rec in by_id.items():
        cs = rec["coords"]
        maxd = 0.0
        for i in range(len(cs)):
            for j in range(i+1, len(cs)):
                maxd = max(maxd, _haversine((cs[i][0],cs[i][1]), (cs[j][0],cs[j][1])))
        rec["spread_m"] = round(maxd, 1)
        if maxd > COORD_TOL_M:
            disagreements.append((oid, rec["spread_m"], sorted(rec["srcs"])))

    # 2) assemble candidate points (id-unioned + anonymous), validate bbox
    cand = []   # (lat,lng,name,srcs,confirmations)
    dropped_bbox = 0
    for oid, rec in by_id.items():
        if not in_bbox(rec["lat"], rec["lng"], bbox): dropped_bbox += 1; continue
        cand.append([rec["lat"], rec["lng"], rec["name"], sorted(rec["srcs"]), len(rec["srcs"])])
    for (lat,lng,nm,sname) in anon:
        if not in_bbox(lat,lng,bbox): dropped_bbox += 1; continue
        cand.append([lat,lng,nm,[sname],1])

    # 3) spatial dedupe within MERGE_M (collapse multi-node junctions / cross-source dups)
    cand.sort(key=lambda r:(r[0],r[1]))
    kept = []
    merged = 0
    for r in cand:
        dup = None
        for k in kept:
            if _haversine((r[0],r[1]),(k[0],k[1])) <= MERGE_M:
                dup = k; break
        if dup is None:
            kept.append(r)
        else:
            merged += 1
            for s in r[3]:
                if s not in dup[3]: dup[3].append(s)
            dup[4] = len(dup[3])
            if r[2] and not dup[2]: dup[2] = r[2]

    kept.sort(key=lambda r:(r[0],r[1]))
    nsrc = len(sources)
    confirmed = sum(1 for r in kept if r[4] >= 2)
    os.makedirs(out_dir, exist_ok=True)

    # GeoJSON
    feats = [{"type":"Feature","geometry":{"type":"Point","coordinates":[round(r[1],7),round(r[0],7)]},
              "properties":{"name":r[2] or "signal","sources":r[3],"confirmations":r[4]}} for r in kept]
    gj = {"type":"FeatureCollection",
          "metadata":{"area":"Chennai","source":"OpenStreetMap highway=traffic_signals, cross-checked across %d source(s)"%nsrc,
                      "crs":"WGS84 (lat/lng)","count":len(kept),"generated":time.strftime("%Y-%m-%d %H:%M:%S")},
          "features":feats}
    with open(os.path.join(out_dir,"signals_chennai.geojson"),"w",encoding="utf-8") as f:
        json.dump(gj,f,ensure_ascii=False,indent=0)

    # CSV
    with open(os.path.join(out_dir,"signals_chennai.csv"),"w",newline="",encoding="utf-8") as f:
        wtr = csv.writer(f); wtr.writerow(["lat","lng","name","sources","confirmations"])
        for r in kept: wtr.writerow([f"{r[0]:.7f}",f"{r[1]:.7f}",r[2] or "signal","|".join(r[3]),r[4]])

    # Report
    lines = []
    lines.append("LifeLine — Chennai traffic-signal dataset · validation report")
    lines.append(time.strftime("Generated: %Y-%m-%d %H:%M:%S"))
    lines.append(f"BBox (S,W,N,E): {bbox}")
    lines.append("")
    lines.append("Sources cross-checked:")
    for sname, nodes in sources: lines.append(f"  - {sname}: {len(nodes)} nodes")
    lines.append("")
    lines.append(f"Unique OSM signals (by id): {len(by_id)}")
    lines.append(f"Confirmed by >= 2 sources: {confirmed} / {len(kept)}  ({(100*confirmed/len(kept) if kept else 0):.0f}%)")
    lines.append(f"Near-duplicate nodes merged (<= {MERGE_M:.0f} m): {merged}")
    lines.append(f"Dropped (outside Chennai bbox): {dropped_bbox}")
    lines.append(f"Coordinate disagreements (> {COORD_TOL_M:.0f} m between sources): {len(disagreements)}")
    for oid, sp, ss in disagreements[:20]:
        lines.append(f"    id {oid}: sources {ss} disagree by {sp} m")
    lines.append("")
    lines.append(f"FINAL dataset: {len(kept)} signals  ->  {os.path.join(out_dir,'signals_chennai.geojson')}")
    report = "\n".join(lines)
    with open(os.path.join(out_dir,"validation_report.txt"),"w",encoding="utf-8") as f: f.write(report+"\n")
    print("\n"+report)
    return len(kept)

def main():
    ap = argparse.ArgumentParser(description="Build a cross-checked Chennai traffic-signal dataset.")
    ap.add_argument("--from-files", nargs="*", default=[], help="Overpass JSON / GeoJSON export files to cross-check")
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("S","W","N","E"), default=list(BBOX))
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","data"))
    ap.add_argument("--no-fetch", action="store_true", help="do not query the mirrors; use --from-files only")
    args = ap.parse_args()
    bbox = tuple(args.bbox)
    sources = []

    for path in args.from_files:
        try:
            with open(path,"r",encoding="utf-8") as f: txt = f.read()
            sources.append((os.path.basename(path), load_source(os.path.basename(path), txt)))
        except Exception as ex:
            print(f"  ! could not read {path}: {ex}")

    if not args.no_fetch:
        q = _query(bbox)
        print(f"Querying {len(MIRRORS)} Overpass mirror(s) for Chennai traffic_signals ...")
        for url in MIRRORS:
            try:
                txt = _fetch(url, q)
                if '"elements"' not in txt and '"FeatureCollection"' not in txt:
                    print(f"  ! {url}: unexpected response (busy?)"); continue
                sources.append((url.split("//")[1].split("/")[0], load_source(url, txt)))
            except Exception as ex:
                print(f"  ! {url}: {ex}")

    sources = [(n, nodes) for (n, nodes) in sources if nodes]
    if not sources:
        print("\nNo usable sources. Either run where the Overpass mirrors are reachable, "
              "or export the data from https://overpass-turbo.eu and pass it with --from-files.")
        sys.exit(2)
    if len(sources) == 1:
        print("\nNOTE: only one source available — building it, but cross-source confirmation is limited. "
              "Add more mirrors or an Overpass Turbo export for a stronger cross-check.")
    build(sources, bbox, os.path.abspath(args.out))

if __name__ == "__main__":
    main()
