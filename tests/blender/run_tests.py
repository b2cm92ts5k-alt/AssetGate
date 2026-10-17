"""Gate 1 tests. Each check gets a clean scene that passes and a deliberately broken one.

Usage: blender -b --factory-startup --python tests/blender/run_tests.py -- <empty work folder>
Reports written during the run stay in <work folder>/data/reports for schema validation.
"""
import json
import os
import sys
import traceback

import bmesh
import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "blender_addon"))

import asset_gate  # noqa: E402
from asset_gate import core, fixes, i18n  # noqa: E402

# Most assertions below match Thai result text; the English case switches explicitly.
i18n.LANG = "th"

WORK = sys.argv[sys.argv.index("--") + 1]
DATA = os.path.join(WORK, "data")
FBX_DIR = os.path.join(WORK, "fbx")
PACK = "Test Pack"
GOOD_EXPORT = dict(axis_forward='-Z', axis_up='Y', bake_space_transform=True, embed_textures=False)

results = []
case_no = 0


def build_clean(name="Crate", tex=1024):
    """Closed, triangulated, UV-mapped 1 m box with its origin at the bottom centre."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bm.loops.layers.uv.new("UVMap")
    bmesh.ops.create_cube(bm, size=1.0, calc_uvs=True)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, 0.5))
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)

    image = bpy.data.images.new(f"{name}_BaseColor", tex, tex)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    mat.node_tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
    mesh.materials.append(mat)
    bpy.context.view_layer.update()
    return obj


def edit(obj, fn):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    fn(bm)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def export(model, **overrides):
    os.makedirs(FBX_DIR, exist_ok=True)
    path = os.path.join(FBX_DIR, f"{model}_{case_no}.fbx")
    bpy.ops.export_scene.fbx(filepath=path, **{**GOOD_EXPORT, **overrides})
    return path


def gate(model="Crate", fbx=None, **export_overrides):
    if fbx is None:
        fbx = export(model, **export_overrides)
    report, path = core.run_gate1(bpy.context, DATA, PACK, model, fbx)
    return report["checks"], path


def case(name):
    def wrap(fn):
        global case_no
        case_no += 1
        try:
            fn()
            results.append((name, None))
        except Exception:
            results.append((name, traceback.format_exc()))
        return fn
    return wrap


def expect(checks, check_id, status, contains=""):
    got = checks[check_id]
    assert got["status"] == status, f"{check_id}: expected {status}, got {got['status']} — {got['detail']} {got['values']}"
    assert contains in got["detail"], f"{check_id}: detail {got['detail']!r} lacks {contains!r}"


def reset_data():
    """Fresh Data folder so peers/budget from earlier cases do not leak in."""
    import shutil
    shutil.rmtree(DATA, ignore_errors=True)
    os.makedirs(DATA)


# ---------------------------------------------------------------- clean model

@case("clean model: every check passes, report written")
def _():
    reset_data()
    build_clean()
    checks, path = gate()
    for check_id in core.CHECK_IDS:
        # m1-11: no other model in the pack yet · m1-13: a person looks at the texture (SPEC D19)
        want = {"m1-11": "na", "m1-13": "review", "m1-16": "review"}.get(check_id, "pass")
        expect(checks, check_id, want)
    assert checks["m1-13"]["values"]["textures"] == ["Crate_BaseColor"]
    assert path and os.path.exists(path)
    assert os.path.exists(os.path.join(DATA, "config.json")), "config.json should be copied on first run"
    with open(path, encoding="utf-8") as f:
        report = json.load(f)
    assert report["stats"] == {"tris": 12, "tex": 1024, "mats": 1, "objs": 1}, report["stats"]
    assert len(report["source"]["fbxSha256"]) == 64


@case("no FBX: scene checks run, m1-14 pending, no report file")
def _():
    reset_data()
    build_clean()
    report, path = core.run_gate1(bpy.context, DATA, PACK, "Crate", "")
    expect(report["checks"], "m1-14", "pending")
    expect(report["checks"], "m1-1", "pass")
    assert path is None and not os.path.exists(core.report_path(DATA, PACK, "Crate"))


@case("checking does not modify the scene")
def _():
    reset_data()
    obj = build_clean()
    before = (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.materials), len(bpy.data.images),
              [tuple(v.co) for v in obj.data.vertices])
    gate()
    after = (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.materials), len(bpy.data.images),
             [tuple(v.co) for v in obj.data.vertices])
    assert before == after


# ---------------------------------------------------------------- broken models

@case("m1-1 fail: hole in mesh (non-manifold)")
def _():
    obj = build_clean()
    edit(obj, lambda bm: bmesh.ops.delete(bm, geom=[list(bm.faces)[0]], context='FACES'))
    expect(gate()[0], "m1-1", "fail", "Non-manifold edge 3")


@case("m1-1 fail: zero-area face")
def _():
    obj = build_clean()

    def collapse(bm):
        face = list(bm.faces)[0]
        face.verts[0].co = face.verts[1].co
    edit(obj, collapse)
    checks, _ = gate()
    expect(checks, "m1-1", "fail")
    assert checks["m1-1"]["values"]["zeroFaces"] >= 1 and checks["m1-1"]["values"]["zeroEdges"] >= 1


@case("m1-2 review: self-intersecting geometry")
def _():
    obj = build_clean()

    def add_crossing(bm):
        geom = bmesh.ops.create_cube(bm, size=1.0, calc_uvs=True)
        bmesh.ops.translate(bm, verts=geom["verts"], vec=(0.5, 0.5, 1.0))
        bmesh.ops.triangulate(bm, faces=bm.faces)
    edit(obj, add_crossing)
    checks, _ = gate()
    expect(checks, "m1-2", "review")
    assert checks["m1-2"]["values"]["intersectingFaces"] > 0


@case("m1-3 fail: loose vertex")
def _():
    obj = build_clean()
    edit(obj, lambda bm: bm.verts.new((3, 3, 3)))
    checks, _ = gate()
    expect(checks, "m1-3", "fail")
    assert checks["m1-3"]["values"]["looseVerts"] == 1


@case("m1-3 fail: unmerged duplicate vertices")
def _():
    obj = build_clean()
    edit(obj, lambda bm: bmesh.ops.split_edges(bm, edges=bm.edges))
    checks, _ = gate()
    expect(checks, "m1-3", "fail")
    assert checks["m1-3"]["values"]["doubles"] > 0


@case("m1-4 fail: flipped face")
def _():
    obj = build_clean()
    edit(obj, lambda bm: bmesh.ops.reverse_faces(bm, faces=list(bm.faces)[:2]))
    checks, _ = gate()
    expect(checks, "m1-4", "fail")
    assert checks["m1-4"]["values"]["flippedFaces"] == 2


@case("m1-5 fail: unapplied scale")
def _():
    obj = build_clean()
    obj.scale = (2, 2, 2)
    bpy.context.view_layer.update()
    expect(gate()[0], "m1-5", "fail", "Crate")


@case("m1-5 fail: unapplied rotation and location")
def _():
    obj = build_clean()
    obj.rotation_euler = (0, 0, 0.5)
    obj.location = (1, 0, 0)
    bpy.context.view_layer.update()
    expect(gate()[0], "m1-5", "fail")


@case("m1-6 fail: quads not triangulated")
def _():
    obj = build_clean()
    edit(obj, lambda bm: bmesh.ops.join_triangles(
        bm, faces=bm.faces, angle_face_threshold=3.2, angle_shape_threshold=3.2))
    checks, _ = gate()
    expect(checks, "m1-6", "fail")
    assert checks["m1-6"]["values"]["nonTris"] == 6


@case("m1-7 review: origin away from bottom centre")
def _():
    obj = build_clean()
    edit(obj, lambda bm: bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, 0.25)))
    checks, _ = gate()
    expect(checks, "m1-7", "review")
    assert abs(checks["m1-7"]["values"]["offset"] - 0.25) < 1e-4


@case("m1-8 fail: default / suffixed / lowercase names")
def _():
    obj = build_clean()
    obj.name = "Crate.001"
    obj.data.name = "Mesh_0"
    obj.data.materials[0].name = "material"
    checks, _ = gate()
    expect(checks, "m1-8", "fail")
    bad = checks["m1-8"]["values"]["bad"]
    assert set(bad) == {"object:Crate.001", "mesh:Mesh_0", "material:material"}, bad


@case("m1-8 pass: underscore suffixes allowed")
def _():
    obj = build_clean()
    obj.name = "Crate_LOD0"
    expect(gate()[0], "m1-8", "pass")


@case("m1-9 review: two materials")
def _():
    obj = build_clean()
    obj.data.materials.append(bpy.data.materials.new("CrateMetal"))
    checks, _ = gate()
    expect(checks, "m1-9", "review")
    assert checks["m1-9"]["values"]["materials"] == 2


@case("m1-9 fail: no material")
def _():
    obj = build_clean()
    obj.data.materials.clear()
    expect(gate()[0], "m1-9", "fail")


@case("m1-10 fail: UV outside 0-1")
def _():
    obj = build_clean()
    for loop in obj.data.uv_layers.active.data:
        loop.uv = loop.uv * 2
    expect(gate()[0], "m1-10", "fail", "นอกกรอบ")


@case("m1-10 fail: no UV map")
def _():
    obj = build_clean()
    obj.data.uv_layers.remove(obj.data.uv_layers.active)
    obj.data.update_tag()
    expect(gate()[0], "m1-10", "fail", "ไม่มี UV")


@case("m1-10 review: overlapping UV islands")
def _():
    obj = build_clean()
    uv = obj.data.uv_layers.active.data
    corners = [(0.1, 0.1), (0.9, 0.1), (0.5, 0.9)]
    for poly in obj.data.polygons:
        for i, loop_index in enumerate(poly.loop_indices):
            uv[loop_index].uv = corners[i]
    checks, _ = gate()
    expect(checks, "m1-10", "review")
    assert checks["m1-10"]["values"]["overlapPercent"] > 90
    assert checks["m1-10"]["values"]["overlapFaces"] == 12


def write_peer(model, px_per_meter, tex=1024):
    path = core.report_path(DATA, PACK, model)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"stats": {"tex": tex},
                   "checks": {"m1-11": {"status": "na", "detail": "", "values": {"pxPerMeter": px_per_meter}}}}, f)


@case("m1-11 pass / review against pack median (SPEC D16)")
def _():
    reset_data()
    build_clean()
    own = gate()[0]["m1-11"]["values"]["pxPerMeter"]
    write_peer("Barrel", own * 1.1)
    checks, _ = gate()
    expect(checks, "m1-11", "pass")
    write_peer("Barrel", own * 2)
    checks, _ = gate()
    expect(checks, "m1-11", "review", "ค่ากลางของแพ็ก")
    reset_data()


@case("m1-12 fail: non power-of-two texture")
def _():
    build_clean(tex=1000)
    expect(gate()[0], "m1-12", "fail", "1000x1000")


@case("m1-12 review: size differs from the rest of the pack")
def _():
    reset_data()
    build_clean(tex=1024)
    write_peer("Barrel", 500, tex=2048)
    expect(gate()[0], "m1-12", "review", "2048")
    reset_data()


@case("m1-12 fail: no texture")
def _():
    obj = build_clean()
    nodes = obj.data.materials[0].node_tree.nodes
    nodes.remove(next(n for n in nodes if n.type == 'TEX_IMAGE'))
    expect(gate()[0], "m1-12", "fail", "ไม่พบเท็กซ์เจอร์")


@case("m1-14 fail: wrong axis")
def _():
    build_clean()
    expect(gate(axis_forward='Y', axis_up='Z')[0], "m1-14", "fail", "แกน")


@case("m1-14 fail: Apply Transform off")
def _():
    build_clean()
    expect(gate(bake_space_transform=False)[0], "m1-14", "fail", "Apply Transform")


@case("m1-14 fail: embedded texture")
def _():
    obj = build_clean()
    image = obj.data.materials[0].node_tree.nodes["Image Texture"].image
    os.makedirs(FBX_DIR, exist_ok=True)
    image.filepath_raw = os.path.join(FBX_DIR, "Crate_BaseColor.png")
    image.file_format = 'PNG'
    image.save()
    expect(gate(path_mode='COPY', embed_textures=True)[0], "m1-14", "fail", "ฝังในไฟล์")


@case("m1-14 fail: FBX is stale (scene edited after export)")
def _():
    obj = build_clean()
    fbx = export("Crate")
    edit(obj, lambda bm: bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=1) and
         bmesh.ops.triangulate(bm, faces=bm.faces))
    expect(gate(fbx=fbx)[0], "m1-14", "fail", "สามเหลี่ยม")


@case("m1-14 fail: FBX of a different size")
def _():
    obj = build_clean()
    fbx = export("Crate", global_scale=2.0)
    expect(gate(fbx=fbx)[0], "m1-14", "fail", "ขนาด")


@case("m1-14 fail: scene unit not metric 1.0")
def _():
    build_clean()
    bpy.context.scene.unit_settings.scale_length = 0.01
    expect(gate()[0], "m1-14", "fail", "Scene Unit")


@case("m1-14 fail: unreadable FBX")
def _():
    build_clean()
    os.makedirs(FBX_DIR, exist_ok=True)
    bad = os.path.join(FBX_DIR, "Broken.fbx")
    with open(bad, "wb") as f:
        f.write(b"not an fbx file")
    expect(gate(fbx=bad)[0], "m1-14", "fail", "อ่านไฟล์ FBX ไม่ได้")


@case("m1-15 fail: over the pack tris budget")
def _():
    reset_data()
    build_clean()
    with open(os.path.join(DATA, "state.json"), "w", encoding="utf-8") as f:
        json.dump({"v": 3, "models": {}, "packs": {PACK: {"budget": "10"}}}, f)
    expect(gate()[0], "m1-15", "fail", "เกินงบ")
    reset_data()


@case("m1-1 pass: small faces are not zero faces (Toolbox: area <= threshold squared)")
def _():
    obj = build_clean()
    edit(obj, lambda bm: bmesh.ops.scale(bm, verts=bm.verts, vec=(0.01, 0.01, 0.01)))
    checks, _ = gate()
    expect(checks, "m1-1", "pass")  # 1 cm cube: faces are 0.00005 m2, above 0.0001 ** 2


@case("language: English results contain no Thai text, Thai results do")
def _():
    import re
    thai = re.compile("[\u0e00-\u0e7f]")
    obj = build_clean()
    obj.name = "Crate.001"
    edit(obj, lambda bm: bmesh.ops.join_triangles(bm, faces=bm.faces, angle_face_threshold=3.2, angle_shape_threshold=3.2))
    try:
        i18n.LANG = "en"
        checks, path = gate()
        expect(checks, "m1-6", "fail", "not triangles")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        assert not thai.search(text), "English report must not contain Thai: " + thai.search(text).group()
        try:
            core.run_gate1(bpy.context, DATA, "", "Crate", "")
        except core.GateError as exc:
            assert "pack name" in str(exc), str(exc)
    finally:
        i18n.LANG = "th"
    checks, _ = gate()
    expect(checks, "m1-6", "fail", "สามเหลี่ยม")
    assert all(core.title(cid) for cid in core.CHECK_IDS)


@case("language: every string has both English and Thai")
def _():
    import re
    thai = re.compile("[\u0e00-\u0e7f]")
    for key, (en, th) in i18n.STRINGS.items():
        assert en and th, key
        assert not thai.search(en), "Thai text in English string " + key
        names = lambda s: sorted(re.findall(r"{(\w+)", s))
        assert names(en) == names(th), "placeholders differ in " + key


# ---------------------------------------------------------------- selection

def faces_selected(obj):
    bpy.ops.object.mode_set(mode='OBJECT')
    return {p.index for p in obj.data.polygons if p.select}


@case("selection: indices recorded per problem, never written to the report")
def _():
    reset_data()
    obj = build_clean()
    edit(obj, lambda bm: bmesh.ops.reverse_faces(bm, faces=[f for f in bm.faces if f.index in (3, 7)]))
    checks, path = gate()
    sel = core.last_selection[("m1-4", "flippedFaces")]
    assert sel["mode"] == 'FACE' and sel["objects"] == {"Crate": [3, 7]}, sel
    assert sel["counts"]["Crate"] == (8, 18, 12), sel["counts"]
    with open(path, encoding="utf-8") as f:
        assert "_select" not in f.read()
    assert all("_select" not in c for c in checks.values())


@case("selection: hole -> 3 non-manifold edges recorded")
def _():
    obj = build_clean()
    edit(obj, lambda bm: bmesh.ops.delete(bm, geom=[list(bm.faces)[0]], context='FACES'))
    gate()
    sel = core.last_selection[("m1-1", "nonManifold")]
    assert sel["mode"] == 'EDGE' and len(sel["objects"]["Crate"]) == 3, sel


@case("select operator: selects exactly the problem faces in Edit Mode")
def _():
    asset_gate.register()
    try:
        obj = build_clean()
        edit(obj, lambda bm: bmesh.ops.reverse_faces(bm, faces=[f for f in bm.faces if f.index in (3, 7)]))
        gate()
        bpy.context.view_layer.objects.active = obj
        assert bpy.ops.asset_gate.select(check_id="m1-4", key="flippedFaces") == {'FINISHED'}
        assert obj.mode == 'EDIT'
        assert faces_selected(obj) == {3, 7}
    finally:
        asset_gate.unregister()


@case("select operator: refuses when the mesh changed after the check")
def _():
    asset_gate.register()
    try:
        obj = build_clean()
        edit(obj, lambda bm: bmesh.ops.reverse_faces(bm, faces=[f for f in bm.faces if f.index == 0]))
        gate()
        edit(obj, lambda bm: bm.verts.new((5, 5, 5)))
        try:
            outcome = bpy.ops.asset_gate.select(check_id="m1-4", key="flippedFaces")
        except RuntimeError as exc:
            assert "เก่าแล้ว" in str(exc), str(exc)
        else:
            assert outcome == {'CANCELLED'}, outcome
    finally:
        asset_gate.unregister()


# ---------------------------------------------------------------- confirmations (SPEC D11)

def two_materials():
    obj = build_clean()
    obj.data.materials.append(bpy.data.materials.new("CrateMetal"))
    return obj


def read_confirms(model="Crate"):
    with open(core.confirms_path(DATA, PACK, model), encoding="utf-8") as f:
        return json.load(f)


@case("confirm: stored next to the report, kept while the result is unchanged, dropped when it changes")
def _():
    reset_data()
    obj = two_materials()
    fbx = export("Crate")
    report, _ = core.run_gate1(bpy.context, DATA, PACK, "Crate", fbx)
    assert core.set_confirm(DATA, report, "m1-9", True) == {"m1-9"}
    data = read_confirms()
    assert data["tool"] == "blender" and data["model"] == "Crate", data
    assert data["confirms"]["m1-9"]["values"] == json.loads(json.dumps(report["checks"]["m1-9"]["values"]))
    assert data["confirms"]["m1-9"]["values"]["materials"] == 2
    # same result -> still confirmed after a new check
    report, _ = core.run_gate1(bpy.context, DATA, PACK, "Crate", fbx)
    assert core.prune_confirms(DATA, report) == {"m1-9"}
    # result changes (third material) -> confirmation removed from the file
    obj.data.materials.append(bpy.data.materials.new("CrateWood"))
    report, _ = core.run_gate1(bpy.context, DATA, PACK, "Crate", export("Crate"))
    assert report["checks"]["m1-9"]["status"] == "review"
    assert read_confirms()["confirms"] == {}, read_confirms()


@case("confirm: refused for items that are not waiting for review; undo removes it")
def _():
    reset_data()
    two_materials()
    report, _ = core.run_gate1(bpy.context, DATA, PACK, "Crate", export("Crate"))
    try:
        core.set_confirm(DATA, report, "m1-1", True)
    except core.GateError as exc:
        assert "ไม่ได้รอยืนยัน" in str(exc), str(exc)
    else:
        raise AssertionError("expected GateError")
    core.set_confirm(DATA, report, "m1-9", True)
    assert core.set_confirm(DATA, report, "m1-9", False) == set()
    assert read_confirms()["confirms"] == {}


@case("confirm operator: needs a written report, then confirms and undoes")
def _():
    reset_data()
    asset_gate.register()
    original = asset_gate._data_folder
    asset_gate._data_folder = lambda _context: DATA
    try:
        two_materials()
        asset_gate._last.update(report=None, path=None, confirmed=set())
        try:
            outcome = bpy.ops.asset_gate.confirm(check_id="m1-9", confirmed=True)
        except RuntimeError as exc:
            assert "ตรวจ" in str(exc), str(exc)
        else:
            assert outcome == {'CANCELLED'}, outcome
        report, path = core.run_gate1(bpy.context, DATA, PACK, "Crate", export("Crate"))
        asset_gate._last.update(report=report, path=path, confirmed=set())
        assert bpy.ops.asset_gate.confirm(check_id="m1-9", confirmed=True) == {'FINISHED'}
        assert asset_gate._is_confirmed("m1-9", report["checks"]["m1-9"])
        assert "m1-9" in read_confirms()["confirms"]
        assert bpy.ops.asset_gate.confirm(check_id="m1-9", confirmed=False) == {'FINISHED'}
        assert not asset_gate._is_confirmed("m1-9", report["checks"]["m1-9"])
    finally:
        asset_gate._data_folder = original
        asset_gate.unregister()


@case("check from Edit Mode sees unsaved edit-mode changes")
def _():
    obj = build_clean()
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.new((4, 4, 4))
    bmesh.update_edit_mesh(obj.data)
    checks, _ = gate()
    bpy.ops.object.mode_set(mode='OBJECT')
    expect(checks, "m1-3", "fail")
    assert checks["m1-3"]["values"]["looseVerts"] == 1


# ---------------------------------------------------------------- fix buttons (SPEC §10)

def cfg():
    return core.load_config(DATA)


def fix_and_check(check_id, variant, checks, model="Crate"):
    """Fix must be offered for this result, apply it, then check again with a fresh FBX."""
    offered = [f.variant for f in fixes.available(check_id, checks[check_id])]
    assert variant in offered, f"{check_id}: {variant} not offered ({offered}) for {checks[check_id]}"
    fix = fixes.find(check_id, variant)
    lines = fixes.plan(bpy.context, cfg(), fix, checks[check_id], model, "")
    assert lines, "the confirmation dialog must say what will change"
    fixes.apply(bpy.context, cfg(), fix, checks[check_id], model, "")
    return gate(model)[0]


def save_textures(obj):
    """Give the generated test images real files, like a user's textures."""
    os.makedirs(FBX_DIR, exist_ok=True)
    for slot in obj.material_slots:
        for node in slot.material.node_tree.nodes:
            if node.type == 'TEX_IMAGE':
                path = os.path.join(FBX_DIR, f"{node.image.name}_{case_no}.png")
                node.image.filepath_raw = path
                node.image.file_format = 'PNG'
                node.image.save()


