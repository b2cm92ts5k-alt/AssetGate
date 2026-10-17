"""Gate 1 entry point: run every check, build the report, write it to the Data folder."""
import datetime
import glob
import hashlib
import json
import os
import shutil

import bpy

from . import fbx_check, mesh_checks
from .i18n import tr
from .mesh_checks import result

TOOL_VERSION = "1.0.0"
REPORT_SCHEMA = 1
FORBIDDEN_NAME_CHARS = '<>:"/\\|?*'
REQUIRED_CONFIG = {
    "mesh": ("mergeDistance", "degenerateThreshold"),
    "naming": ("pattern", "defaultNameBlocklist"),
    "material": ("maxWithoutReview",),
    "texture": ("allowedSizes",),
    "texelDensity": ("tolerancePercent",),
    "fbx": ("forward", "up", "unitScale", "embedTextures"),
}

# Shown in the panel in this order.
CHECK_IDS = ("m1-1", "m1-2", "m1-3", "m1-4", "m1-5", "m1-6", "m1-7", "m1-8", "m1-9", "m1-10",
             "m1-11", "m1-12", "m1-13", "m1-14", "m1-15", "m1-16")


def title(check_id):
    return tr("title." + check_id)

# Element indices of the last run, keyed by (check id, value key). Runtime only — never written to a report.
last_selection = {}


class GateError(Exception):
    """A problem the user has to fix before a check can run."""


# Data folder inside the Unity project when none is set (SPEC D18); outside Assets/ so Unity ignores it.
DATA_SUBFOLDER = "AssetGate"


def is_unity_project(path):
    return bool(path) and os.path.isfile(os.path.join(path, "ProjectSettings", "ProjectVersion.txt"))


def resolve_data_folder(override, unity_project):
    """The Data folder in use: the one set by the user, else <Unity project>/AssetGate (created on demand).
    Empty when neither is usable."""
    if override:
        return override
    if is_unity_project(unity_project):
        folder = os.path.join(unity_project, DATA_SUBFOLDER)
        os.makedirs(folder, exist_ok=True)
        return folder
    return ""


def default_config_path():
    here = os.path.dirname(__file__)
    for path in (os.path.join(here, "default.config.json"),  # packaged add-on
                 os.path.join(here, "..", "..", "config", "default.config.json")):  # repo checkout
        if os.path.exists(path):
            return path
    raise GateError(tr("err.noDefaultConfig"))


def load_config(data_folder):
    path = os.path.join(data_folder, "config.json")
    if not os.path.exists(path):
        shutil.copyfile(default_config_path(), path)
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except ValueError as exc:
        raise GateError(tr("err.configUnreadable", exc=exc))
    missing = [f"{section}.{key}" for section, keys in REQUIRED_CONFIG.items()
               for key in keys if key not in cfg.get(section, {})]
    if missing:
        raise GateError(tr("err.configMissing", keys=", ".join(missing)))
    # Sections added in later versions (e.g. polycount, SPEC D22) come from the default config when an
    # older config.json does not have them. Only in memory: the user's config.json is not changed.
    # Keys inside a section too (e.g. unity.minEditorVersion, SPEC D24).
    with open(default_config_path(), encoding="utf-8") as f:
        for section, value in json.load(f).items():
            if section not in cfg:
                cfg[section] = value
            elif isinstance(value, dict) and isinstance(cfg[section], dict):
                for key, inner in value.items():
                    cfg[section].setdefault(key, inner)
    return cfg


def _check_name(label, value):
    if not value.strip():
        raise GateError(tr("err.emptyName", label=label))
    if any(c in FORBIDDEN_NAME_CHARS for c in value):
        raise GateError(tr("err.badChars", label=label, chars=FORBIDDEN_NAME_CHARS))
    return value.strip()


def report_path(data_folder, pack, model):
    return os.path.join(data_folder, "reports", pack, f"{model}.blender.json")


def load_peers(data_folder, pack, model):
    """Gate 1 reports of the other models in the same pack."""
    peers = []
    own = os.path.normcase(report_path(data_folder, pack, model))
    for path in glob.glob(os.path.join(glob.escape(os.path.join(data_folder, "reports", pack)), "*.blender.json")):
        if os.path.normcase(path) == own:
            continue
        try:
            with open(path, encoding="utf-8") as f:
                peers.append(json.load(f))
        except (OSError, ValueError):
            continue
    return peers


def pack_budget(data_folder, pack):
    """Tris budget of the pack from state.json (owned by the web page); 0 when not set."""
    try:
        with open(os.path.join(data_folder, "state.json"), encoding="utf-8") as f:
            return int(json.load(f)["packs"][pack]["budget"] or 0)
    except (OSError, ValueError, KeyError, TypeError):
        return 0


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(checks, check_id, fn, *args):
    try:
        checks[check_id] = fn(*args)
    except Exception as exc:  # a check that crashed did not pass
        checks[check_id] = result("fail", tr("res.crashed", exc=f"{type(exc).__name__}: {exc}"))


