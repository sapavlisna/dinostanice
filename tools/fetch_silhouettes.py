"""Fetch candidate silhouettes from PhyloPic.

PhyloPic hosts scientifically-vetted silhouettes of organisms under Creative
Commons terms. They are filled shapes, which is exactly what a colouring
template needs: trace the outline and you have a big clean area to fill in.

Downloads previews so a human can pick, and records licence and attribution
for every candidate. Nothing is used without knowing who made it.
"""

import argparse
import json
import os
import urllib.parse
import urllib.request

BASE = "https://api.phylopic.org"
HEADERS = {"Accept": "application/vnd.phylopic.v2+json",
           "User-Agent": "DinoStanice/1.0 (personal, non-commercial)"}

TAXA = ["brachiosaurus", "tyrannosaurus", "pteranodon", "plesiosaurus",
        "stegosaurus", "triceratops", "parasaurolophus", "ankylosaurus"]

FREE = {"https://creativecommons.org/publicdomain/zero/1.0/": "CC0",
        "https://creativecommons.org/publicdomain/mark/1.0/": "PD"}


def api(path, **params):
    if params:
        path += ("&" if "?" in path else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(BASE + path, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def current_build():
    try:
        api("/nodes", filter_name="life")
    except urllib.error.HTTPError as e:
        return json.load(e)["build"]
    return api("/nodes", filter_name="life")["build"]


def find_node(name, build):
    res = api("/nodes", build=build, filter_name=name, page=0)
    items = res.get("_links", {}).get("items", [])
    return items[0]["href"].split("/")[-1].split("?")[0] if items else None


def image_detail(href, build):
    uuid = href.split("/")[-1].split("?")[0]
    return api(f"/images/{uuid}", build=build)


def candidates(taxon, build, limit=8):
    node = find_node(taxon, build)
    if not node:
        return []
    res = api("/images", build=build, filter_clade=node, page=0)
    out = []
    for item in res.get("_links", {}).get("items", [])[:limit]:
        try:
            out.append(image_detail(item["href"], build))
        except Exception:
            continue
    return out


def describe(img):
    links = img.get("_links", {})
    lic = links.get("license", {}).get("href", "")
    contributor = links.get("contributor", {}).get("title", "?")
    rasters = links.get("rasterFiles", []) or []
    return {
        "uuid": img.get("uuid"),
        "licence": FREE.get(lic, lic),
        "free": lic in FREE,
        "contributor": contributor,
        "attribution": img.get("attribution") or contributor,
        "vector": (links.get("vectorFile") or {}).get("href"),
        "raster": rasters[0]["href"] if rasters else None,
        "sponsor": img.get("sponsor"),
    }


def download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": HEADERS["User-Agent"]})
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        f.write(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/silhouettes")
    ap.add_argument("--free-only", action="store_true",
                    help="keep only CC0 / public domain candidates")
    args = ap.parse_args()

    build = current_build()
    print(f"PhyloPic build {build}")
    os.makedirs(args.out, exist_ok=True)
    index = {}

    for taxon in TAXA:
        rows = []
        for img in candidates(taxon, build):
            d = describe(img)
            if args.free_only and not d["free"]:
                continue
            if not d["raster"]:
                continue
            d["file"] = f"{taxon}_{d['uuid'][:8]}.png"
            try:
                download(d["raster"], os.path.join(args.out, d["file"]))
            except Exception as e:
                print(f"  {taxon} {d['uuid'][:8]}: stažení selhalo ({e})")
                continue
            rows.append(d)
        index[taxon] = rows
        free = sum(1 for r in rows if r["free"])
        print(f"{taxon:16s} {len(rows):2d} kandidátů ({free} volných)")

    with open(os.path.join(args.out, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"build": build, "taxa": index}, f, ensure_ascii=False, indent=1)
    print(f"\nindex -> {args.out}/index.json")


if __name__ == "__main__":
    main()