@case("fix m1-1: remove zero faces")
def _():
    obj = build_clean()
    edit(obj, lambda bm: setattr(list(bm.faces)[0].verts[0], "co", list(bm.faces)[0].verts[1].co.copy()))
    checks = fix_and_check("m1-1", "dissolve", gate()[0])
    assert checks["m1-1"]["values"]["zeroFaces"] == 0 and checks["m1-1"]["values"]["zeroEdges"] == 0, checks["m1-1"]


@case("fix m1-1: fill a hole (risky)")
def _():
    obj = build_clean()
    edit(obj, lambda bm: bmesh.ops.delete(bm, geom=[list(bm.faces)[0]], context='FACES'))
    assert fixes.find("m1-1", "fillHoles").level == fixes.RISKY
    checks = fix_and_check("m1-1", "fillHoles", gate()[0])
    expect(checks, "m1-1", "pass")


@case("fix m1-3: merge doubles and delete loose geometry")
def _():
    obj = build_clean()
    edit(obj, lambda bm: (bmesh.ops.split_edges(bm, edges=bm.edges), bm.verts.new((3, 3, 3))))
    expect(fix_and_check("m1-3", "mergeLoose", gate()[0]), "m1-3", "pass")


@case("fix m1-4: recalculate normals")
def _():
    obj = build_clean()
    edit(obj, lambda bm: bmesh.ops.reverse_faces(bm, faces=list(bm.faces)[:2]))
    expect(fix_and_check("m1-4", "normals", gate()[0]), "m1-4", "pass")


