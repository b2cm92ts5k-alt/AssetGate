"""Fix buttons for Gate 1 (SPEC §10). Each fix runs only when the user presses it and confirms.

Mesh, transform and naming fixes change the open scene (undoable with Ctrl+Z, the .blend is never
saved). Texture fixes write NEW image files next to the originals and point the materials at them;
the original files are never overwritten (SPEC D13).
"""
import math
import os
import re
from collections import Counter

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import core, mesh_checks
from .i18n import tr

SAFE, RISKY = "safe", "risky"
INVALID_CHARS = re.compile(r"[^A-Za-z0-9]+")


class Fix:
    def __init__(self, check_id, variant, level, applies):
        self.check_id, self.variant, self.level, self.applies = check_id, variant, level, applies

    @property
    def label(self):
        return tr(f"fix.{self.variant}")


def _v(check, key):
    return check.get("values", {}).get(key) or 0


# Shown under a check when its result matches `applies`; most-recommended first.
FIXES = [
    Fix("m1-1", "dissolve", SAFE, lambda c: c["status"] == "fail" and (_v(c, "zeroFaces") or _v(c, "zeroEdges"))),
    Fix("m1-1", "recalcContiguous", SAFE, lambda c: c["status"] == "fail" and _v(c, "badContiguous")),
    Fix("m1-1", "fillHoles", RISKY, lambda c: c["status"] == "fail" and _v(c, "nonManifold")),
    Fix("m1-3", "mergeLoose", SAFE, lambda c: c["status"] == "fail"),
    Fix("m1-4", "normals", SAFE, lambda c: c["status"] == "fail"),
    Fix("m1-5", "applyTransform", SAFE, lambda c: c["status"] == "fail"),
    Fix("m1-6", "triangulate", RISKY, lambda c: c["status"] == "fail"),
    Fix("m1-7", "pivot", SAFE, lambda c: c["status"] == "review"),
    Fix("m1-8", "rename", RISKY, lambda c: c["status"] == "fail" and c.get("values", {}).get("bad")),
    Fix("m1-10", "smartUv", RISKY, lambda c: c["status"] == "fail" and c.get("values", {}).get("missingUv")),
    Fix("m1-11", "texel", RISKY, lambda c: c["status"] == "review" and _v(c, "packMedian")),
    # Only for sizes the rule rejects; "differs from the pack" is a review for a person (m1-11 decides sharpness).
    Fix("m1-12", "textureSize", RISKY, lambda c: c["status"] == "fail" and c.get("values", {}).get("sizes")),
    Fix("m1-14", "reexport", SAFE, lambda c: c["status"] == "fail"),
]

# Checks without a fix button get a short "how to fix it yourself" hint.
HINTS = {"m1-2": "hint.m1-2", "m1-9": "hint.m1-9", "m1-10": "hint.m1-10", "m1-15": "hint.m1-15"}


def available(check_id, check):
    return [f for f in FIXES if f.check_id == check_id and f.applies(check)]


def find(check_id, variant):
    return next(f for f in FIXES if f.check_id == check_id and f.variant == variant)


# ---------------------------------------------------------------- helpers

def mesh_objects(context):
    return [o for o in context.scene.objects if o.type == 'MESH']


def _object_mode(context):
    if context.object and context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def _single_user(objects):
    """Give objects that share mesh data their own copy, so baking one does not move the others."""
    for o in objects:
        if o.data.users > 1:
            o.data = o.data.copy()


def _edit_meshes(objects, fn):
    """Run fn(bm) once per mesh data block. Returns the summed counts fn returns."""
    total = 0
    for mesh in {o.data for o in objects}:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        total += fn(bm) or 0
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
    return total


def _modifier_note(objects):
    names = [o.name for o in objects if o.modifiers]
    return [tr("fix.note.modifiers", names=", ".join(names))] if names else []


def _hierarchy_order(objects):
    depth = {o: 0 for o in objects}
    for o in objects:
        p = o.parent
        while p:
            depth[o] += 1
            p = p.parent
    return sorted(objects, key=lambda o: depth[o])


def _bake_transforms(context, objects, offset):
    """Bake each object's world transform into its mesh, shift the geometry by -offset (world),
    and leave the object at the world origin with no rotation/scale."""
    _single_user(objects)
    worlds = {o: o.matrix_world.copy() for o in objects}
    shift = Matrix.Translation(-Vector(offset))
    for o in objects:
        o.data.transform(shift @ worlds[o])
        o.data.update()
    for o in _hierarchy_order(objects):   # parents first, so children get the parent's new matrix
        o.matrix_world = Matrix.Identity(4)
        context.view_layer.update()


