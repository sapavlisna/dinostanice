"""Postaví tři postavy mikulášské scény: Mikuláše, anděla a čerta.

    python tools/make_mikulas.py                 # modely do scenes/mikulas/modely/
    python tools/make_mikulas.py cert            # jen jednoho

Postavy jsou nízkopolygonové, s kostrou Hips/Spine/Chest/Neck/Head, pažemi
a nohami (chodidla `Foot*`/`Toe*`, aby scéna změřila krok) a klipy Walk, Run,
Idle, LookAround, Wave a Jump. Stavebnice (tvary, váhy, zápis GLB) je
v tools/humanoid.py. Pak `python tools/scena.py import mikulas --bez-blenderu`.

Proporce jsou záměrně buclaté (velká hlava, krátké nohy): z bokorysu musí jít
vybarvit, a oblast užší než ~5 mm se na listu sloučí se sousedem. Každý díl,
který má jít vybarvit zvlášť (čepice, vous, plášť, boty…), je vlastní materiál,
protože z hranic materiálů vznikají vnitřní linky předlohy.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from humanoid import (  # noqa: E402
    ID, Builder, Pose, Skeleton, blob, chain, combine, leg_foot_drop, lathe, make_clip,
    qmul3, qx, qy, qz, rad, rigid, rot_x, smooth, spindle, sweep, torus, write_rigged)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "scenes/mikulas/modely"

R, L = -1, 1                 # pravá strana je -X (ta se kreslí do bokorysu)
SIDE = {"R": R, "L": L}


# ------------------------------------------------------------------ kostra

def skeleton(p):
    """Společná kostra; `p` nese polohy kloubů. Klidová póza = žádné natočení."""
    sk = Skeleton()
    sk.add("Hips", None, (0, p["hips_y"], 0))
    sk.add("Spine", "Hips", (0, p["spine_y"], p.get("spine_z", 0)))
    sk.add("Chest", "Spine", (0, p["chest_y"], p.get("chest_z", 0)))
    sk.add("Neck", "Chest", (0, p["neck_y"], p.get("neck_z", 0)))
    sk.add("Head", "Neck", (0, p["head_y"], p.get("head_z", 0)))
    for s, sg in SIDE.items():
        sh = (sg * p["shoulder_x"], p["shoulder_y"], p.get("shoulder_z", 0))
        sk.add(f"UpperArm{s}", "Chest", sh)
        sk.add(f"LowerArm{s}", f"UpperArm{s}", p[f"elbow{s}"])
        sk.add(f"Hand{s}", f"LowerArm{s}", p[f"wrist{s}"])
        hx = sg * p["hip_x"]
        sk.add(f"UpperLeg{s}", "Hips", (hx, p["hips_y"] - 0.02, 0))
        sk.add(f"LowerLeg{s}", f"UpperLeg{s}", (hx, p["knee_y"], 0))
        sk.add(f"Foot{s}", f"LowerLeg{s}", (hx, p["ankle_y"], 0))
        sk.add(f"Toe{s}", f"Foot{s}", (hx, p["ankle_y"] - 0.04, p["toe_z"]))
    return sk


def limb(sk, s, kind):
    names = {"arm": [f"UpperArm{s}", f"LowerArm{s}", f"Hand{s}"],
             "leg": [f"UpperLeg{s}", f"LowerLeg{s}", f"Foot{s}"]}[kind]
    return names, [sk.pos(n) for n in names]


def torso_skin(sk):
    return chain(sk, ["Hips", "Spine", "Chest", "Neck"], 0.07)


def skirt_skin(sk, hem, kmax=0.6):
    """Sukně se kývá s nohama: boční poloviny táhne stehno na své straně."""
    torso = torso_skin(sk)
    hip_y = sk.pos("Hips")[1]
    thigh_l, thigh_r = rigid(sk, "UpperLegL"), rigid(sk, "UpperLegR")

    def k(v):
        return np.clip((hip_y - v[:, 1]) / (hip_y - hem), 0, 1) ** 1.2 * kmax

    def side(v):
        return smooth(v[:, 0], -0.08, 0.08)

    return combine((torso, lambda v: 1 - k(v)),
                   (thigh_l, lambda v: k(v) * side(v)),
                   (thigh_r, lambda v: k(v) * (1 - side(v))))


def profile_at(rings, y):
    """Poloměry a posun středu pláště ve výšce y z tabulky prstenců."""
    ys = [r[1] for r in rings]
    return tuple(np.interp(y, ys, [r[i] for r in rings]) for i in (0, 2, 3, 4))


def arm_tube(b, sk, s, radii, mat, end=0.0):
    names, pts = limb(sk, s, "arm")
    path = [pts[0], pts[1], pts[2] + (pts[2] - pts[1]) * end]
    b.add(sweep(path, radii, nu=10), mat, chain(sk, names, 0.05))


def leg_tube(b, sk, s, radii, mat):
    names, pts = limb(sk, s, "leg")
    b.add(sweep(pts, radii, nu=10), mat, chain(sk, names, 0.05))


def hand(b, sk, s, mat, r=0.06, along=0.4, extra=(0, 0, 0)):
    names, pts = limb(sk, s, "arm")
    d = pts[2] - pts[1]
    c = pts[2] + d / np.linalg.norm(d) * r * along + np.asarray(extra)
    b.add(blob(c, (r, r * 1.05, r)), mat, rigid(sk, f"Hand{s}"))


# ------------------------------------------------------------------ klipy

def gait(sk, G, ph):
    """Chůze a běh: nohy, ruce, trup. ph = fáze cyklu v radiánech (jeden cyklus =
    dva kroky); stojná noha je vždy na zemi, kyčle klesají podle skutečné
    délky nohou, takže chodidla neklouzají nahoru a dolů."""
    P = Pose()
    l1 = float(np.linalg.norm(sk.pos("UpperLegR") - sk.pos("LowerLegR")))
    l2 = float(np.linalg.norm(sk.pos("LowerLegR") - sk.pos("FootR")))
    raises = []
    for s, off in (("R", 0.0), ("L", np.pi)):
        p = ph + off
        a_t = -rad(G["A"]) * np.sin(p) - rad(G.get("A0", 0))
        a_k = rad(G["K0"]) + rad(G["K"]) * max(0.0, np.cos(p + 0.45)) ** 1.5
        a_f = -(a_t + a_k) * 0.92 - rad(G.get("toe", 0)) * max(0.0, np.cos(p + 1.2))
        P.turn(f"UpperLeg{s}", qx(a_t))
        P.turn(f"LowerLeg{s}", qx(a_k))
        P.turn(f"Foot{s}", qx(a_f))
        raises.append(leg_foot_drop(l1, l2, a_t, a_k))

        damp = G.get("arm_damp", {}).get(s, 1.0)
        a_s = rad(G["arm"]) * np.sin(p) * damp
        flex = rad(G["elbow0"]) + rad(G["elbow1"]) * max(0.0, -np.sin(p)) * damp
        P.turn(f"UpperArm{s}", qx(a_s))
        P.turn(f"LowerArm{s}", qx(-flex * (1 if damp > 0.5 else 0.0)))

    air = G.get("air", 0.0) * 0.5 * (1 - np.cos(2 * ph))
    P.move = np.array([G.get("sway", 0.0) * np.sin(ph), -min(raises) + air, 0.0])
    twist = rad(G.get("twist", 0.0)) * np.sin(ph)
    lean = rad(G.get("lean", 0.0))
    P.turn("Hips", qmul3(qx(lean * 0.6), qy(-twist * 0.5), qz(rad(G.get("roll", 0)) * np.sin(ph))))
    P.turn("Spine", qmul3(qx(lean * 0.4), qy(twist * 0.6)))
    P.turn("Chest", qy(twist * 0.5))
    P.turn("Neck", qmul3(qx(-lean * 0.5), qy(-twist * 0.4)))
    P.turn("Head", qx(-lean * 0.3 + rad(2) * np.sin(2 * ph)))
    extras(sk, P, G, ph, 1.0)
    return P


def extras(sk, P, G, ph, k):
    """Ocas, křídla a čelist: vrtí se v rytmu cyklu, k = jak moc (idle slaběji)."""
    for i in range(1, 5):
        if f"Tail{i}" in sk.index:
            a = G.get("tail", 0) * k * np.sin(ph + i * 0.7)
            P.turn(f"Tail{i}", qmul3(qy(rad(a)), qx(rad(G.get("tail_up", 0)) * k * np.sin(2 * ph + i * 0.5))))
    for s, sg in SIDE.items():
        if f"Wing{s}" in sk.index:
            a = G.get("wing", 0) * k * (0.5 + 0.5 * np.sin(2 * ph + 0.4))
            P.turn(f"Wing{s}", qz(-sg * rad(a)))
    if "Jaw" in sk.index and G.get("jaw", 0):
        P.turn("Jaw", qx(rad(G["jaw"]) * k * (0.5 + 0.5 * np.sin(2 * ph))))


def idle(sk, G, t, T=4.0):
    ph = 2 * np.pi * t / T
    P = Pose()
    P.turn("Spine", qx(rad(1.2) * np.sin(ph)))
    P.turn("Chest", qx(rad(1.6) * np.sin(ph - 0.5)))
    P.turn("Head", qmul3(qy(rad(7) * np.sin(ph * 0.5 + 0.3)), qx(rad(2) * np.sin(ph - 1.0))))
    for s, sg in SIDE.items():
        d = G.get("arm_damp", {}).get(s, 1.0)
        P.turn(f"UpperArm{s}", qmul3(qx(rad(2.5) * np.sin(ph + 0.8) * d), qz(sg * rad(1.5) * np.sin(ph) * d)))
        P.turn(f"LowerArm{s}", qx(-rad(2) * np.sin(ph + 1.4) * d))
    extras(sk, P, {**G, "tail": G.get("tail", 0) * 1.4, "wing": G.get("wing", 0) * 0.9}, ph * 2, 0.55)
    return P


def look_around(sk, G, t, T=5.0):
    ph = 2 * np.pi * t / T
    yaw = rad(44) * np.sin(ph) * (0.35 + 0.65 * np.sin(ph * 0.5) ** 2)
    P = idle(sk, G, t * 0.8, T=4.0)
    P.turn("Chest", qy(yaw * 0.12))
    P.turn("Neck", qy(yaw * 0.40))
    P.turn("Head", qmul3(qy(yaw * 0.55), qx(rad(4) * np.sin(ph * 2 + 1.0))))
    return P


def jump(sk, G, t, T=1.0):
    """Přikrčení, výskok s nataženýma rukama a dopad do dřepu."""
    u = t / T
    crouch = np.sin(np.pi * u / 0.3) if u < 0.3 else 0.0
    land = 0.75 * np.sin(np.pi * (u - 0.72) / 0.28) if u > 0.72 else 0.0
    d = max(crouch, land)
    air = np.sin(np.pi * (u - 0.3) / 0.42) if 0.3 <= u <= 0.72 else 0.0
    P = Pose()
    l1 = float(np.linalg.norm(sk.pos("UpperLegR") - sk.pos("LowerLegR")))
    l2 = float(np.linalg.norm(sk.pos("LowerLegR") - sk.pos("FootR")))
    a_t = -rad(38) * d - rad(18) * air
    a_k = rad(70) * d + rad(40) * air
    for s in SIDE:
        P.turn(f"UpperLeg{s}", qx(a_t))
        P.turn(f"LowerLeg{s}", qx(a_k))
        P.turn(f"Foot{s}", qx(-(a_t + a_k) * 0.9))
        k = G.get("arm_damp", {}).get(s, 1.0)
        P.turn(f"UpperArm{s}", qx((rad(35) * d - rad(150) * air) * k))
        P.turn(f"LowerArm{s}", qx(-rad(20) * air * k))
    P.move = np.array([0.0, -leg_foot_drop(l1, l2, a_t, a_k) + G.get("jump_h", 0.34) * air, 0.0])
    P.turn("Spine", qx(rad(14) * d - rad(6) * air))
    extras(sk, P, G, 2 * np.pi * u * 2, 0.8)
    return P


def wave(sk, G, t, T=3.2, arm="L"):
    """Pozdrav: volná ruka vyletí nahoru a mává předloktím. Začíná i končí v klidu."""
    r = smooth(t, 0.0, 0.5) * (1 - smooth(t, T - 0.6, T))
    ph = 2 * np.pi * t / T
    P = idle(sk, G, t, T=T)
    sg = SIDE[arm]
    P.turn(f"UpperArm{arm}", qz(sg * rad(125) * r))
    P.turn(f"LowerArm{arm}", qz(sg * (rad(22) + rad(28) * np.sin(ph * 3.0)) * r))
    P.turn("Chest", qz(-sg * rad(4) * r))
    P.turn("Head", qz(-sg * rad(7) * r))
    return P


def cert_threat(sk, G, t, T=3.2):
    """Čert hrozí: píchá vidlemi, škrábe drápy, otvírá tlamu a šlehá ocasem."""
    r = smooth(t, 0.0, 0.45) * (1 - smooth(t, T - 0.55, T))
    ph = 2 * np.pi * t / T
    P = idle(sk, G, t, T=T)
    P.turn("UpperArmR", qx(rad(22) * r + rad(12) * r * np.sin(ph * 3)))
    P.turn("UpperArmL", qz(rad(105) * r))
    P.turn("LowerArmL", qz((rad(25) + rad(40) * np.sin(ph * 4)) * r))
    P.turn("Jaw", qx(rad(26) * r * (0.5 + 0.5 * np.sin(ph * 3 + 1))))
    P.turn("Spine", qx(rad(10) * r))
    P.turn("Head", qx(-rad(8) * r))
    for i in range(1, 5):
        P.turn(f"Tail{i}", qy(rad(28) * r * np.sin(ph * 4 + i * 0.7)))
    return P


def clips_for(sk, G, G_run, wave_fn=wave, with_jump=True):
    out = {
        "Walk": make_clip(sk, lambda t: gait(sk, G, 2 * np.pi * t / G["T"]), G["T"]),
        "Run": make_clip(sk, lambda t: gait(sk, G_run, 2 * np.pi * t / G_run["T"]), G_run["T"]),
        "Idle": make_clip(sk, lambda t: idle(sk, G, t), 4.0),
        "LookAround": make_clip(sk, lambda t: look_around(sk, G, t), 5.0),
        "Wave": make_clip(sk, lambda t: wave_fn(sk, G, t), 3.2),
    }
    if with_jump:
        out["Jump"] = make_clip(sk, lambda t: jump(sk, G, t), 1.0, loop=False)
    return out


# ------------------------------------------------------------------ Mikuláš

MIK_MAT = [("robe", (0.78, 0.10, 0.12)), ("trim", (0.97, 0.96, 0.92)), ("skin", (0.94, 0.72, 0.62)),
           ("mitre", (0.80, 0.12, 0.14)), ("gold", (0.92, 0.74, 0.22)), ("boots", (0.26, 0.16, 0.10)),
           ("sack", (0.58, 0.42, 0.26)), ("beard", (0.98, 0.98, 0.98))]

STAFF_X, STAFF_Z = -0.26, 0.56

MIK = dict(
    hips_y=0.88, hip_x=0.10, knee_y=0.50, ankle_y=0.10, toe_z=0.14,
    spine_y=1.00, chest_y=1.14, neck_y=1.36, head_y=1.42, shoulder_x=0.26, shoulder_y=1.24,
    elbowR=(-0.30, 1.00, 0.22), wristR=(STAFF_X, 1.08, STAFF_Z - 0.05),
    elbowL=(0.31, 0.98, 0.04), wristL=(0.31, 0.78, 0.14),
)
MIK_ROBE = [(0, 0.22, 0, 0.37, 0.35), (0, 0.45, 0, 0.32, 0.30), (0, 0.70, 0, 0.28, 0.27),
            (0, 0.90, 0.03, 0.31, 0.33), (0, 1.10, 0.01, 0.29, 0.28), (0, 1.26, 0, 0.27, 0.20),
            (0, 1.36, 0, 0.14, 0.12), (0, 1.40, 0, 0.09, 0.09)]
MIK_MITRE = [(0, 1.64, -0.005, 0.16, 0.175), (0, 1.78, -0.02, 0.14, 0.15), (0, 1.96, -0.045, 0.085, 0.09),
             (0, 2.12, -0.07, 0.03, 0.03), (0, 2.18, -0.075, 0.0, 0.0)]

def shell(rings, y0, y1, grow, n=4):
    """Prstenec obalující plášť mezi výškami y0..y1 (lem, pásek)."""
    out = []
    for y in np.linspace(y0, y1, n):
        cx, cz, rx, rz = profile_at(rings, y)
        out.append((cx, y, cz, rx + grow, rz + grow))
    return out


def build_mikulas():
    p = MIK
    sk = skeleton(p)
    sk.add("Hair", "Head", (0, 1.50, 0))
    sk.add("Mitre", "Head", (0, 1.62, 0))
    b = Builder(sk, MIK_MAT)
    robe_skin = skirt_skin(sk, 0.22)

    b.add(lathe(MIK_ROBE, nu=20), "robe", robe_skin)
    b.add(lathe(shell(MIK_ROBE, 0.17, 0.36, 0.022, 4)[:], nu=20), "trim", robe_skin)
    front = [(0, y, profile_at(MIK_ROBE, y)[1] + profile_at(MIK_ROBE, y)[3] + 0.004)
             for y in (1.30, 1.18, 1.08, 0.92, 0.72, 0.52, 0.34, 0.24)]
    b.add(sweep(front, 0.027, nu=8, dome=(True, True)), "trim", robe_skin)
    b.add(lathe([(0, 1.25, -0.005, 0.17, 0.15), (0, 1.33, -0.005, 0.185, 0.165),
                 (0, 1.41, 0, 0.12, 0.11)], nu=18), "trim", torso_skin(sk))
    b.add(lathe(shell(MIK_ROBE, 0.78, 0.86, 0.012, 3), nu=20), "gold", robe_skin)

    for s in "RL":
        arm_tube(b, sk, s, 0.085, "robe", end=-0.18)
        names, pts = limb(sk, s, "arm")
        d = pts[2] - pts[1]
        d /= np.linalg.norm(d)
        b.add(sweep([pts[2] - d * 0.10, pts[2] + d * 0.0], 0.092, nu=10), "trim", rigid(sk, f"LowerArm{s}"))
        hand(b, sk, s, "skin", 0.062, 0.7)
        leg_tube(b, sk, s, 0.08, "boots")
        hx = SIDE[s] * p["hip_x"]
        b.add(blob((hx, 0.06, 0.06), (0.09, 0.07, 0.16)), "boots", rigid(sk, f"Foot{s}"))

    head = blob((0, 1.56, 0), (0.165, 0.175, 0.17), nu=20, nv=12)
    b.add(head, "skin", rigid(sk, "Head"))
    b.add(blob((0, 1.545, 0.17), (0.045, 0.045, 0.05)), "skin", rigid(sk, "Head"))
    b.add(blob((0, 1.58, -0.075), (0.185, 0.19, 0.15), nu=18), "beard", rigid(sk, "Hair"))
    b.add(blob((0, 1.495, 0.15), (0.125, 0.04, 0.06)), "beard", rigid(sk, "Hair"))
    b.add(blob((0, 1.36, 0.10), (0.17, 0.20, 0.115), nu=18, nv=12), "beard", rigid(sk, "Hair"))

    b.add(lathe(MIK_MITRE, nu=20), "mitre", rigid(sk, "Mitre"))
    b.add(lathe([(0, 1.62, -0.005, 0.166, 0.182), (0, 1.70, -0.012, 0.158, 0.172)], nu=20), "gold", rigid(sk, "Mitre"))
    b.add(blob((0, 2.19, -0.075), (0.035, 0.035, 0.035)), "gold", rigid(sk, "Mitre"))
    for sg in (-1, 1):
        cx, cz, rx, rz = profile_at(MIK_MITRE, 1.90)
        b.add(blob((sg * (rx * 0.80 + 0.012), 1.90, cz), (0.014, 0.105, 0.026)), "gold", rigid(sk, "Mitre"))
        b.add(blob((sg * (rx * 0.80 + 0.012), 1.91, cz), (0.014, 0.026, 0.07)), "gold", rigid(sk, "Mitre"))

    arc = [(STAFF_X, y, STAFF_Z) for y in (0.03, 0.6, 1.2, 1.7, 1.95)]
    zc, yc, rr = STAFF_Z + 0.13, 1.95, 0.13
    for a in np.linspace(np.pi, -np.pi * 0.45, 14)[1:]:
        arc.append((STAFF_X, yc + rr * np.sin(a), zc + rr * np.cos(a)))
    radii = np.concatenate([np.full(5, 0.030), np.linspace(0.030, 0.020, 13)])
    b.add(sweep(arc, radii, nu=10), "gold", rigid(sk, "HandR"))

    b.add(blob((0.04, 1.0, -0.38), (0.25, 0.33, 0.22), rot=rot_x(rad(8)), nu=18, nv=12), "sack", rigid(sk, "Chest"))
    b.add(blob((0.04, 1.33, -0.34), (0.09, 0.08, 0.09)), "sack", rigid(sk, "Chest"))

    G = dict(T=1.15, A=22, A0=0, K0=4, K=36, toe=10, arm=12, elbow0=8, elbow1=8, twist=4, sway=0.012,
             roll=1.5, lean=2, arm_damp={"R": 0.0, "L": 1.0})
    G_run = dict(G, T=0.8, A=30, K=58, arm=30, elbow0=16, elbow1=22, twist=6, lean=8, air=0.05)
    clips = clips_for(sk, G, G_run, wave, with_jump=False)
    return b, clips


# ------------------------------------------------------------------- anděl

AND_MAT = [("dress", (0.98, 0.98, 0.98)), ("trim", (0.93, 0.76, 0.26)), ("skin", (0.96, 0.76, 0.66)),
           ("hair", (0.96, 0.80, 0.34)), ("wing", (0.96, 0.97, 1.0)), ("halo", (0.98, 0.84, 0.25)),
           ("shoe", (0.90, 0.70, 0.30))]

AND = dict(
    hips_y=0.80, hip_x=0.085, knee_y=0.46, ankle_y=0.09, toe_z=0.12,
    spine_y=0.92, chest_y=1.04, neck_y=1.22, head_y=1.28, shoulder_x=0.17, shoulder_y=1.12,
    elbowR=(-0.20, 0.88, 0.05), wristR=(-0.19, 0.68, 0.15),
    elbowL=(0.20, 0.88, 0.04), wristL=(0.20, 0.68, 0.11),
)
AND_DRESS = [(0, 0.14, 0, 0.31, 0.29), (0, 0.35, 0, 0.24, 0.22), (0, 0.62, 0, 0.17, 0.16),
             (0, 0.82, 0, 0.115, 0.115), (0, 0.98, 0.005, 0.14, 0.13), (0, 1.10, 0, 0.17, 0.12),
             (0, 1.19, 0, 0.06, 0.06), (0, 1.22, 0, 0.055, 0.055)]


def build_andel():
    sk = skeleton(AND)
    sk.add("Hair", "Head", (0, 1.45, 0))
    sk.add("Halo", "Head", (0, 1.72, 0))
    sk.add("WingL", "Chest", (0.06, 1.10, -0.12))
    sk.add("WingR", "Chest", (-0.06, 1.10, -0.12))
    b = Builder(sk, AND_MAT)
    dress_skin = skirt_skin(sk, 0.14, kmax=0.55)

    b.add(lathe(AND_DRESS, nu=20), "dress", dress_skin)
    b.add(lathe(shell(AND_DRESS, 0.11, 0.2, 0.016, 3), nu=20), "trim", dress_skin)
    b.add(lathe(shell(AND_DRESS, 0.78, 0.86, 0.010, 3), nu=20), "trim", dress_skin)

    for s in "RL":
        sg = SIDE[s]
        names, pts = limb(sk, s, "arm")
        b.add(sweep([pts[0], pts[0] + (pts[1] - pts[0]) * 0.5], 0.075, nu=10),
              "dress", rigid(sk, f"UpperArm{s}"))
        arm_tube(b, sk, s, 0.045, "skin", end=-0.1)
        hand(b, sk, s, "skin", 0.05, 0.7)
        leg_tube(b, sk, s, 0.04, "skin")
        hx = sg * AND["hip_x"]
        b.add(blob((hx, 0.05, 0.05), (0.058, 0.05, 0.12)), "shoe", rigid(sk, f"Foot{s}"))

    b.add(blob((0, 1.44, 0), (0.15, 0.16, 0.155), nu=20, nv=12), "skin", rigid(sk, "Head"))
    b.add(blob((0, 1.43, 0.155), (0.03, 0.03, 0.035)), "skin", rigid(sk, "Head"))
    b.add(blob((0, 1.475, -0.045), (0.168, 0.18, 0.165), nu=18, nv=12), "hair", rigid(sk, "Hair"))
    b.add(blob((0, 1.585, 0.09), (0.12, 0.055, 0.075)), "hair", rigid(sk, "Hair"))
    b.add(blob((0, 1.37, -0.15), (0.12, 0.16, 0.07)), "hair", rigid(sk, "Hair"))
    for sg in (-1, 1):
        b.add(sweep([(sg * 0.145, 1.50, -0.01), (sg * 0.165, 1.36, -0.06), (sg * 0.16, 1.22, -0.10)],
                    [0.055, 0.05, 0.045], nu=10), "hair", rigid(sk, "Hair"))
        b.add(blob((sg * 0.16, 1.18, -0.10), (0.065, 0.065, 0.065)), "hair", rigid(sk, "Hair"))

    b.add(torus((0, 1.73, -0.02), 0.13, 0.021, axis=(1, 0, 0)), "halo", rigid(sk, "Halo"))

    for s, sg in (("L", 1), ("R", -1)):
        root = sk.pos(f"Wing{s}")
        for psi, ln in zip((8, 28, 48, 70, 94), (0.72, 0.78, 0.74, 0.64, 0.52)):
            d = np.array([sg * 0.22, np.cos(rad(psi)), -np.sin(rad(psi))])
            d /= np.linalg.norm(d)
            b.add(spindle(root + d * 0.04, root + d * (0.04 + ln), (0.022, 0.09)), "wing", rigid(sk, f"Wing{s}"))

    G = dict(T=1.2, A=20, A0=0, K0=3, K=32, toe=8, arm=14, elbow0=6, elbow1=10, twist=5, sway=0.01,
             roll=2, lean=1, wing=13)
    G_run = dict(G, T=0.85, A=28, K=55, arm=32, elbow0=18, elbow1=25, twist=7, lean=7, air=0.06, wing=22)
    G["jump_h"] = 0.36
    clips = clips_for(sk, G, G_run, wave, with_jump=True)
    return b, clips


# -------------------------------------------------------------------- čert

CERT_MAT = [("fur", (0.17, 0.12, 0.12)), ("fur2", (0.40, 0.22, 0.16)), ("muzzle", (0.50, 0.33, 0.28)),
            ("hoof", (0.10, 0.09, 0.09)), ("horn", (0.88, 0.84, 0.72)), ("tongue", (0.86, 0.12, 0.16)),
            ("metal", (0.64, 0.66, 0.70)), ("wood", (0.50, 0.34, 0.20))]

FORK_X, FORK_Z = -0.24, 0.50

CERT = dict(
    hips_y=0.80, hip_x=0.09, knee_y=0.46, ankle_y=0.12, toe_z=0.12,
    spine_y=0.94, spine_z=0.02, chest_y=1.08, chest_z=0.05, neck_y=1.26, neck_z=0.10,
    head_y=1.32, head_z=0.13, shoulder_x=0.22, shoulder_y=1.18, shoulder_z=0.05,
    elbowR=(-0.27, 0.95, 0.20), wristR=(FORK_X, 1.04, FORK_Z - 0.06),
    elbowL=(0.26, 0.92, 0.10), wristL=(0.28, 0.72, 0.21),
)
CERT_TORSO = [(0, 0.78, 0, 0.17, 0.14), (0, 0.92, 0.02, 0.15, 0.13), (0, 1.08, 0.05, 0.19, 0.15),
              (0, 1.20, 0.07, 0.20, 0.14), (0, 1.30, 0.10, 0.09, 0.09)]
CERT_SHORTS = [(0, 0.56, 0, 0.21, 0.18), (0, 0.70, 0, 0.22, 0.19), (0, 0.82, 0, 0.19, 0.16), (0, 0.88, 0, 0.12, 0.10)]

def build_cert():
    p = CERT
    sk = skeleton(p)
    sk.add("Jaw", "Head", (0, 1.40, 0.20))
    sk.add("Horn", "Head", (0, 1.60, 0.14))
    for i, pos in enumerate([(0, 0.80, -0.14), (0, 0.84, -0.30), (0, 0.95, -0.42), (0, 1.12, -0.50)], 1):
        sk.add(f"Tail{i}", "Hips" if i == 1 else f"Tail{i - 1}", pos)
    b = Builder(sk, CERT_MAT)

    b.add(lathe(CERT_TORSO, nu=16), "fur", torso_skin(sk))
    shorts = skirt_skin(sk, 0.56, kmax=0.45)
    b.add(lathe(CERT_SHORTS, nu=16), "fur2", shorts)

    for s in "RL":
        arm_tube(b, sk, s, 0.05, "fur", end=-0.05)
        hand(b, sk, s, "fur", 0.058, 0.8)
        leg_tube(b, sk, s, [0.065, 0.058, 0.045], "fur")
        hx = SIDE[s] * p["hip_x"]
        b.add(blob((hx, 0.055, 0.055), (0.07, 0.06, 0.11)), "hoof", rigid(sk, f"Foot{s}"))

    b.add(blob((0, 1.49, 0.13), (0.17, 0.17, 0.18), nu=18, nv=12), "fur", rigid(sk, "Head"))
    b.add(blob((0, 1.44, 0.29), (0.085, 0.075, 0.11)), "muzzle", rigid(sk, "Head"))
    b.add(blob((0, 1.465, 0.385), (0.04, 0.035, 0.035)), "hoof", rigid(sk, "Head"))
    for sg in (-1, 1):
        b.add(spindle((sg * 0.13, 1.52, 0.07), (sg * 0.30, 1.68, 0.0), (0.025, 0.05)), "fur", rigid(sk, "Head"))
        b.add(sweep([(sg * 0.075, 1.62, 0.15), (sg * 0.13, 1.75, 0.14), (sg * 0.13, 1.87, 0.07), (sg * 0.09, 1.95, -0.04)],
                    [0.045, 0.036, 0.024, 0.008], nu=8), "horn", rigid(sk, "Horn"))
    b.add(sweep([(0, 1.375, 0.30), (0, 1.33, 0.40), (0, 1.25, 0.46)], [0.026, 0.024, 0.02], nu=8),
          "tongue", rigid(sk, "Jaw"))
    b.add(spindle((0, 1.40, 0.24), (0, 1.27, 0.27), (0.035, 0.04)), "fur", rigid(sk, "Jaw"))

    tail = [(0, 0.80, -0.14), (0, 0.84, -0.30), (0, 0.95, -0.42), (0, 1.12, -0.50), (0, 1.30, -0.50)]
    b.add(sweep(tail, [0.05, 0.045, 0.036, 0.028, 0.02], nu=8), "fur",
          chain(sk, ["Tail1", "Tail2", "Tail3", "Tail4"], 0.05))
    b.add(blob((0, 1.40, -0.49), (0.014, 0.10, 0.065), rot=rot_x(rad(-10))), "tongue", rigid(sk, "Tail4"))

    shaft = [(FORK_X, 0.03, FORK_Z), (FORK_X, 0.9, FORK_Z), (FORK_X, 1.66, FORK_Z)]
    b.add(sweep(shaft, 0.028, nu=8), "wood", rigid(sk, "HandR"))
    b.add(sweep([(FORK_X, 1.66, FORK_Z - 0.15), (FORK_X, 1.70, FORK_Z), (FORK_X, 1.66, FORK_Z + 0.15)], 0.022, nu=8),
          "metal", rigid(sk, "HandR"))
    for dz, top in ((-0.15, 1.96), (0.0, 2.06), (0.15, 1.96)):
        b.add(sweep([(FORK_X, 1.66, FORK_Z + dz), (FORK_X, top, FORK_Z + dz)], [0.02, 0.008], nu=8),
              "metal", rigid(sk, "HandR"))

    G = dict(T=0.9, A=30, A0=0, K0=6, K=48, toe=12, arm=24, elbow0=10, elbow1=14, twist=8, sway=0.014,
             roll=2.5, lean=3, tail=14, tail_up=5, jaw=7, arm_damp={"R": 0.0, "L": 1.0})
    G_run = dict(G, T=0.6, A=40, K=78, arm=48, elbow0=20, elbow1=30, twist=10, lean=14, air=0.09,
                 tail=22, jaw=12)
    G["jump_h"] = 0.4
    clips = clips_for(sk, G, G_run, cert_threat, with_jump=True)
    return b, clips


CHARACTERS = {
    "mik_mikulas": build_mikulas,
    "mik_andel": build_andel,
    "mik_cert": build_cert,
}


def main():
    keys = sys.argv[1:] or list(CHARACTERS)
    for key in keys:
        name = key if key in CHARACTERS else f"mik_{key}"
        b, clips = CHARACTERS[name]()
        dst = OUT / f"{name}.glb"
        write_rigged(dst, b, clips)
        v = b.arrays()[0]
        print(f"{dst}  {dst.stat().st_size // 1024} kB, {len(v)} vrcholů, "
              f"výška {v[:, 1].max():.2f}, délka {np.ptp(v[:, 2]):.2f}, šířka {np.ptp(v[:, 0]):.2f}")


if __name__ == "__main__":
    main()