@case("fix m1-5: apply transforms, geometry stays where it was")
def _():
    obj = build_clean()
    obj.scale = (2, 2, 2)
    obj.rotation_euler = (0, 0, 0.5)
    bpy.context.view_layer.update()
    before = sorted(tuple(round(c, 4) for c in obj.matrix_world @ v.co) for v in obj.data.vertices)
    checks = fix_and_check("m1-5", "applyTransform", gate()[0])
    expect(checks, "m1-5", "pass")
    after = sorted(tuple(round(c, 4) for c in obj.matrix_world @ v.co) for v in obj.data.vertices)
    assert before == after


@case("fix m1-6: triangulate (risky)")
def _():
    obj = build_clean()
    edit(obj, lambda bm: bmesh.ops.join_triangles(bm, faces=bm.faces, angle_face_threshold=3.2, angle_shape_threshold=3.2))
    expect(fix_and_check("m1-6", "triangulate", gate()[0]), "m1-6", "pass")


@case("fix m1-7: base centre to origin, transforms applied too")
def _():
    obj = build_clean()
    edit(obj, lambda bm: bmesh.ops.translate(bm, verts=bm.verts, vec=(0.3, 0, 0.25)))
    checks = fix_and_check("m1-7", "pivot", gate()[0])
    expect(checks, "m1-7", "pass")
    expect(checks, "m1-5", "pass")


