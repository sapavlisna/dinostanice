"""Regresní kontrola chůze: prokluz chodidel a tempo per druh proti cílům.

    python tools/gait_report.py --url http://127.0.0.1:8100/

Osadí běžící scénu šesti chodci, několik desítek sekund loguje polohu tvorů
a světové X jejich zadních chodidel a spočítá:

  - zpětný prokluz chodidel (fail při >3 % ujeté dráhy),
  - těl/s, px/s, dobu přejezdu obrazovky a délku cyklu,
  - srovnání těl/s proti cílové tabulce (STRIDE_RATE ve web/scene.js),
    s tolerancí ±10 % na okrajích intervalu.

Zastávky a otočky měření nekazí: počítá se jen přes snímky, kdy tvor
skutečně jde (timeScale ~ plné tempo). Exit code 0 = vše v mezích.
"""

import argparse
import sys

from playwright.sync_api import sync_playwright

# Cílové intervaly těl/s — stejná čísla jako STRIDE_RATE ve web/scene.js.
TARGETS = {
    "trex3d": (0.11, 0.18),
    "apatosaurus3d": (0.05, 0.09),
    "triceratops3d": (0.17, 0.28),
    "stegosaurus3d": (0.16, 0.26),
    "velociraptor3d": (0.30, 0.40),
    "parasaurolophus3d": (0.14, 0.25),
}
SLIP_MAX = 3.0      # % ujeté dráhy
TOL = 0.10          # tolerance na okrajích cílového intervalu
W = 1600

SETUP = """
window.__probe = () => window.DinoScene.actors
  .filter(a => a.m3 && a.motion === 'walk').map(a => {
    const feet = [];
    a.m3.root.traverse(o => {
      if (/foot/i.test(o.name) && !/_end$/.test(o.name)) feet.push(o);
    });
    return { key: a.key, dir: a.dir, x: a.xFrac,
             rate: a.rate, ts: a.m3.action.timeScale,
             bodyPx: a.m3.length * a.m3.root.scale.x,
             feet: feet.map(f => ({ n: f.name, x: f.matrixWorld.elements[12] })) };
  });
window.__run = 0;
window.__start = () => { window.__log = []; const gen = ++window.__run;
  (function tick(){ requestAnimationFrame(() => { if (gen !== window.__run) return;
     window.__log.push({ t: performance.now()/1000, out: window.__probe() }); tick(); }); })(); };
0;
"""


def measure(url, seconds):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--use-gl=angle", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": W, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url, wait_until="networkidle")
        page.wait_for_function("window.__ready === true", timeout=30000)
        page.evaluate("""async (keys) => {
            window.DinoScene.actors.length = 0;
            for (const key of keys) await window.DinoScene.add(
              {kind:'model', id:'m-'+key, creature:key, texture:`/models3d/${key}_texture.png`},
              {silent:true});
        }""", list(TARGETS))
        page.evaluate(SETUP)
        page.wait_for_timeout(2000)          # než doběhne "pop" při narození
        page.evaluate("window.__start()")
        page.wait_for_timeout(int(seconds * 1000))
        log = page.evaluate("window.__log")
        where = page.evaluate("window.DinoScene.where()")
        browser.close()
    return log, where, errors


def analyze(log, where):
    rows = []
    for i, a0 in enumerate(log[0]["out"]):
        design = next((w for w in where if w.get("key") == a0["key"]), {})
        bodies = px = t_act = 0.0
        slip = {}                            # noha -> [wrong, net]
        for k in range(1, len(log)):
            p, q = log[k - 1]["out"][i], log[k]["out"][i]
            # jen snímky, kdy tvor opravdu jde: plné tempo, žádná otočka,
            # žádný přeskok přes okraj obrazovky
            if q["ts"] < 0.9 * q["rate"] or p["ts"] < 0.9 * p["rate"]:
                continue
            if p["dir"] != q["dir"]:
                continue
            dx = abs(q["x"] - p["x"])
            if dx > 0.5:
                continue
            dt = log[k]["t"] - log[k - 1]["t"]
            body_px = (p["bodyPx"] + q["bodyPx"]) / 2
            bodies += dx * W / body_px
            px += dx * W
            t_act += dt
            for f, foot in enumerate(q["feet"]):
                if not foot["n"].lower().startswith("back"):
                    continue
                d = (foot["x"] - p["feet"][f]["x"]) * q["dir"]
                if abs(d) > 0.2 * body_px:
                    continue                 # skok při obcházení scény
                s = slip.setdefault(foot["n"], [0.0, 0.0])
                s[1] += d
                if d < 0:
                    s[0] -= d
        bodies_s = bodies / t_act if t_act else 0.0
        px_s = px / t_act if t_act else 0.0
        rows.append({
            "key": a0["key"], "t_act": t_act,
            "bodies_s": bodies_s, "px_s": px_s,
            "cross": W / px_s if px_s else 0.0,
            "cycle": design.get("cycle") or 0.0,
            "design": design.get("bodiesPerS") or 0.0,
            "slip": max((100 * w / n if n else 0.0) for w, n in slip.values())
                    if slip else 0.0,
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8100/")
    ap.add_argument("--seconds", type=float, default=25,
                    help="délka měření; kratší okno zkreslí zastávky")
    args = ap.parse_args()

    log, where, errors = measure(args.url, args.seconds)
    rows = analyze(log, where)

    ok = True
    print(f"{'druh':18s} {'prokluz':>8s} {'těl/s':>7s} {'cíl':>11s} "
          f"{'px/s':>6s} {'přejezd':>8s} {'cyklus':>7s} {'chůze':>6s}  verdikt")
    for r in rows:
        lo, hi = TARGETS[r["key"]]
        bad = []
        if r["t_act"] < 5:
            bad.append("málo chůze v okně, prodluž --seconds")
        if r["slip"] > SLIP_MAX:
            bad.append(f"prokluz >{SLIP_MAX:.0f} %")
        if not lo * (1 - TOL) <= r["bodies_s"] <= hi * (1 + TOL):
            bad.append(f"tempo mimo {lo}-{hi}")
        ok &= not bad
        print(f"{r['key']:18s} {r['slip']:6.1f} % {r['bodies_s']:7.3f} "
              f"{lo:5.2f}-{hi:4.2f} {r['px_s']:6.1f} {r['cross']:6.0f} s "
              f"{r['cycle']:5.2f} s {r['t_act']:4.0f} s  "
              + ("OK" if not bad else "FAIL: " + "; ".join(bad)))
    if errors:
        ok = False
        print("CHYBY V PROHLÍŽEČI:", *errors, sep="\n  ")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
