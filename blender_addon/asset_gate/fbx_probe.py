"""Read an FBX file in a separate background Blender and dump what Gate 1 needs as JSON.

Run by fbx_check.py:  blender -b --factory-startup --python fbx_probe.py -- <file.fbx> <out.json>
Runs in its own process so the user's open .blend is never touched.
"""
import json
import sys

import bpy

AXES = "XYZ"


def _axis(index, sign, flip=False):
    if flip:
        sign = -sign
    return ("-" if sign < 0 else "") + AXES[index]


def _props70(elem):
    for child in elem.elems:
        if child.id == b"Properties70":
            return {p.props[0].decode(): p.props[4:] for p in child.elems}
    return {}


def read_raw(path):
    from io_scene_fbx import parse_fbx

    root, version = parse_fbx.parse(path)
    raw = {"version": version, "models": [], "embedded": []}
    for elem in root.elems:
        if elem.id == b"GlobalSettings":
            p = _props70(elem)
            raw["up"] = _axis(p["UpAxis"][0], p["UpAxisSign"][0])
            # FBX "front" points at the viewer, so forward is its opposite
            raw["forward"] = _axis(p["FrontAxis"][0], p["FrontAxisSign"][0], flip=True)
            raw["unitScaleFactor"] = p["UnitScaleFactor"][0]
        elif elem.id == b"Objects":
            for obj in elem.elems:
                name = obj.props[1].split(b"\x00")[0].decode("utf-8", "replace")
                if obj.id == b"Model":
                    p = _props70(obj)
                    raw["models"].append({
                        "name": name,
                        "type": obj.props[2].decode(),
                        "rotation": list(p.get("Lcl Rotation", (0.0, 0.0, 0.0))[:3]),
                        "scale": list(p.get("Lcl Scaling", (1.0, 1.0, 1.0))[:3]),
                    })
                elif obj.id == b"Video":
                    if any(c.id == b"Content" and len(c.props[0]) > 0 for c in obj.elems):
                        raw["embedded"].append(name)
    return raw


def read_imported(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path)
    bpy.context.view_layer.update()
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    coords = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    size = [max(c[i] for c in coords) - min(c[i] for c in coords) for i in range(3)] if coords else [0, 0, 0]
    return {
        "meshObjects": sorted(o.name for o in meshes),
        "tris": sum(len(p.vertices) - 2 for o in meshes for p in o.data.polygons),
        "size": size,
    }


def main():
    fbx_path, out_path = sys.argv[sys.argv.index("--") + 1:][:2]
    try:
        info = read_raw(fbx_path)
        info.update(read_imported(fbx_path))
    except Exception as exc:  # reported to the caller, which turns it into a failed check
        info = {"error": f"{type(exc).__name__}: {exc}"}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(info, f)


if __name__ == "__main__":
    main()