@case("fix m1-8: rename to the rule, texture role words kept")
def _():
    reset_data()
    obj = build_clean()
    obj.name = "Crate.001"
    obj.data.name = "Mesh_0"
    obj.data.materials[0].name = "material"
    obj.data.materials[0].node_tree.nodes["Image Texture"].image.name = "crate_metallic_roughness.png"
    checks = fix_and_check("m1-8", "rename", gate()[0])
    expect(checks, "m1-8", "pass")
    assert obj.name == "Crate", obj.name
    assert obj.data.name == "Crate_Mesh", obj.data.name
    assert obj.data.materials[0].name == "Crate_Material", obj.data.materials[0].name
    assert obj.data.materials[0].node_tree.nodes["Image Texture"].image.name == "Crate_metallic_roughness"


@case("fix m1-10: create missing UVs (risky)")
def _():
    obj = build_clean()
    obj.data.uv_layers.remove(obj.data.uv_layers.active)
    obj.data.update_tag()
    checks = fix_and_check("m1-10", "smartUv", gate()[0])
    assert checks["m1-10"]["status"] != "fail" or "missingUv" not in checks["m1-10"]["values"], checks["m1-10"]
    assert obj.data.uv_layers


@case("fix m1-11: textures resized as new files, originals untouched")
def _():
    reset_data()
    obj = build_clean(tex=1024)
    save_textures(obj)
    image = obj.data.materials[0].node_tree.nodes["Image Texture"].image
    original = bpy.path.abspath(image.filepath)
    stamp = (os.path.getsize(original), os.path.getmtime(original))
    own = gate()[0]["m1-11"]["values"]["pxPerMeter"]
    write_peer("Barrel", own / 2)          # pack median is half -> 512 px
    checks, _ = gate()
    expect(checks, "m1-11", "review")
    lines = fixes.plan(bpy.context, cfg(), fixes.find("m1-11", "texel"), checks["m1-11"], "Crate", "")
    assert any("1024×1024 → 512×512" in line for line in lines), lines
    checks = fix_and_check("m1-11", "texel", checks)
    expect(checks, "m1-11", "pass")
    new = obj.data.materials[0].node_tree.nodes["Image Texture"].image
    assert tuple(new.size) == (512, 512) and new != image
    assert os.path.isfile(bpy.path.abspath(new.filepath)) and bpy.path.abspath(new.filepath) != original
    assert (os.path.getsize(original), os.path.getmtime(original)) == stamp, "original file must not change"
    reset_data()


