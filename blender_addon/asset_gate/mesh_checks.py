"""Gate 1 scene checks (m1-1 .. m1-13, m1-15). Read-only: never edits user data."""
import math
import re
import statistics

import bmesh
from mathutils.bvhtree import BVHTree

from .i18n import tr

# Numeric noise tolerance for "equals 0 / equals 1" comparisons, not a pass/fail threshold.
FLOAT_EPS = 1e-5
# Sampling resolution of the UV overlap measurement.
UV_GRID = 1024
NUMERIC_SUFFIX = re.compile(r"\.\d{3,}$")


def result(status, detail="", **values):
    return {"status": status, "detail": detail, "values": values}


def selectable(res, key, mode, per_object):
    """Attach element indices so the panel can select them. Stripped before the report is written.

    mode: 'VERT' | 'EDGE' | 'FACE'; per_object: {object name: [indices]} of the evaluated mesh.
    """
    per_object = {name: sorted(idx) for name, idx in per_object.items() if idx}
    if per_object:
        res.setdefault("_select", {})[key] = {"mode": mode, "objects": per_object}
    return res


def _names(items, limit=5):
    items = list(items)
    more = tr("res.more", n=len(items) - limit) if len(items) > limit else ""
    return ", ".join(items[:limit]) + more


class SceneData:
    """World-space evaluated bmesh per mesh object, plus the materials and images they use."""

    def __init__(self, context):
        self.scene = context.scene
        self.objects = [o for o in context.scene.objects if o.type == 'MESH']
        edited = [o for o in self.objects if o.mode == 'EDIT']
        for o in edited:
            o.update_from_editmode()  # sync edits made in Edit Mode without leaving it
            o.data.update_tag()
        if edited:
            context.view_layer.update()
        depsgraph = context.evaluated_depsgraph_get()
        self.meshes = {}
        for o in self.objects:
            # Not bm.from_object(): it returns an empty mesh for objects in Edit Mode.
            evaluated = o.evaluated_get(depsgraph)
            bm = bmesh.new()
            bm.from_mesh(evaluated.to_mesh())
            evaluated.to_mesh_clear()
            bm.transform(o.matrix_world)
            bm.normal_update()
            for seq in (bm.verts, bm.edges, bm.faces):
                seq.index_update()
            self.meshes[o.name] = bm
        # Element counts at check time, so selection can tell when the result is out of date.
        self.counts = {name: (len(bm.verts), len(bm.edges), len(bm.faces)) for name, bm in self.meshes.items()}

        self.materials = []
        self.empty_slots = []
        for o in self.objects:
            if not o.material_slots:
                self.empty_slots.append(o.name)
            for slot in o.material_slots:
                if slot.material is None:
                    self.empty_slots.append(o.name)
                elif slot.material not in self.materials:
                    self.materials.append(slot.material)

        self.images = []
        for mat in self.materials:
            if not mat.node_tree:
                continue
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image and node.image not in self.images:
                    self.images.append(node.image)

    def free(self):
        for bm in self.meshes.values():
            bm.free()
        self.meshes = {}

    @property
    def tris(self):
        return sum(len(f.verts) - 2 for bm in self.meshes.values() for f in bm.faces)

    def bounds(self):
        coords = [v.co for bm in self.meshes.values() for v in bm.verts]
        lo = [min(c[i] for c in coords) for i in range(3)]
        hi = [max(c[i] for c in coords) for i in range(3)]
        return lo, hi


def check_integrity(data, cfg):
    # Same definitions as 3D-Print Toolbox 1.4.1: the area threshold is the length threshold squared.
    length = cfg["mesh"]["degenerateThreshold"]
    area = length ** 2
    found = {"nonManifold": {}, "badContiguous": {}, "zeroFaces": {}, "zeroEdges": {}}
    for name, bm in data.meshes.items():
        found["nonManifold"][name] = [e.index for e in bm.edges if not e.is_manifold]
        found["badContiguous"][name] = [e.index for e in bm.edges if e.is_manifold and not e.is_contiguous]
        found["zeroFaces"][name] = [f.index for f in bm.faces if f.calc_area() <= area]
        found["zeroEdges"][name] = [e.index for e in bm.edges if e.calc_length() <= length]
    totals = {key: sum(len(i) for i in per.values()) for key, per in found.items()}
    bad_objects = sorted({name for per in found.values() for name, idx in per.items() if idx})
    if not bad_objects:
        return result("pass", **totals)
    labels = {"nonManifold": "Non-manifold edge", "badContiguous": "Bad contiguous edge",
              "zeroFaces": "Zero face", "zeroEdges": "Zero edge"}
    detail = tr("m1-1.found", list=", ".join(f"{labels[k]} {n}" for k, n in totals.items() if n))
    res = result("fail", detail, objects=bad_objects, **totals)
    for key in ("nonManifold", "badContiguous", "zeroEdges"):
        selectable(res, key, 'EDGE', found[key])
    return selectable(res, "zeroFaces", 'FACE', found["zeroFaces"])