def _base_centre(context):
    data = mesh_checks.SceneData(context)
    try:
        lo, hi = data.bounds()
    finally:
        data.free()
    return [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]]


# ---------------------------------------------------------------- names (m1-8)

def _valid_name(name, pattern, blocklist):
    return (not mesh_checks.NUMERIC_SUFFIX.search(name) and not any(b.match(name) for b in blocklist)
            and pattern.match(name) is not None)


def _clean(name):
    """Smallest change that fits the naming rule: drop .001 and the file extension, invalid
    characters become "_", first letter upper case. Words stay "_"-separated so Unity's Setup
    still recognises texture roles (MEMORY #texture-role-words)."""
    name = mesh_checks.NUMERIC_SUFFIX.sub("", name)
    name = re.sub(r"\.(png|jpe?g|tga|tiff?|exr|bmp|webp)$", "", name, flags=re.IGNORECASE)
    words = [w for w in INVALID_CHARS.split(name) if w]
    if not words:
        return ""
    name = "_".join(words)
    return name[0].upper() + name[1:]


def rename_plan(context, cfg, model):
    """[(kind, datablock, old name, new name)] for every name m1-8 rejects."""
    pattern = re.compile(cfg["naming"]["pattern"])
    blocklist = [re.compile(p) for p in cfg["naming"]["defaultNameBlocklist"]]
    model_name = _clean(model) or "Model"
    data = mesh_checks.SceneData(context)
    try:
        groups = [
            ("object", list(data.objects), bpy.data.objects),
            ("mesh", sorted({o.data for o in data.objects}, key=lambda m: m.name), bpy.data.meshes),
            ("material", list(data.materials), bpy.data.materials),
            ("texture", list(data.images), bpy.data.images),
        ]
    finally:
        data.free()
    kind_word = {"object": "", "mesh": "Mesh", "material": "Material", "texture": "Texture"}
    plan = []
    for kind, blocks, collection in groups:
        taken = {b.name for b in collection}
        for block in blocks:
            if _valid_name(block.name, pattern, blocklist):
                continue
            candidates = [_clean(block.name), "_".join(w for w in (model_name, kind_word[kind]) if w)]
            base = next((c for c in candidates if c and _valid_name(c, pattern, blocklist)), candidates[-1])
            new, n = base, 2
            while new in taken or not _valid_name(new, pattern, blocklist):
                new, n = f"{base}_{n}", n + 1
            taken.add(new)
            plan.append((kind, block, block.name, new))
    return plan


# ---------------------------------------------------------------- textures (m1-11, m1-12)

def _nearest(value, allowed):
    """Allowed size closest to value on a log scale (halving and doubling count the same)."""
    return min(allowed, key=lambda a: (abs(math.log(a / value)), -a))


def _model_images(context):
    data = mesh_checks.SceneData(context)
    try:
        return list(data.images), list(data.materials)
    finally:
        data.free()


# Generated images remember the image they were made from, so a later fix always resizes the
# original (no quality loss from resizing twice) and can switch back to it without a new file.
SOURCE_KEY = "asset_gate_source"


def source_image(image):
    name = image.get(SOURCE_KEY)
    return (bpy.data.images.get(name) if name else None) or image


class TextureChange:
    """One image of the model: what it becomes and how ("original" | "reuse" | "new")."""

    def __init__(self, image, size):
        self.image, self.size = image, size
        self.source = source_image(image)
        self.action, self.target, self.path = "new", None, ""

    def line(self):
        old = f"{self.image.size[0]}×{self.image.size[1]}"
        new = f"{self.size[0]}×{self.size[1]}"
        how = {"original": tr("fix.texture.original", name=self.source.name),
               "reuse": tr("fix.texture.reuse", file=os.path.basename(self.path)),
               "new": tr("fix.texture.new", file=os.path.basename(self.path))}[self.action]
        return f"{self.image.name}: {old} → {new} ({how})"