@case("fix m1-12: packed texture keeps its pixels (regression: blank images on ARROW)")
def _():
    import numpy as np
    obj = build_clean(tex=1000)
    image = obj.data.materials[0].node_tree.nodes["Image Texture"].image
    w, h = image.size
    xs = np.tile(np.linspace(0, 1, w, dtype=np.float32), h)
    ys = np.repeat(np.linspace(0, 1, h, dtype=np.float32), w)
    image.pixels.foreach_set(np.stack([xs, ys, 1 - xs, np.ones_like(xs)], axis=1).ravel())
    image.pack()
    os.makedirs(WORK, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(WORK, f"packed_{case_no}.blend"))
    image.buffers_free()                      # like a freshly opened file: pixels not loaded yet
    checks = fix_and_check("m1-12", "textureSize", gate()[0])
    expect(checks, "m1-12", "pass")
    new = obj.data.materials[0].node_tree.nodes["Image Texture"].image
    reloaded = bpy.data.images.load(bpy.path.abspath(new.filepath))
    px = np.empty(1024 * 1024 * 4, dtype=np.float32)
    reloaded.pixels.foreach_get(px)
    px = px.reshape(-1, 4)
    assert px[:, 0].std() > 0.2 and px[:, 1].std() > 0.2, "resized texture is blank"
    assert abs(px[:, 0].mean() - 0.5) < 0.05 and abs(px[:, 2].mean() - 0.5) < 0.05, px.mean(axis=0)


def texel_fix(obj):
    checks = gate()[0]
    expect(checks, "m1-11", "review")
    fix = fixes.find("m1-11", "texel")
    changes, _ = fixes.texture_plan(bpy.context, cfg(), "m1-11", checks["m1-11"])
    fixes.plan(bpy.context, cfg(), fix, checks["m1-11"], "Crate", "")
    fixes.apply(bpy.context, cfg(), fix, checks["m1-11"], "Crate", "")
    return changes, obj.data.materials[0].node_tree.nodes["Image Texture"].image


def pngs():
    return sorted(f for f in os.listdir(FBX_DIR) if f.endswith(".png"))


@case("texture fix: back to the original without a new file, earlier file reused, original kept")
def _():
    reset_data()
    obj = build_clean(tex=1024)
    original = obj.data.materials[0].node_tree.nodes["Image Texture"].image
    original.name = f"Crate_Tex{case_no}"     # own file names, not shared with earlier cases
    save_textures(obj)
    own = gate()[0]["m1-11"]["values"]["pxPerMeter"]
    write_peer("Barrel", own / 2)
    changes, small = texel_fix(obj)
    assert changes[0].action == "new" and tuple(small.size) == (512, 512)
    assert original.use_fake_user, "the original must survive a save even with no users"
    files = pngs()

    # like Ctrl+Z: material back on the original, the generated datablock gone, its file still there
    obj.data.materials[0].node_tree.nodes["Image Texture"].image = original
    bpy.data.images.remove(small)
    changes, again = texel_fix(obj)
    assert changes[0].action == "reuse", changes[0].action
    assert pngs() == files, "no new file when the same size was made before"

    # the pack median moves back up: the fix switches to the original, still no new file
    write_peer("Barrel", own)
    changes, back = texel_fix(obj)
    assert changes[0].action == "original" and back == original, (changes[0].action, back.name)
    assert pngs() == files
    reset_data()


@case("texture fix: never scales up past the original")
def _():
    reset_data()
    obj = build_clean(tex=1024)
    save_textures(obj)
    own = gate()[0]["m1-11"]["values"]["pxPerMeter"]
    write_peer("Barrel", own * 2)
    checks = gate()[0]
    expect(checks, "m1-11", "review")
    try:
        fixes.plan(bpy.context, cfg(), fixes.find("m1-11", "texel"), checks["m1-11"], "Crate", "")
    except core.GateError as exc:
        assert "ไม่ขยาย" in str(exc), str(exc)
    else:
        raise AssertionError("expected GateError")
    reset_data()


@case("m1-12 review (size differs from the pack): confirm only, no resize button")
def _():
    reset_data()
    build_clean(tex=1024)
    write_peer("Barrel", 500, tex=2048)
    checks = gate()[0]
    expect(checks, "m1-12", "review")
    assert not fixes.available("m1-12", checks["m1-12"])
    reset_data()


@case("after Undo/Redo the panel result is stale: Fix and Confirm refuse until Check")
def _():
    reset_data()
    asset_gate.register()
    original = asset_gate._data_folder
    asset_gate._data_folder = lambda _context: DATA
    try:
        assert asset_gate._mark_stale in bpy.app.handlers.undo_post
        obj = two_materials()
        edit(obj, lambda bm: bmesh.ops.reverse_faces(bm, faces=list(bm.faces)[:2]))
        bpy.context.scene.asset_gate.pack, bpy.context.scene.asset_gate.model = PACK, "Crate"
        assert bpy.ops.asset_gate.check() == {'FINISHED'}
        asset_gate._mark_stale()
        for call in (lambda: bpy.ops.asset_gate.confirm(check_id="m1-9", confirmed=True),
                     lambda: bpy.ops.asset_gate.fix('EXEC_DEFAULT', check_id="m1-4", variant="normals")):
            try:
                outcome = call()
            except RuntimeError as exc:
                assert "Undo" in str(exc), str(exc)
            else:
                assert outcome == {'CANCELLED'}, outcome
        assert bpy.ops.asset_gate.check() == {'FINISHED'} and not asset_gate._last["stale"]
        assert bpy.ops.asset_gate.confirm(check_id="m1-9", confirmed=True) == {'FINISHED'}
    finally:
        asset_gate._data_folder = original
        asset_gate.unregister()
    assert asset_gate._mark_stale not in bpy.app.handlers.undo_post


@case("fix m1-12: non power-of-two texture to an allowed size")
def _():
    obj = build_clean(tex=1000)
    save_textures(obj)
    checks = fix_and_check("m1-12", "textureSize", gate()[0])
    expect(checks, "m1-12", "pass")
    assert tuple(obj.data.materials[0].node_tree.nodes["Image Texture"].image.size) == (1024, 1024)


@case("fix m1-12: unsaved image needs a saved .blend first")
def _():
    build_clean(tex=1000)
    checks = gate()[0]
    try:
        fixes.plan(bpy.context, cfg(), fixes.find("m1-12", "textureSize"), checks["m1-12"], "Crate", "")
        fixes.apply(bpy.context, cfg(), fixes.find("m1-12", "textureSize"), checks["m1-12"], "Crate", "")
    except core.GateError as exc:
        assert ".blend" in str(exc), str(exc)
    else:
        raise AssertionError("expected GateError")


@case("fix m1-14: export the FBX again")
def _():
    build_clean()
    fbx = export("Crate", axis_forward='Y', axis_up='Z')
    checks = gate(fbx=fbx)[0]
    expect(checks, "m1-14", "fail")
    fix = fixes.find("m1-14", "reexport")
    fixes.apply(bpy.context, cfg(), fix, checks["m1-14"], "Crate", fbx)
    expect(gate(fbx=fbx)[0], "m1-14", "pass")


@case("fix: no button where only a person can fix it; hints instead")
def _():
    for check_id in ("m1-2", "m1-9", "m1-15"):
        assert not fixes.available(check_id, {"status": "fail", "values": {"x": 1}}) and check_id in fixes.HINTS
    for fix in fixes.FIXES:
        assert i18n.STRINGS[f"fix.{fix.variant}"]


