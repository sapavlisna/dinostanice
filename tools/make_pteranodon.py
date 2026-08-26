"""Postavi letajiciho ptakojestera z modelu, ktery prisel bez kostry.

Animovany pterosaur se pod otevrenou licenci sehnat neda (viz CREDITS.md), zato
staticky ano. Tenhle nastroj z nej vyrobi tvora, ktery mava kridly: vytahne
jednoho ze tri v puvodni scene, narovna ho do kanonicke polohy, odvodi kostru
z geometrie a dopise animaci letu.

    python tools/make_pteranodon.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dinostanice.glbexport import write_skinned
from dinostanice.gltf import Model

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/models_src/pterosaurs_scene.glb"
DST = ROOT / "data/models_src/pteranodon.glb"

SHOULDER = 0.12          # podil rozpeti, kde kridlo zacina (uvnitr = trup)
ELBOW = 0.45             # kde se kridlo lame na vnejsi cast
FLAP_DEG = 26.0          # rozkmit vnitrniho kridla
TIP_DEG = 20.0           # pridavek vnejsi casti
LAG = 0.16               # zpozdeni spicky za ramenem, v podilu cyklu
PERIOD = 1.4
FRAMES = 24


def split_bodies(model: Model, verts: np.ndarray) -> list[np.ndarray]:
    """Rozdeli scenu na jednotlive tvory podle prekryvu obalek primitiv.

    Kridla maji teziste daleko od tela, takze shlukovat podle stredu primitiv
    nestaci — spojuji se az protinajici se obalky.
    """
    boxes = [(verts[p.first_vertex:p.first_vertex + p.vertex_count].min(0),
              verts[p.first_vertex:p.first_vertex + p.vertex_count].max(0))
             for p in model.primitives]
    parent = list(range(len(boxes)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i in range(len(boxes)):
        for k in range(i + 1, len(boxes)):
            lo = np.maximum(boxes[i][0], boxes[k][0])
            hi = np.minimum(boxes[i][1], boxes[k][1])
            if np.all(hi - lo > -0.02):
                a, b = find(i), find(k)
                if a != b:
                    parent[b] = a

    groups: dict[int, list[int]] = {}
    for i in range(len(boxes)):
        groups.setdefault(find(i), []).append(i)
    masks = []
    for prims in groups.values():
        keep = np.zeros(len(model.indices), bool)
        for i in prims:
            p = model.primitives[i]
            keep[p.first_index // 3: p.first_index // 3 + p.index_count // 3] = True
        masks.append(keep)
    return sorted(masks, key=lambda m: -int(m.sum()))


def _occupancy(points: np.ndarray, grid: int = 28) -> np.ndarray:
    """Hruba voxelova maska mraku, znormovana na jednotkovou krychli."""
    lo, hi = points.min(0), points.max(0)
    idx = np.clip(((points - lo) / np.maximum(hi - lo, 1e-9) * (grid - 1)).astype(int),
                  0, grid - 1)
    vox = np.zeros((grid,) * 3, bool)
    vox[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    return vox


def symmetry_axis(verts: np.ndarray, steps: int = 40) -> np.ndarray:
    """Normala roviny, podle ktere je tvor nejlepe zrcadlovy.

    Osy z PCA nestaci: tvor je zachyceny uprostred mavnuti, jedno kridlo vys
    nez druhe, takze rozptyl miri sikmo. Symetrii ale mavnuti neporusi — levy
    a pravy bok tvora jsou porad zrcadlove.
    """
    centred = verts - verts.mean(0)
    best, score = np.array([1.0, 0.0, 0.0]), -1.0
    for theta in np.linspace(0, np.pi, steps, endpoint=False):
        for phi in np.linspace(0, np.pi, steps, endpoint=False):
            n = np.array([np.sin(theta) * np.cos(phi), np.sin(theta) * np.sin(phi),
                          np.cos(theta)])
            mirrored = centred - 2 * np.outer(centred @ n, n)
            a, b = _occupancy(centred), _occupancy(mirrored)
            overlap = float((a & b).sum()) / max(float((a | b).sum()), 1.0)
            if overlap > score:
                best, score = n, overlap
    return best


def canonicalise(verts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Otoci tvora do os: x rozpeti kridel, y vyska, z delka tela.

    Vraci otocene vrcholy a bazi, aby slo stejne otocit i normaly.
    """
    centre = verts.mean(0)
    n = symmetry_axis(verts)
    centred = verts - centre

    # v rovine symetrie je delka tela smer s nejvetsim rozptylem, vyska zbytek
    plane = centred - np.outer(centred @ n, n)
    _, _, vh = np.linalg.svd(plane, full_matrices=False)
    length, up = vh[0], np.cross(n, vh[0])
    basis = np.stack([n, up / np.linalg.norm(up), length])
    if np.linalg.det(basis) < 0:
        basis[1] *= -1
    return centred @ basis.T, basis


def mirror_half(verts: np.ndarray, normals: np.ndarray, tris: np.ndarray,
                group: np.ndarray):
    """Nahradi jednu polovinu tvora zrcadlem te druhe.

    Predloha se kresli shora, takze musi byt soumerna — jinak dite dostane
    zvire s jednim kridlem nahoru a druhym dolu. Zrcadli se ta polovina, ktera
    ma vic geometrie, aby se nic neztratilo.
    """
    centroid = verts[tris].mean(axis=1)[:, 0]
    keep = centroid >= 0 if (centroid >= 0).sum() >= len(centroid) / 2 else centroid <= 0
    sign = 1.0 if (centroid >= 0).sum() >= len(centroid) / 2 else -1.0

    half_tris = tris[keep]
    half_group = group[keep]
    used = np.unique(half_tris)
    remap = np.full(len(verts), -1, np.int64)
    remap[used] = np.arange(len(used))

    v = verts[used].copy()
    v[:, 0] = np.abs(v[:, 0]) * sign
    n = normals[used]
    t = remap[half_tris]

    flip = np.array([-1.0, 1.0, 1.0])
    v2 = v * flip
    n2 = n * flip
    t2 = t[:, ::-1] + len(v)                     # zrcadleni obraci orientaci sten

    return (np.vstack([v, v2]), np.vstack([n, n2]), np.vstack([t, t2]),
            np.concatenate([half_group, half_group]))


