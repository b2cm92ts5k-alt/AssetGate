"""Gate 1 FBX check (m1-14): the exported file against config and against the open scene."""
import json
import os
import subprocess
import tempfile

import bpy

from .i18n import tr
from .mesh_checks import FLOAT_EPS, result

# Relative numeric tolerance when comparing sizes that went through an export/import round trip.
SIZE_REL_EPS = 1e-3
PROBE_TIMEOUT = 300


def probe(fbx_path):
    script = os.path.join(os.path.dirname(__file__), "fbx_probe.py")
    with tempfile.TemporaryDirectory() as tmp:
        out_path = os.path.join(tmp, "probe.json")
        proc = subprocess.run(
            [bpy.app.binary_path, "-b", "--factory-startup", "--python", script, "--", fbx_path, out_path],
            capture_output=True, timeout=PROBE_TIMEOUT)
        if not os.path.exists(out_path):
            tail = proc.stdout.decode("utf-8", "replace").strip().splitlines()[-1:]
            return {"error": tr("fbx.probeFailed", tail=" ".join(tail))}
        with open(out_path, encoding="utf-8") as f:
            return json.load(f)


def check_fbx(data, cfg, fbx_path):
    info = probe(fbx_path)
    if "error" in info:
        return result("fail", tr("fbx.unreadable", err=info["error"]))

    want = cfg["fbx"]
    problems = []

    unit = data.scene.unit_settings
    if unit.system != 'METRIC' or abs(unit.scale_length - want["unitScale"]) > FLOAT_EPS:
        problems.append(tr("fbx.unit", system=unit.system, scale=unit.scale_length, want=want["unitScale"]))

    if info["forward"] != want["forward"] or info["up"] != want["up"]:
        problems.append(tr("fbx.axis", forward=info["forward"], up=info["up"], wf=want["forward"], wu=want["up"]))

    unapplied = [m["name"] for m in info["models"]
                 if any(abs(v) > FLOAT_EPS for v in m["rotation"])
                 or any(abs(v - 1) > FLOAT_EPS for v in m["scale"])]
    if unapplied:
        problems.append(tr("fbx.transform", names=", ".join(unapplied[:5])))

    if info["embedded"] and not want["embedTextures"]:
        problems.append(tr("fbx.embedded", n=len(info["embedded"])))

    scene_names = sorted(o.name for o in data.objects)
    if info["meshObjects"] != scene_names:
        problems.append(tr("fbx.objects", fbx=info["meshObjects"], scene=scene_names))
    if info["tris"] != data.tris:
        problems.append(tr("fbx.tris", fbx=info["tris"], scene=data.tris))

    lo, hi = data.bounds()
    scene_size = [hi[i] - lo[i] for i in range(3)]
    scale = max(scene_size) or 1.0
    if any(abs(a - b) > scale * SIZE_REL_EPS for a, b in zip(info["size"], scene_size)):
        problems.append(tr("fbx.size", fbx=[round(v, 4) for v in info["size"]], scene=[round(v, 4) for v in scene_size]))

    values = {
        "forward": info["forward"], "up": info["up"], "unitScaleFactor": info["unitScaleFactor"],
        "embedded": len(info["embedded"]), "tris": info["tris"], "objects": info["meshObjects"],
        "size": [round(v, 4) for v in info["size"]],
    }
    if problems:
        return result("fail", " · ".join(problems), **values)
    return result("pass", **values)