@case("fix operator: applies, then checks again (EXEC, no dialog)")
def _():
    reset_data()
    asset_gate.register()
    original = asset_gate._data_folder
    asset_gate._data_folder = lambda _context: DATA
    try:
        obj = build_clean()
        edit(obj, lambda bm: bmesh.ops.reverse_faces(bm, faces=list(bm.faces)[:2]))
        bpy.context.scene.asset_gate.pack, bpy.context.scene.asset_gate.model = PACK, "Crate"
        assert bpy.ops.asset_gate.check() == {'FINISHED'}
        expect(asset_gate._last["report"]["checks"], "m1-4", "fail")
        assert bpy.ops.asset_gate.fix('EXEC_DEFAULT', check_id="m1-4", variant="normals") == {'FINISHED'}
        expect(asset_gate._last["report"]["checks"], "m1-4", "pass")
    finally:
        asset_gate._data_folder = original
        asset_gate.unregister()


@case("confirm right after a Check without FBX (SPEC D14), kept through Export-style check")
def _():
    reset_data()
    asset_gate.register()
    original = asset_gate._data_folder
    asset_gate._data_folder = lambda _context: DATA
    try:
        two_materials()
        bpy.context.scene.asset_gate.pack, bpy.context.scene.asset_gate.model = PACK, "Crate"
        bpy.context.scene.asset_gate.fbx_path = ""
        assert bpy.ops.asset_gate.check() == {'FINISHED'}
        assert asset_gate._last["path"] is None
        assert bpy.ops.asset_gate.confirm(check_id="m1-9", confirmed=True) == {'FINISHED'}
        report, _ = core.run_gate1(bpy.context, DATA, PACK, "Crate", export("Crate"))
        assert core.valid_confirms(report, core.load_confirms(DATA, PACK, "Crate")) == {"m1-9"}
    finally:
        asset_gate._data_folder = original
        asset_gate.unregister()


# ---------------------------------------------------------------- M7: data folder, m1-13

@case("data folder: set one wins, else <Unity project>/AssetGate, else none")
def _():
    project = os.path.join(WORK, "UnityProject")
    os.makedirs(os.path.join(project, "ProjectSettings"), exist_ok=True)
    with open(os.path.join(project, "ProjectSettings", "ProjectVersion.txt"), "w") as f:
        f.write("m_EditorVersion: 6000.3.22f1\n")
    assert core.resolve_data_folder(DATA, project) == DATA
    auto = core.resolve_data_folder("", project)
    assert auto == os.path.join(project, "AssetGate") and os.path.isdir(auto)
    assert core.resolve_data_folder("", os.path.join(WORK, "not-unity")) == ""
    assert core.resolve_data_folder("", "") == ""


@case("m1-13: review with the texture names, n/a without textures")
def _():
    obj = build_clean()
    expect(gate()[0], "m1-13", "review")
    nodes = obj.data.materials[0].node_tree.nodes
    nodes.remove(next(n for n in nodes if n.type == 'TEX_IMAGE'))
    expect(gate()[0], "m1-13", "na")


# ---------------------------------------------------------------- m1-16 polygon count (SPEC D22)

@case("m1-16: counts like Meshy (faces, tris, vertices, edges, topology)")
def _():
    reset_data()
    obj = build_clean()
    c = gate()[0]["m1-16"]
    expect({"m1-16": c}, "m1-16", "review")
    v = c["values"]
    assert (v["faces"], v["tris"], v["verts"], v["edges"], v["topology"]) == (12, 12, 8, 18, "triangles"), v
    assert v["tier"] == "low" and v["fits"] == [] and "น้อยกว่าทุกช่วง" in c["detail"], c
    edit(obj, lambda bm: bmesh.ops.join_triangles(bm, faces=bm.faces, angle_face_threshold=3.2, angle_shape_threshold=3.2))
    v = gate()[0]["m1-16"]["values"]
    assert (v["faces"], v["tris"], v["topology"]) == (6, 12, "quads"), v


@case("m1-16: advice tiers and ranges from config")
def _():
    from asset_gate import mesh_checks
    cfg_ = core.load_config(DATA)
    advice = mesh_checks.polycount_advice
    assert advice(cfg_, 496)["tier"] == "low"
    assert advice(cfg_, 1606)["tier"] == "mid"
    assert advice(cfg_, 50000)["tier"] == "high"
    assert advice(cfg_, 250000)["tier"] == "veryHigh" and advice(cfg_, 250000)["fits"] == []
    assert "mediumProp:mobile" in advice(cfg_, 1606)["fits"] and "smallProp:pc" not in advice(cfg_, 1606)["fits"]
    a = advice(cfg_, 1606, "mediumProp", "pc")
    assert (a["range"], a["fit"]) == ([1000, 6000], "within"), a
    assert advice(cfg_, 1606, "smallProp", "mobile")["fit"] == "above"
    assert advice(cfg_, 1606, "character", "pc")["fit"] == "below"
    assert advice(cfg_, 1606, "heroProp", "mobile")["fit"] == "below"
    assert advice(cfg_, 496, "npc", "pc")["range"] == [3500, 16500]
    assert advice(cfg_, 20000, "vehicle", "pc")["fit"] == "within"
    assert advice(cfg_, 6000, "foliage", "pc")["fit"] == "within"
    import copy
    gap = copy.deepcopy(cfg_)
    del gap["polycount"]["byType"]["heroProp"]["mobile"]
    assert advice(gap, 1606, "heroProp", "mobile")["fit"] == "none", "a range removed from config -> no guidance"
    assert advice(cfg_, 1606, "mediumProp", "vr")["range"] == [300, 2000], "VR uses the mobile ranges"


@case("m1-16: type/platform from the panel; confirmation resets when they change")
def _():
    reset_data()
    asset_gate.register()
    try:
        build_clean()
        s = bpy.context.scene.asset_gate
        s.asset_type, s.platform = "smallProp", "vr"
        report, _ = core.run_gate1(bpy.context, DATA, PACK, "Crate", export("Crate"))
        c = report["checks"]["m1-16"]
        assert c["values"]["fit"] == "below" and "Quest" in c["detail"], c
        core.set_confirm(DATA, report, "m1-16", True)
        report, _ = core.run_gate1(bpy.context, DATA, PACK, "Crate", export("Crate"))
        assert "m1-16" in core.valid_confirms(report, core.load_confirms(DATA, PACK, "Crate"))
        s.asset_type = "character"
        report, _ = core.run_gate1(bpy.context, DATA, PACK, "Crate", export("Crate"))
        assert "m1-16" not in core.valid_confirms(report, core.load_confirms(DATA, PACK, "Crate")), "type changed"
    finally:
        asset_gate.unregister()


@case("config: an older config.json without polycount still works (default fills it in memory)")
def _():
    reset_data()
    path = os.path.join(DATA, "config.json")
    with open(core.default_config_path(), encoding="utf-8") as f:
        old = json.load(f)
    del old["polycount"]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(old, f)
    build_clean()
    assert gate()[0]["m1-16"]["status"] == "review"
    with open(path, encoding="utf-8") as f:
        assert "polycount" not in json.load(f), "the user's config.json is not rewritten"
    reset_data()


@case("language switch: the shown results are checked again in the new language")
def _():
    reset_data()
    asset_gate.register()
    original = asset_gate._data_folder
    asset_gate._data_folder = lambda _context: DATA
    try:
        build_clean()
        bpy.context.scene.asset_gate.pack, bpy.context.scene.asset_gate.model = PACK, "Crate"
        i18n.LANG = "en"
        assert bpy.ops.asset_gate.check() == {'FINISHED'}
        assert "tris" in asset_gate._last["report"]["checks"]["m1-16"]["detail"]
        i18n.LANG = "th"                        # what the language setting's update does, then its timer:
        asset_gate._recheck_in_new_language()
        detail = asset_gate._last["report"]["checks"]["m1-16"]["detail"]
        assert "สามเหลี่ยม" in detail and asset_gate._last["lang"] == "th", detail
    finally:
        i18n.LANG = "th"
        asset_gate._data_folder = original
        asset_gate.unregister()