def check_intersect(data, cfg):
    per_object = {}
    for name, bm in data.meshes.items():
        tree = BVHTree.FromBMesh(bm, epsilon=0.00001)
        faces = {i for pair in tree.overlap(tree) for i in pair}
        if faces:
            per_object[name] = faces
    total = sum(len(f) for f in per_object.values())
    if not total:
        return result("pass", intersectingFaces=0)
    res = result("review", tr("m1-2.review", n=total),
                 intersectingFaces=total, objects={n: len(f) for n, f in per_object.items()})
    return selectable(res, "intersectingFaces", 'FACE', per_object)


def check_merge_loose(data, cfg):
    dist = cfg["mesh"]["mergeDistance"]
    found = {"doubles": {}, "looseVerts": {}, "looseEdges": {}, "interiorFaces": {}}
    for name, bm in data.meshes.items():
        targetmap = bmesh.ops.find_doubles(bm, verts=bm.verts, dist=dist)["targetmap"]
        found["doubles"][name] = [v.index for v in targetmap]
        found["looseVerts"][name] = [v.index for v in bm.verts if not v.link_edges]
        found["looseEdges"][name] = [e.index for e in bm.edges if not e.link_faces]
        found["interiorFaces"][name] = [f.index for f in bm.faces if all(len(e.link_faces) > 2 for e in f.edges)]
    values = {key: sum(len(i) for i in per.values()) for key, per in found.items()}
    note = tr("m1-3.interior", n=values["interiorFaces"]) if values["interiorFaces"] else ""
    if values["doubles"] or values["looseVerts"] or values["looseEdges"]:
        detail = tr("m1-3.fail", doubles=values["doubles"], verts=values["looseVerts"], edges=values["looseEdges"])
        res = result("fail", f"{detail} · {note}" if note else detail, **values)
    else:
        res = result("pass", note, **values)
    selectable(res, "doubles", 'VERT', found["doubles"])
    selectable(res, "looseVerts", 'VERT', found["looseVerts"])
    selectable(res, "looseEdges", 'EDGE', found["looseEdges"])
    return selectable(res, "interiorFaces", 'FACE', found["interiorFaces"])


def check_normals(data, cfg):
    flipped = {}
    for name, bm in data.meshes.items():
        fixed = bm.copy()
        bmesh.ops.recalc_face_normals(fixed, faces=fixed.faces)
        fixed.normal_update()
        idx = [a.index for a, b in zip(bm.faces, fixed.faces) if a.normal.dot(b.normal) < 0]
        fixed.free()
        if idx:
            flipped[name] = idx
    total = sum(len(i) for i in flipped.values())
    if total:
        res = result("fail", tr("m1-4.fail", n=total), flippedFaces=total,
                     objects={n: len(i) for n, i in flipped.items()})
        return selectable(res, "flippedFaces", 'FACE', flipped)
    return result("pass", flippedFaces=0)


def check_transforms(data, cfg):
    unapplied = {}
    for o in data.objects:
        loc, rot, scale = o.matrix_world.decompose()
        if (loc.length > FLOAT_EPS or rot.angle > FLOAT_EPS
                or any(abs(s - 1) > FLOAT_EPS for s in scale)):
            unapplied[o.name] = {
                "location": [round(v, 5) for v in loc],
                "rotation": [round(math.degrees(v), 3) for v in rot.to_euler()],
                "scale": [round(v, 5) for v in scale],
            }
    if unapplied:
        return result("fail", tr("m1-5.fail", names=_names(unapplied)), unapplied=unapplied)
    return result("pass", objects=len(data.objects))


def check_triangulated(data, cfg):
    non_tris = {name: idx for name, bm in data.meshes.items()
                if (idx := [f.index for f in bm.faces if len(f.verts) != 3])}
    total = sum(len(i) for i in non_tris.values())
    if total:
        res = result("fail", tr("m1-6.fail", n=total), nonTris=total,
                     objects={n: len(i) for n, i in non_tris.items()})
        return selectable(res, "nonTris", 'FACE', non_tris)
    return result("pass", nonTris=0)