def texture_plan(context, cfg, check_id, check):
    """[TextureChange] for every image that changes size, plus extra dialog lines.

    Never larger than the original rounded to the nearest allowed size: scaling up adds file
    size, not detail."""
    allowed = sorted(cfg["texture"]["allowedSizes"])
    images, _ = _model_images(context)
    images = [i for i in images if i.size[0] and i.size[1]]
    if not images:
        return [], []
    values = check.get("values", {})
    lines = []
    if check_id == "m1-11":
        largest = max(max(i.size) for i in images)
        factor = largest and _nearest(largest * values["packMedian"] / values["pxPerMeter"], allowed) / largest
        wanted = {i: _nearest(max(i.size) * factor, allowed) for i in images}
    else:
        sizes = Counter(_nearest(max(i.size), allowed) for i in images)
        target = max(sizes, key=lambda s: (sizes[s], s))   # most common, then the larger
        wanted = {i: target for i in images}
    changes = []
    for image, size in wanted.items():
        src = source_image(image)
        size = min(size, _nearest(max(src.size), allowed))
        if tuple(image.size) != (size, size):
            changes.append(TextureChange(image, (size, size)))
    if check_id == "m1-11" and changes:
        factor = changes[0].size[0] / max(changes[0].image.size)
        predicted = values["pxPerMeter"] * factor
        diff = abs(predicted - values["packMedian"]) / values["packMedian"] * 100
        lines.append(tr("fix.texel.predict", d=values["pxPerMeter"], new=predicted, median=values["packMedian"], diff=diff))
    for change in changes:
        _decide(change)
    return changes, lines


def _decide(change):
    """Prefer the original, then a file made earlier, and only then write a new one."""
    src, size = change.source, change.size
    if tuple(src.size) == size:
        change.action, change.target = "original", src
        return
    for image in bpy.data.images:
        if image.get(SOURCE_KEY) == src.name and tuple(image.size) == size and image.filepath \
                and os.path.isfile(bpy.path.abspath(image.filepath)):
            change.action, change.target, change.path = "reuse", image, bpy.path.abspath(image.filepath)
            return
    path = _image_path(src, size)
    if os.path.isfile(path):
        loaded = bpy.data.images.load(path, check_existing=True)
        if tuple(loaded.size) == size:
            loaded[SOURCE_KEY] = src.name
            loaded.colorspace_settings.name = src.colorspace_settings.name
            change.action, change.target, change.path = "reuse", loaded, path
            return
        path = _image_path(src, size, unique=True)   # a different file has that name: never overwrite
    change.path = path


def _image_path(src, size, unique=False):
    if src.filepath and not src.packed_file:
        folder = os.path.dirname(bpy.path.abspath(src.filepath))
    elif bpy.data.filepath:
        folder = os.path.dirname(bpy.data.filepath)
    else:
        raise core.GateError(tr("fix.err.saveBlend"))
    stem = _clean(src.name) or "Texture"
    suffix = f"{size[0]}" if size[0] == size[1] else f"{size[0]}x{size[1]}"
    path, n = os.path.join(folder, f"{stem}_{suffix}.png"), 2
    while unique and os.path.exists(path):
        path, n = os.path.join(folder, f"{stem}_{suffix}_{n}.png"), n + 1
    return path


def _write_resized(change):
    src, (w, h) = change.source, change.size
    # Read the source pixels explicitly: image.copy() of a packed (or not yet loaded) image has
    # no pixel buffer, and scaling it produced blank textures on a real model (MEMORY #packed-image-blank).
    sw, sh = src.size
    pixels = np.empty(sw * sh * 4, dtype=np.float32)
    src.pixels.foreach_get(pixels)
    if not pixels.any():
        raise core.GateError(tr("fix.err.noPixels", name=src.name))
    scaled = bpy.data.images.new("AssetGateScale", sw, sh, alpha=True, float_buffer=src.is_float)
    try:
        scaled.colorspace_settings.name = src.colorspace_settings.name
        scaled.pixels.foreach_set(pixels)
        scaled.scale(w, h)
        out = np.empty(w * h * 4, dtype=np.float32)
        scaled.pixels.foreach_get(out)
    finally:
        bpy.data.images.remove(scaled)
    new = bpy.data.images.new(os.path.splitext(os.path.basename(change.path))[0], w, h,
                              alpha=True, float_buffer=src.is_float)
    new.colorspace_settings.name = src.colorspace_settings.name
    new.pixels.foreach_set(out)
    new.alpha_mode = src.alpha_mode
    new.filepath_raw = change.path
    new.file_format = 'PNG'
    new.save()
    new[SOURCE_KEY] = src.name
    return new


def resize_textures(context, changes):
    """Point the model's materials at the resized images. Returns the files written."""
    _, materials = _model_images(context)
    written = []
    for change in changes:
        if change.action == "new":
            change.target = _write_resized(change)
            written.append(change.path)
        # Keep the original even when no material uses it any more: Blender drops unused
        # data when the file is saved, and a packed original would be lost for good.
        change.source.use_fake_user = True
        for mat in materials:
            for node in (mat.node_tree.nodes if mat.node_tree else []):
                if node.type == 'TEX_IMAGE' and node.image == change.image:
                    node.image = change.target
    return written