@case("config: an older config.json with only unity.editorVersion gets minEditorVersion from the default")
def _():
    reset_data()
    with open(core.default_config_path(), encoding="utf-8") as f:
        old = json.load(f)
    del old["unity"]["minEditorVersion"]
    old["unity"]["editorVersion"] = "6000.3.22f1"
    with open(os.path.join(DATA, "config.json"), "w", encoding="utf-8") as f:
        json.dump(old, f)
    assert core.load_config(DATA)["unity"]["minEditorVersion"] == "6000.0"
    reset_data()


# ---------------------------------------------------------------- errors and UI

def expect_gate_error(contains, *args):
    try:
        core.run_gate1(bpy.context, *args)
    except core.GateError as exc:
        assert contains in str(exc), str(exc)
    else:
        raise AssertionError("expected GateError")


@case("GateError: bad inputs produce no report")
def _():
    reset_data()
    build_clean()
    expect_gate_error("โฟลเดอร์ข้อมูล", os.path.join(WORK, "missing"), PACK, "Crate", "")
    expect_gate_error("ชื่อแพ็ก", DATA, "", "Crate", "")
    expect_gate_error("อักขระ", DATA, PACK, "Cra/te", "")
    expect_gate_error("ไม่พบไฟล์ FBX", DATA, PACK, "Crate", os.path.join(WORK, "nope.fbx"))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    expect_gate_error("ไม่มีโมเดล", DATA, PACK, "Crate", "")
    assert not os.path.exists(os.path.join(DATA, "reports"))