def check_pivot(data, cfg):
    lo, hi = data.bounds()
    base = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]]
    size = [round(hi[i] - lo[i], 4) for i in range(3)]
    offsets = {}
    for o in data.objects:
        if o.parent is None:
            origin = o.matrix_world.translation
            offsets[o.name] = [round(origin[i] - base[i], 4) for i in range(3)]
    worst = max(math.sqrt(sum(c * c for c in off)) for off in offsets.values())
    values = {"offset": round(worst, 4), "offsets": offsets, "size": size}
    if worst <= FLOAT_EPS:
        return result("pass", **values)
    return result("review", tr("m1-7.review", d=worst), **values)


def check_naming(data, cfg):
    pattern = re.compile(cfg["naming"]["pattern"])
    blocklist = [re.compile(p) for p in cfg["naming"]["defaultNameBlocklist"]]
    groups = {
        "object": [o.name for o in data.objects],
        "mesh": sorted({o.data.name for o in data.objects}),
        "material": [m.name for m in data.materials],
        "texture": [i.name for i in data.images],
    }
    bad = {}
    for kind, names in groups.items():
        for name in names:
            if NUMERIC_SUFFIX.search(name):
                reason = tr("m1-8.suffix")
            elif any(b.match(name) for b in blocklist):
                reason = tr("m1-8.default")
            elif not pattern.match(name):
                reason = tr("m1-8.pascal")
            else:
                continue
            bad[f"{kind}:{name}"] = reason
    checked = sum(len(n) for n in groups.values())
    if bad:
        return result("fail", tr("m1-8.fail", n=len(bad)),
                      bad=bad, checked=checked)
    return result("pass", checked=checked)


def material_textures(material):
    """Image names used by a material; Unity's Setup uses this to wire textures (SPEC D9)."""
    if not material.node_tree:
        return []
    return [n.image.name for n in material.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image]


def check_material_count(data, cfg):
    count = len(data.materials)
    names = [m.name for m in data.materials]
    textures = {m.name: material_textures(m) for m in data.materials}
    if data.empty_slots:
        return result("fail", tr("m1-9.noMaterial", names=_names(sorted(set(data.empty_slots)))),
                      materials=count, names=names, textures=textures)
    if count > cfg["material"]["maxWithoutReview"]:
        return result("review", tr("m1-9.review", n=count, names=_names(names)),
                      materials=count, names=names, textures=textures)
    return result("pass", materials=count, names=names, textures=textures)


def _uv_triangles(bm, uv_layer, with_face=False):
    for tri in bm.calc_loop_triangles():
        uvs = [tuple(loop[uv_layer].uv) for loop in tri]
        yield (uvs, tri[0].face.index) if with_face else uvs


def _edge(a, b, px, py):
    """Signed edge function, evaluated identically for both faces sharing the edge."""
    if a > b:
        return -_edge(b, a, px, py)
    return (b[0] - a[0]) * (py - a[1]) - (b[1] - a[1]) * (px - a[0])


def _pixel_box(tri):
    us, vs = [p[0] for p in tri], [p[1] for p in tri]
    x0 = max(int(math.floor(min(us) * UV_GRID)), 0)
    x1 = min(int(math.ceil(max(us) * UV_GRID)), UV_GRID)
    y0 = max(int(math.floor(min(vs) * UV_GRID)), 0)
    y1 = min(int(math.ceil(max(vs) * UV_GRID)), UV_GRID)
    return x0, x1, y0, y1


def _inside(tri, x0, x1, y0, y1):
    import numpy as np

    a, b, c = tri
    area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    px = (np.arange(x0, x1) + 0.5) / UV_GRID
    py = ((np.arange(y0, y1) + 0.5) / UV_GRID)[:, None]
    sign = 1 if area > 0 else -1
    return ((sign * _edge(a, b, px, py) > 0) & (sign * _edge(b, c, px, py) > 0)
            & (sign * _edge(c, a, px, py) > 0))


def _uv_overlap(triangles):
    """Share of covered texels covered more than once, and the indices of triangles touching them."""
    import numpy as np

    counts = np.zeros((UV_GRID, UV_GRID), dtype=np.uint16)
    boxes = []
    for tri in triangles:
        a, b, c = tri
        box = _pixel_box(tri)
        degenerate = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) == 0
        if degenerate or box[0] >= box[1] or box[2] >= box[3]:
            boxes.append(None)
            continue
        boxes.append(box)
        x0, x1, y0, y1 = box
        counts[y0:y1, x0:x1] += _inside(tri, *box)
    covered = int((counts >= 1).sum())
    if not covered:
        return 0.0, []
    overlapped = counts >= 2
    ratio = int(overlapped.sum()) / covered
    touching = []
    if ratio:
        for i, (tri, box) in enumerate(zip(triangles, boxes)):
            if box and (overlapped[box[2]:box[3], box[0]:box[1]] & _inside(tri, *box)).any():
                touching.append(i)
    return ratio, touching