def run_gate1(context, data_folder, pack, model, fbx_path="", record_fbx_path="", write=True):
    """Run Gate 1. Returns (report, written_path); written_path is None when nothing was written.

    record_fbx_path is stored in the report instead of fbx_path when the checked file is a
    staging copy of the one that will be delivered.
    """
    if not data_folder or not os.path.isdir(data_folder):
        raise GateError(tr("err.noDataFolder"))
    pack = _check_name(tr("label.pack"), pack)
    model = _check_name(tr("label.model"), model)
    fbx_path = bpy.path.abspath(fbx_path) if fbx_path else ""
    if fbx_path and not os.path.isfile(fbx_path):
        raise GateError(tr("err.fbxMissing", path=fbx_path))

    cfg = load_config(data_folder)
    peers = load_peers(data_folder, pack, model)
    data = mesh_checks.SceneData(context)
    if not data.objects:
        raise GateError(tr("err.noMesh"))
    if not any(len(bm.verts) for bm in data.meshes.values()):
        data.free()
        raise GateError(tr("err.emptyMesh"))

    checks = {}
    try:
        _run(checks, "m1-1", mesh_checks.check_integrity, data, cfg)
        _run(checks, "m1-2", mesh_checks.check_intersect, data, cfg)
        _run(checks, "m1-3", mesh_checks.check_merge_loose, data, cfg)
        _run(checks, "m1-4", mesh_checks.check_normals, data, cfg)
        _run(checks, "m1-5", mesh_checks.check_transforms, data, cfg)
        _run(checks, "m1-6", mesh_checks.check_triangulated, data, cfg)
        _run(checks, "m1-7", mesh_checks.check_pivot, data, cfg)
        _run(checks, "m1-8", mesh_checks.check_naming, data, cfg)
        _run(checks, "m1-9", mesh_checks.check_material_count, data, cfg)
        _run(checks, "m1-10", mesh_checks.check_uv, data, cfg)
        _run(checks, "m1-11", mesh_checks.check_texel_density, data, cfg, peers)
        _run(checks, "m1-12", mesh_checks.check_texture_size, data, cfg, peers)
        _run(checks, "m1-13", mesh_checks.check_baked_lighting, data, cfg)
        if fbx_path:
            _run(checks, "m1-14", fbx_check.check_fbx, data, cfg, fbx_path)
        else:
            checks["m1-14"] = result("pending", tr("res.noFbx"))
        _run(checks, "m1-15", mesh_checks.check_stats, data, cfg, pack_budget(data_folder, pack))
        settings = getattr(context.scene, "asset_gate", None)
        _run(checks, "m1-16", mesh_checks.check_polycount, data, cfg,
             getattr(settings, "asset_type", "none"), getattr(settings, "platform", "none"))
        stats = mesh_checks.model_stats(data)
        counts = data.counts
    finally:
        data.free()

    last_selection.clear()
    for check_id, check in checks.items():
        for key, sel in check.pop("_select", {}).items():
            sel["counts"] = {name: counts[name] for name in sel["objects"]}
            last_selection[(check_id, key)] = sel

    report = {
        "schema": REPORT_SCHEMA,
        "tool": "blender",
        "toolVersion": TOOL_VERSION,
        "scope": "model",
        "pack": pack,
        "model": model,
        "checkedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stats": stats,
        "checks": checks,
    }
    if not fbx_path:
        if write:
            prune_confirms(data_folder, report)
        return report, None

    report["source"] = {"fbxPath": record_fbx_path or fbx_path, "fbxSha256": sha256(fbx_path)}
    if bpy.data.filepath:
        report["source"]["blendPath"] = bpy.data.filepath
    if not write:
        return report, None
    path = write_report(data_folder, report)
    prune_confirms(data_folder, report)
    return report, path


def write_report(data_folder, report):
    path = report_path(data_folder, report["pack"], report["model"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


# ---- confirmations made in the panel (SPEC D11) --------------------------------------------
# reports/<Pack>/<Model>.blender.confirms.json, owned by the add-on like the report itself.
# A confirmation counts only while the check is still "review" with the values that were confirmed.

def confirms_path(data_folder, pack, model):
    return os.path.join(data_folder, "reports", pack, f"{model}.blender.confirms.json")


def _plain(values):
    """Values as they read back from JSON, so in-memory tuples and stored lists compare equal."""
    return json.loads(json.dumps(values))


def load_confirms(data_folder, pack, model):
    try:
        with open(confirms_path(data_folder, pack, model), encoding="utf-8") as f:
            confirms = json.load(f).get("confirms", {})
        return confirms if isinstance(confirms, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def valid_confirms(report, confirms):
    """Check ids whose confirmation still matches the report."""
    return {cid for cid, entry in confirms.items()
            if cid in report["checks"] and report["checks"][cid]["status"] == "review"
            and isinstance(entry, dict) and entry.get("values") == _plain(report["checks"][cid]["values"])}


def _write_confirms(data_folder, report, confirms):
    path = confirms_path(data_folder, report["pack"], report["model"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"schema": REPORT_SCHEMA, "tool": "blender", "scope": "model",
            "pack": report["pack"], "model": report["model"], "confirms": confirms}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def set_confirm(data_folder, report, check_id, confirmed):
    """Confirm (or undo) one review check of a written report. Returns the valid check ids."""
    confirms = load_confirms(data_folder, report["pack"], report["model"])
    keep = valid_confirms(report, confirms)
    confirms = {cid: confirms[cid] for cid in keep}
    if confirmed:
        check = report["checks"].get(check_id)
        if not check or check["status"] != "review":
            raise GateError(tr("conf.notReview"))
        confirms[check_id] = {
            "values": _plain(check["values"]),
            "confirmedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    else:
        confirms.pop(check_id, None)
    _write_confirms(data_folder, report, confirms)
    return set(confirms)


def prune_confirms(data_folder, report):
    """After a new check, drop confirmations whose result changed (they have to be confirmed again)."""
    confirms = load_confirms(data_folder, report["pack"], report["model"])
    keep = valid_confirms(report, confirms)
    if keep != set(confirms):
        _write_confirms(data_folder, report, {cid: confirms[cid] for cid in keep})
    return keep


def gate_passed(report, ignore=()):
    """True when every automatic check passed; review items still need a human in the web page."""
    return all(c["status"] in ("pass", "na", "review")
               for check_id, c in report["checks"].items() if check_id not in ignore)