# ---------------------------------------------------------------- plan / apply

def plan(context, cfg, fix, check, model, fbx_path):
    """Lines describing what the fix will change. Raises GateError when there is nothing to do."""
    objects = mesh_objects(context)
    lines = []
    v = fix.variant
    if v in ("dissolve", "recalcContiguous", "fillHoles", "mergeLoose", "normals", "triangulate"):
        lines.append(tr(f"fix.{v}.desc", objects=len(objects)))
        lines += _modifier_note(objects)
    elif v in ("applyTransform", "pivot"):
        lines.append(tr(f"fix.{v}.desc", names=", ".join(o.name for o in objects)))
        lines += _modifier_note(objects)
    elif v == "rename":
        changes = rename_plan(context, cfg, model)
        if not changes:
            raise core.GateError(tr("fix.err.nothing"))
        lines.append(tr("fix.rename.desc"))
        lines += [f"{kind}: {old} → {new}" for kind, _, old, new in changes]
    elif v == "smartUv":
        missing = [o.name for o in objects if not o.data.uv_layers]
        lines.append(tr("fix.smartUv.desc", names=", ".join(missing)))
    elif v in ("texel", "textureSize"):
        changes, extra = texture_plan(context, cfg, fix.check_id, check)
        if not changes:
            raise core.GateError(tr("fix.err.noUpscale"))
        lines.append(tr("fix.texture.desc"))
        lines += [c.line() for c in changes]
        lines += extra
        lines.append(tr("fix.texture.files"))
    elif v == "reexport":
        if not fbx_path:
            raise core.GateError(tr("fix.err.noFbx"))
        lines.append(tr("fix.reexport.desc", path=bpy.path.abspath(fbx_path)))
    if fix.level == RISKY:
        lines.append(tr("fix.riskyNote"))
    return lines


def apply(context, cfg, fix, check, model, fbx_path):
    """Apply the fix to the open scene. Returns a short summary for the status bar."""
    _object_mode(context)
    objects = mesh_objects(context)
    v = fix.variant
    mesh_cfg = cfg["mesh"]
    if v == "dissolve":
        n = _edit_meshes(objects, lambda bm: bmesh.ops.dissolve_degenerate(
            bm, dist=mesh_cfg["degenerateThreshold"], edges=bm.edges) and 0)
    elif v == "recalcContiguous" or v == "normals":
        n = _edit_meshes(objects, lambda bm: bmesh.ops.recalc_face_normals(bm, faces=bm.faces) and 0)
    elif v == "fillHoles":
        n = _edit_meshes(objects, lambda bm: len(bmesh.ops.holes_fill(bm, edges=bm.edges, sides=0)["faces"]))
    elif v == "mergeLoose":
        def merge(bm):
            before = len(bm.verts)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=mesh_cfg["mergeDistance"])
            bmesh.ops.delete(bm, geom=[e for e in bm.edges if not e.link_faces], context='EDGES')
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_edges], context='VERTS')
            return before - len(bm.verts)
        n = _edit_meshes(objects, merge)
    elif v == "triangulate":
        n = _edit_meshes(objects, lambda bm: len(bmesh.ops.triangulate(
            bm, faces=[f for f in bm.faces if len(f.verts) > 3], quad_method='BEAUTY', ngon_method='BEAUTY')["faces"]))
    elif v == "applyTransform":
        _bake_transforms(context, objects, (0, 0, 0))
        n = len(objects)
    elif v == "pivot":
        _bake_transforms(context, objects, _base_centre(context))
        n = len(objects)
    elif v == "rename":
        changes = rename_plan(context, cfg, model)
        for _, block, _, new in changes:
            block.name = new
        n = len(changes)
    elif v == "smartUv":
        missing = [o for o in objects if not o.data.uv_layers]
        for o in context.view_layer.objects:
            o.select_set(o in missing)
        context.view_layer.objects.active = missing[0]
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project()
        bpy.ops.object.mode_set(mode='OBJECT')
        n = len(missing)
    elif v in ("texel", "textureSize"):
        changes, _ = texture_plan(context, cfg, fix.check_id, check)
        resize_textures(context, changes)
        n = len(changes)
    elif v == "reexport":
        from .unity_export import _export_fbx
        _export_fbx(bpy.path.abspath(fbx_path), cfg)
        n = 1
    else:
        raise core.GateError(tr("fix.err.nothing"))
    return tr("fix.done", label=fix.label, n=n)