@case("GateError: config missing a threshold")
def _():
    reset_data()
    build_clean()
    with open(core.default_config_path(), encoding="utf-8") as f:
        cfg = json.load(f)
    del cfg["mesh"]["mergeDistance"]
    with open(os.path.join(DATA, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    expect_gate_error("mesh.mergeDistance", DATA, PACK, "Crate", "")
    reset_data()


@case("add-on registers, operator runs, unregisters")
def _():
    reset_data()
    asset_gate.register()
    try:
        build_clean()
        assert hasattr(bpy.context.scene, "asset_gate")
        assert hasattr(bpy.types, "ASSETGATE_PT_panel")
        bpy.context.scene.asset_gate.pack = PACK
        # Not installed as an add-on here, so there are no preferences: the operator must refuse cleanly.
        try:
            outcome = bpy.ops.asset_gate.check()
        except RuntimeError as exc:
            assert "โฟลเดอร์ข้อมูล" in str(exc), str(exc)
        else:
            assert outcome == {'CANCELLED'}, outcome
    finally:
        asset_gate.unregister()
    assert not hasattr(bpy.types.Scene, "asset_gate")


# ---------------------------------------------------------------- export to unity

from asset_gate import unity_export  # noqa: E402

UNITY = os.path.join(WORK, "UnityProject")


def fake_unity(version=None, is_open=True):
    import shutil
    shutil.rmtree(UNITY, ignore_errors=True)
    version = version or "6000.3.22f1"
    os.makedirs(os.path.join(UNITY, "ProjectSettings"))
    os.makedirs(os.path.join(UNITY, "Assets"))
    with open(os.path.join(UNITY, "ProjectSettings", "ProjectVersion.txt"), "w", encoding="utf-8") as f:
        f.write(f"m_EditorVersion: {version}\nm_EditorVersionWithRevision: {version} (abc)\n")
    if is_open:
        os.makedirs(os.path.join(UNITY, "Temp"))
        open(os.path.join(UNITY, "Temp", "UnityLockfile"), "w").close()


def unity_files():
    found = []
    for folder, _, files in os.walk(os.path.join(UNITY, "Assets")):
        found += [os.path.relpath(os.path.join(folder, f), UNITY).replace("\\", "/") for f in files]
    return sorted(found)


def send(model="Crate", **kwargs):
    return unity_export.export_to_unity(bpy.context, DATA, UNITY, PACK, model, **kwargs)


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@case("export: clean model is delivered with textures and a passing report")
def _():
    reset_data()
    fake_unity()
    build_clean()
    images_before = len(bpy.data.images)
    report, path, delivered = send()
    assert unity_files() == ["Assets/Test Pack/Meshes/Crate.fbx", "Assets/Test Pack/Textures/Crate_BaseColor.png"], unity_files()
    assert len(delivered) == 2 and path and os.path.exists(path)
    fbx = os.path.join(UNITY, "Assets", PACK, "Meshes", "Crate.fbx")
    assert report["source"]["fbxPath"] == fbx, report["source"]
    assert report["source"]["fbxSha256"] == core.sha256(fbx), "report hash must match the delivered file"
    expect(report["checks"], "m1-14", "pass")
    with open(os.path.join(UNITY, "Assets", PACK, "Textures", "Crate_BaseColor.png"), "rb") as f:
        assert f.read(8) == PNG_SIGNATURE
    assert len(bpy.data.images) == images_before, "temporary image copy must be removed"


@case("export: metallic-roughness is delivered converted (URP metallic-smoothness), pixel-exact")
def _():
    import numpy as np
    reset_data()
    fake_unity()
    obj = build_clean()
    mr = bpy.data.images.new("Crate_metallic_roughness", 1024, 1024, alpha=True)
    mr.colorspace_settings.name = 'Non-Color'
    rng = np.random.default_rng(7)
    src = (rng.integers(0, 256, size=(1024 * 1024, 4)) / 255.0).astype(np.float32)
    mr.pixels.foreach_set(src.ravel())
    mr.pack()                                   # Meshy imports usually come packed
    node = obj.data.materials[0].node_tree.nodes.new("ShaderNodeTexImage")
    node.image = mr
    report, path, delivered = send()
    textures = os.path.join(UNITY, "Assets", PACK, "Textures")
    assert unity_files() == ["Assets/Test Pack/Meshes/Crate.fbx", "Assets/Test Pack/Textures/Crate_BaseColor.png",
                             "Assets/Test Pack/Textures/Crate_metallic_roughness_MetallicSmoothness.png"], unity_files()
    assert report["checks"]["m1-9"]["values"]["textures"]["Crate"] == ["Crate_BaseColor", "Crate_metallic_roughness"], \
        "the report keeps the Blender image names; Unity finds the converted file from them"
    out = bpy.data.images.load(os.path.join(textures, "Crate_metallic_roughness_MetallicSmoothness.png"))
    out.colorspace_settings.name = 'Non-Color'
    got = np.empty(1024 * 1024 * 4, dtype=np.float32)
    out.pixels.foreach_get(got)
    got = np.rint(got.reshape(-1, 4) * 255).astype(int)
    want = np.rint(src * 255).astype(int)
    # Unity's ModelSetup.ConvertMetallicRoughness: R = source B, G = B = 0, A = 255 - source G
    assert (got[:, 0] == want[:, 2]).all(), "R must be the metallic (blue) channel"
    assert (got[:, 1] == 0).all() and (got[:, 2] == 0).all()
    assert (got[:, 3] == 255 - want[:, 1]).all(), "A must be 255 - roughness (green)"
    assert "Crate_metallic_roughness" in bpy.data.images and mr.packed_file, "the user's image stays as it was"


@case("export: packed JPEG texture is delivered as PNG with the same pixels (regression: SHOVEL)")
def _():
    import numpy as np
    reset_data()
    fake_unity()
    obj = build_clean()
    image = obj.data.materials[0].node_tree.nodes["Image Texture"].image
    rng = np.random.default_rng(3)
    image.pixels.foreach_set((rng.integers(0, 256, size=(1024 * 1024, 4)) / 255.0).astype(np.float32).ravel())
    os.makedirs(FBX_DIR, exist_ok=True)
    jpg = os.path.join(FBX_DIR, f"Crate_BaseColor_{case_no}.jpg")
    image.file_format = 'JPEG'                    # Blender writes in file_format, not by extension
    image.save(filepath=jpg, quality=80)
    with open(jpg, "rb") as f:
        assert f.read(2) == bytes([0xFF, 0xD8]), "test setup: the source must really be a JPEG"
    # Packed the way the glTF importer does it (Meshy GLB -> SHOVEL.blend): raw JPEG bytes, no file path
    with open(jpg, "rb") as f:
        data = f.read()
    packed = bpy.data.images.new("Crate_BaseColor_jpg", 1, 1)
    packed.pack(data=data, data_len=len(data))
    packed.source = 'FILE'
    packed.alpha_mode = 'CHANNEL_PACKED'
    obj.data.materials[0].node_tree.nodes["Image Texture"].image = packed
    bpy.data.images.remove(image)
    packed.name = "Crate_BaseColor"
    image = packed
    assert image.filepath == "" and image.packed_file and tuple(image.size) == (1024, 1024)
    decoded = np.empty(1024 * 1024 * 4, dtype=np.float32)
    image.pixels.foreach_get(decoded)
    image.buffers_free()                          # like a freshly opened .blend: pixels not loaded yet
    send()
    delivered = os.path.join(UNITY, "Assets", PACK, "Textures", "Crate_BaseColor.png")
    with open(delivered, "rb") as f:
        assert f.read(8) == PNG_SIGNATURE, "must be a real PNG, not re-compressed JPEG data named .png"
    out = bpy.data.images.load(delivered)
    out.colorspace_settings.name = image.colorspace_settings.name
    got = np.empty(1024 * 1024 * 4, dtype=np.float32)
    out.pixels.foreach_get(got)
    diff = np.abs(np.rint(got.reshape(-1, 4)[:, :3] * 255) - np.rint(decoded.reshape(-1, 4)[:, :3] * 255)).max()
    assert diff == 0, f"delivered PNG differs from the packed JPEG by up to {diff} levels"


@case("export: texture role words match Unity's rule")
def _():
    from asset_gate import unity_export
    cfg = core.load_config(DATA)
    role = lambda n: unity_export.texture_role(cfg, n)
    assert role("Shovel_metallic_roughness") == "metallicRoughness"
    assert role("Rock_ORM") == "metallicRoughness"
    assert role("Shovel_normal") == "normalMap", "orm inside normal must not match"
    assert role("Shovel_base_color") == "baseMap"
    assert role("Shovel_Detail") is None


@case("export: delivered FBX uses the configured export settings")
def _():
    reset_data()
    fake_unity()
    build_clean()
    report, _, _ = send()
    values = report["checks"]["m1-14"]["values"]
    assert (values["forward"], values["up"], values["embedded"]) == ("-Z", "Y", 0), values


@case("export: scene check fails -> nothing delivered, no report")
def _():
    reset_data()
    fake_unity()
    obj = build_clean()
    edit(obj, lambda bm: bmesh.ops.join_triangles(
        bm, faces=bm.faces, angle_face_threshold=3.2, angle_shape_threshold=3.2))
    report, path, delivered = send()
    expect(report["checks"], "m1-6", "fail")
    assert path is None and delivered == [] and unity_files() == []
    assert not os.path.exists(os.path.join(DATA, "reports"))


@case("export: FBX-stage check fails -> nothing delivered, no report")
def _():
    reset_data()
    fake_unity()
    build_clean()
    bpy.context.scene.unit_settings.scale_length = 0.01
    report, path, delivered = send()
    expect(report["checks"], "m1-14", "fail", "Scene Unit")
    assert path is None and delivered == [] and unity_files() == []
    assert not os.path.exists(os.path.join(DATA, "reports"))


def expect_export_error(contains):
    try:
        send()
    except core.GateError as exc:
        assert contains in str(exc), str(exc)
    else:
        raise AssertionError("expected GateError")
    assert unity_files() == []


@case("export: refused when Unity is not open / wrong version / not a project")
def _():
    reset_data()
    build_clean()
    fake_unity(is_open=False)
    expect_export_error("ยังไม่ได้เปิด")
    fake_unity(version="2022.3.10f1")
    expect_export_error("ต้องเป็น 6000.0 ขึ้นไป")
    for accepted in ("6000.0.35f1", "6000.3.22f1", "6000.5.0f1"):   # SPEC D24: minimum, not an exact lock
        fake_unity(version=accepted)
        assert unity_export.check_unity(UNITY, core.load_config(DATA)) == accepted
    import shutil
    shutil.rmtree(os.path.join(UNITY, "ProjectSettings"))
    expect_export_error("ไม่ใช่โปรเจกต์ Unity")


@case("export: existing files need confirmation; overwrite keeps .meta")
def _():
    reset_data()
    fake_unity()
    build_clean()
    send()
    fbx = os.path.join(UNITY, "Assets", PACK, "Meshes", "Crate.fbx")
    with open(fbx + ".meta", "w") as f:
        f.write("guid: keepme")
    with open(fbx, "wb") as f:
        f.write(b"old")
    try:
        send()
    except unity_export.ExistingFiles as exc:
        assert len(exc.files) == 2, exc.files
    else:
        raise AssertionError("expected ExistingFiles")
    with open(fbx, "rb") as f:
        assert f.read() == b"old", "file must be untouched without confirmation"
    send(overwrite=True)
    assert os.path.getsize(fbx) > 1000
    with open(fbx + ".meta") as f:
        assert f.read() == "guid: keepme"


@case("export: packed PNG is written byte-for-byte")
def _():
    reset_data()
    fake_unity()
    obj = build_clean()
    image = obj.data.materials[0].node_tree.nodes["Image Texture"].image
    os.makedirs(FBX_DIR, exist_ok=True)
    source = os.path.join(FBX_DIR, "packed_source.png")
    image.filepath_raw = source
    image.file_format = 'PNG'
    image.save()
    image.source = 'FILE'
    image.pack()
    image.filepath = ""
    with open(source, "rb") as f:
        original = f.read()
    send()
    with open(os.path.join(UNITY, "Assets", PACK, "Textures", "Crate_BaseColor.png"), "rb") as f:
        assert f.read() == original


# Leave one clean report behind for schema validation.
reset_data()
build_clean()
gate()

failed = [(name, err) for name, err in results if err]
for name, err in results:
    print(("FAIL " if err else "OK   ") + name)
for name, err in failed:
    print(f"\n--- {name}\n{err}")
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
sys.exit(1 if failed else 0)