def check_uv(data, cfg):
    missing, outside, triangles, owners = [], {}, [], []
    for name, bm in data.meshes.items():
        uv_layer = bm.loops.layers.uv.active
        if uv_layer is None:
            missing.append(name)
            continue
        faces = [f.index for f in bm.faces
                 if any(any(c < -FLOAT_EPS or c > 1 + FLOAT_EPS for c in loop[uv_layer].uv) for loop in f.loops)]
        if faces:
            outside[name] = faces
        for uvs, face in _uv_triangles(bm, uv_layer, with_face=True):
            triangles.append(uvs)
            owners.append((name, face))
    if missing:
        return result("fail", tr("m1-10.noUv", names=_names(missing)), missingUv=missing)
    ratio, touching = _uv_overlap(triangles)
    overlap = round(ratio * 100, 2)
    overlap_faces = {}
    for i in touching:
        name, face = owners[i]
        overlap_faces.setdefault(name, set()).add(face)
    values = {"outsideFaces": sum(len(f) for f in outside.values()), "overlapPercent": overlap,
              "overlapFaces": sum(len(f) for f in overlap_faces.values())}
    if outside:
        res = result("fail", tr("m1-10.outside", n=values["outsideFaces"]), **values)
    elif overlap > 0:
        res = result("review", tr("m1-10.overlap", p=overlap), **values)
    else:
        res = result("pass", **values)
    selectable(res, "outsideFaces", 'FACE', outside)
    return selectable(res, "overlapFaces", 'FACE', overlap_faces)


def _texture_size(data):
    sizes = sorted({tuple(i.size) for i in data.images})
    return sizes, (max(max(s) for s in sizes) if sizes else 0)


def texel_density(data):
    """Pixels per metre: texture size * sqrt(UV area / world area). None when it cannot be measured."""
    _, tex = _texture_size(data)
    uv_area = world_area = 0.0
    for bm in data.meshes.values():
        uv_layer = bm.loops.layers.uv.active
        if uv_layer is None:
            return None
        for a, b, c in _uv_triangles(bm, uv_layer):
            uv_area += abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2
        world_area += sum(f.calc_area() for f in bm.faces)
    if not tex or uv_area <= 0 or world_area <= 0:
        return None
    return tex * math.sqrt(uv_area / world_area)


def check_texel_density(data, cfg, peers):
    density = texel_density(data)
    if density is None:
        return result("fail", tr("m1-11.unmeasurable"))
    density = round(density, 1)
    peer_values = [p["checks"]["m1-11"]["values"]["pxPerMeter"] for p in peers
                   if "pxPerMeter" in p.get("checks", {}).get("m1-11", {}).get("values", {})]
    if not peer_values:
        return result("na", tr("m1-11.noPeers", d=density), pxPerMeter=density, peers=0)
    median = statistics.median(peer_values)
    diff = round(abs(density - median) / median * 100, 1)
    tolerance = cfg["texelDensity"]["tolerancePercent"]
    values = {"pxPerMeter": density, "packMedian": round(median, 1), "diffPercent": diff, "peers": len(peer_values)}
    if diff > tolerance:
        return result("review", tr("m1-11.review", d=density, median=median, diff=diff, tol=tolerance), **values)
    return result("pass", **values)


def check_texture_size(data, cfg, peers):
    if not data.images:
        return result("fail", tr("m1-12.none"))
    allowed = cfg["texture"]["allowedSizes"]
    sizes, tex = _texture_size(data)
    bad = {i.name: list(i.size) for i in data.images
           if i.size[0] != i.size[1] or i.size[0] not in allowed}
    values = {"sizes": [list(s) for s in sizes], "tex": tex}
    if bad:
        return result("fail", tr("m1-12.notAllowed", allowed=allowed, names=_names(f'{k} {v[0]}x{v[1]}' for k, v in bad.items())),
                      bad=bad, **values)
    if len(sizes) > 1:
        return result("fail", tr("m1-12.mixed", sizes=values["sizes"]), **values)
    peer_sizes = sorted({p["stats"]["tex"] for p in peers if p.get("stats", {}).get("tex")})
    values["packSizes"] = peer_sizes
    if peer_sizes and peer_sizes != [tex]:
        return result("review", tr("m1-12.pack", tex=tex, sizes=peer_sizes), **values)
    return result("pass", **values)