def head_direction(verts: np.ndarray) -> float:
    """Znamenko osy z, na kterem lezi hlava.

    Porovnava se objem obalky obou koncu, ne pocet vrcholu: hlava s hrebenem je
    mohutna, ale nohy s roztazenymi prsty maji vic geometrie a podle poctu
    vrcholu by vyhraly (namereno 10642 prstovych proti 6816 hlavovym).
    """
    z = verts[:, 2]
    edge = 0.6 * np.abs(z).max()

    def bulk(sel):
        q = verts[sel]
        return float(np.prod(q.max(0) - q.min(0))) if len(q) else 0.0

    return 1.0 if bulk(z > edge) > bulk(z < -edge) else -1.0


def build_rig(verts: np.ndarray):
    """Kostra ze symetrie: trup, hlava a dve dvoudilna kridla."""
    span = float(np.abs(verts[:, 0]).max())
    shoulder, elbow = SHOULDER * span, ELBOW * span

    facing = head_direction(verts)
    z = verts[:, 2] * facing
    head_start = 0.35 * z.max()
    head_centre = verts[z > head_start].mean(0) if (z > head_start).any() else verts.mean(0)

    names = [("Body", -1, (0.0, 0.0, 0.0)),
             ("Head", 0, tuple(float(x) for x in head_centre))]
    for side, sign in (("L", 1.0), ("R", -1.0)):
        names.append((f"Wing{side}", 0, (sign * shoulder, 0.0, 0.0)))
        names.append((f"WingTip{side}", len(names) - 1, (sign * (elbow - shoulder), 0.0, 0.0)))

    x = verts[:, 0]
    inner = np.clip((np.abs(x) - shoulder) / max(elbow - shoulder, 1e-6), 0, 1)
    outer = np.clip((np.abs(x) - elbow) / max(span - elbow, 1e-6), 0, 1)
    # hlava si bere z trupu, kridla se prelevaji ven; soucet je vzdy 1
    w_head = (1.0 - inner) * np.clip((z - head_start) / max(z.max() - head_start, 1e-6), 0, 1)
    w_body = 1.0 - inner - w_head
    w_inner = inner * (1.0 - outer)
    w_tip = inner * outer

    joints = np.zeros((len(verts), 4), np.uint8)
    weights = np.zeros((len(verts), 4), np.float32)
    left = x >= 0
    joints[:, 0] = 0
    joints[:, 1] = 1
    joints[:, 2] = np.where(left, 2, 4)
    joints[:, 3] = np.where(left, 3, 5)
    weights[:, 0] = w_body
    weights[:, 1] = w_head
    weights[:, 2] = w_inner
    weights[:, 3] = w_tip
    return names, joints, weights


def flap(names) -> dict:
    """Klip letu: kridla rotuji kolem podelne osy, spicka se opozduje."""
    times = np.linspace(0.0, PERIOD, FRAMES + 1)
    channels = {}
    for joint, (name, _parent, _t) in enumerate(names):
        if name == "Body":
            continue
        sign = 1.0 if name.endswith("L") else -1.0
        lag = LAG if "Tip" in name else 0.0
        amp = np.radians(TIP_DEG if "Tip" in name else FLAP_DEG)
        phase = 2 * np.pi * (times / PERIOD - lag)
        angle = sign * amp * np.sin(phase)
        quats = np.zeros((len(times), 4), np.float32)
        quats[:, 2] = np.sin(angle / 2)          # rotace kolem osy z = smeru letu
        quats[:, 3] = np.cos(angle / 2)
        channels[joint] = (times, quats)
    return {"Flying": channels}


def main() -> None:
    model = Model(SRC)
    verts, normals = model.posed(None, 0.0)
    mask = split_bodies(model, verts)[2]         # nejsymetrictejsi z te trojice

    tris = model.indices[mask]
    used = np.unique(tris)
    remap = np.full(len(verts), -1, np.int64)
    remap[used] = np.arange(len(used))

    v, basis = canonicalise(verts[used])
    n = normals[used] @ basis.T

    palette = {m.get("name"): m.get("pbrMetallicRoughness", {})
               .get("baseColorFactor", [0.5, 0.55, 0.45, 1])[:3]
               for m in model.g.get("materials", [])}
    group = model.tri_material[mask]
    order = {g: i for i, g in enumerate(sorted(set(group.tolist())))}
    colours = [palette.get(model.primitives[g].material, [0.5, 0.55, 0.45])
               for g in sorted(order)]
    group = np.array([order[g] for g in group], np.int32)

    v, n, tris, group = mirror_half(v, n, remap[tris], group)
    v -= np.array([0.0, v[:, 1].mean(), v[:, 2].mean()])

    names, joints, weights = build_rig(v)
    write_skinned(
        DST, verts=v, normals=n, tris=tris, tri_group=group, colours=colours,
        joints=joints, weights=weights, skeleton=names, clips=flap(names),
    )
    print(f"{DST} ({DST.stat().st_size // 1024} kB)")
    print(f"{len(v)} vrcholu, {len(tris)} trojuhelniku, rozpeti "
          f"{np.ptp(v[:, 0]):.2f}, delka {np.ptp(v[:, 2]):.2f}")


if __name__ == "__main__":
    main()