def check_baked_lighting(data, cfg):
    """m1-13: only a person can see light or shadow painted into the base color (SPEC D19).
    Always review; the confirmation resets when the model's textures change."""
    names = sorted(i.name for i in data.images)
    if not names:
        return result("na", tr("m1-13.noTexture"), textures=[])
    return result("review", tr("m1-13.review"), textures=names)


def model_stats(data):
    _, tex = _texture_size(data)
    return {"tris": data.tris, "tex": tex, "mats": len(data.materials), "objs": len(data.objects)}


def polygon_stats(data):
    """Counts like Meshy shows them (after modifiers): faces, triangles, vertices, edges, topology."""
    sides = [len(f.verts) for bm in data.meshes.values() for f in bm.faces]
    topology = "triangles" if sides and all(s == 3 for s in sides) else "quads" if sides and all(s == 4 for s in sides) else "mixed"
    return {
        "faces": len(sides),
        "tris": sum(s - 2 for s in sides),
        "verts": sum(len(bm.verts) for bm in data.meshes.values()),
        "edges": sum(len(bm.edges) for bm in data.meshes.values()),
        "topology": topology,
    }


def polycount_advice(cfg, tris, asset_type="none", platform="none"):
    """Which kind of work this triangle count suits, from config polycount (SPEC D22). Advice, never pass/fail."""
    guide = cfg["polycount"]
    tier = next(t["key"] for t in guide["tiers"] if t["max"] is None or tris <= t["max"])
    fits = [f"{kind}:{plat}" for kind, plats in guide["byType"].items()
            for plat, (lo, hi) in plats.items() if lo <= tris <= hi]
    advice = {"tier": tier, "fits": fits, "assetType": asset_type or "none", "platform": platform or "none"}
    if asset_type and asset_type != "none" and platform and platform != "none":
        plat = guide["vrUses"] if platform == "vr" else platform
        span = guide["byType"].get(asset_type, {}).get(plat)
        advice["range"] = span or []
        advice["fit"] = "none" if not span else "below" if tris < span[0] else "above" if tris > span[1] else "within"
    return advice


def check_polycount(data, cfg, asset_type="none", platform="none"):
    """m1-16: polygon counts plus which kind of work they suit (SPEC D22). Always review: a person decides;
    the confirmation resets when the counts, the model type or the platform change."""
    stats = polygon_stats(data)
    advice = polycount_advice(cfg, stats["tris"], asset_type, platform)
    guide = cfg["polycount"]
    parts = [tr("m1-16.tier", tris=f"{stats['tris']:,}", tier=tr("tier." + advice["tier"]), hint=tr("tierHint." + advice["tier"]))]
    if "fit" in advice:
        kind, plat = tr("type." + advice["assetType"]), tr("platform." + advice["platform"])
        if advice["fit"] == "none":
            parts.append(tr("m1-16.noGuide", type=kind, platform=plat))
        else:
            lo, hi = advice["range"]
            parts.append(tr("m1-16." + advice["fit"], lo=f"{lo:,}", hi=f"{hi:,}", type=kind, platform=plat))
    elif advice["fits"]:
        names = [f"{tr('type.' + k)} ({tr('platform.' + p)})" for k, p in (f.split(":") for f in advice["fits"])]
        parts.append(tr("m1-16.fits", list=_names(names, limit=4)))
    else:
        lowest = min(lo for plats in guide["byType"].values() for lo, _ in plats.values())
        parts.append(tr("m1-16.fitsTiny" if stats["tris"] < lowest else "m1-16.fitsNone"))
    if platform == "vr":
        budget = guide["vrSceneBudget"]
        parts.append(tr("m1-16.vr", q2=f"{budget.get('quest2', 0):,}", q3=f"{budget.get('quest3', 0):,}"))
    parts.append(tr("m1-16.confirm"))
    return result("review", " · ".join(parts), **stats, **advice)


def check_stats(data, cfg, budget):
    stats = model_stats(data)
    if budget and stats["tris"] > budget:
        return result("fail", tr("m1-15.over", tris=stats["tris"], budget=budget), budget=budget, **stats)
    return result("pass", "" if budget else tr("m1-15.noBudget"), budget=budget or 0, **stats)
