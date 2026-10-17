"""Export to Unity: run Gate 1 on a staged export and deliver it to the Unity project only if it passes.

Writes nothing but this model's FBX and textures, inside Assets/<Pack>/, and only on the user's click.
"""
import os
import shutil
import tempfile

import bpy
import numpy as np

from . import core, mesh_checks
from .i18n import tr

REQUIRED_CONFIG = {
    "fbx": ("forward", "up", "embedTextures"),
    "unity": ("minEditorVersion", "export", "textureRoles"),
}
# Same suffix as Unity's Setup (GateContext.ConvertedPath), so both find the converted file.
CONVERTED_SUFFIX = "_MetallicSmoothness"


class ExistingFiles(core.GateError):
    """Delivery would overwrite files; the user has to confirm first."""

    def __init__(self, files):
        super().__init__(tr("err.exists", files=", ".join(os.path.basename(f) for f in files)))
        self.files = files


def _version_numbers(text):
    """"6000.3.22f1" -> (6000, 3, 22); "2022.3" -> (2022, 3)."""
    numbers = []
    for part in text.split("."):
        digits = ""
        for c in part:
            if not c.isdigit():
                break
            digits += c
        if not digits:
            break
        numbers.append(int(digits))
    return tuple(numbers)


def check_unity(project_path, cfg):
    """The project must be Unity minEditorVersion or newer (SPEC D24) and open in the editor. Returns its version."""
    version_file = os.path.join(project_path or "", "ProjectSettings", "ProjectVersion.txt")
    if not project_path or not os.path.isfile(version_file):
        raise core.GateError(tr("err.noUnityProject"))
    version = ""
    with open(version_file, encoding="utf-8") as f:
        for line in f:
            if line.startswith("m_EditorVersion:"):
                version = line.split(":", 1)[1].strip()
    want = cfg["unity"]["minEditorVersion"]
    have = _version_numbers(version)
    if not have or have < _version_numbers(want):
        raise core.GateError(tr("err.unityVersion", version=version or "?", want=want))
    if not os.path.exists(os.path.join(project_path, "Temp", "UnityLockfile")):
        raise core.GateError(tr("err.unityClosed"))
    return version


def _image_stem(image):
    name = image.name
    return name[:-4] if name.lower().endswith(".png") else name


def _image_file_name(image):
    return _image_stem(image) + ".png"


def texture_role(cfg, name):
    """Same rule as Unity's GateContext.RoleOf: unity.textureRoles patterns match whole
    "_"-separated words, case-insensitive (MEMORY #texture-role-words)."""
    words = "_" + name.lower().replace("-", "_").replace(" ", "_") + "_"
    roles = cfg["unity"]["textureRoles"]
    for role in ("metallicRoughness", "normalMap", "baseMap"):
        if any("_" + p.lower() + "_" in words for p in roles.get(role, [])):
            return role
    return None


def delivered_name(cfg, image):
    """File name in Unity. Metallic-roughness maps are delivered already converted to URP
    metallic-smoothness, so the unused original never enters the project (k3-7)."""
    stem = _image_stem(image)
    if texture_role(cfg, stem) == "metallicRoughness":
        return stem + CONVERTED_SUFFIX + ".png"
    return stem + ".png"


def targets(context, cfg, project_path, pack, model):
    """Destination paths: {"fbx": path, "textures": {image name: path}}."""
    folders = cfg["unity"]["export"]
    pack_dir = os.path.join(project_path, "Assets", pack)
    data = mesh_checks.SceneData(context)
    try:
        images = list(data.images)
    finally:
        data.free()
    texture_dir = os.path.join(pack_dir, folders["textureFolder"])
    return {
        "fbx": os.path.join(pack_dir, folders["meshFolder"], f"{model}.fbx"),
        "textures": {image.name: os.path.join(texture_dir, delivered_name(cfg, image)) for image in images},
    }


def existing(plan):
    return [p for p in [plan["fbx"], *plan["textures"].values()] if os.path.exists(p)]


def _export_fbx(path, cfg):
    fbx = cfg["fbx"]
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=False, object_types={'MESH'},
        axis_forward=fbx["forward"], axis_up=fbx["up"],
        bake_space_transform=True, embed_textures=fbx["embedTextures"])


def _write_png(image, path):
    if image.packed_file and image.file_format == 'PNG':
        with open(path, "wb") as f:
            f.write(image.packed_file.data)
        return
    source = bpy.path.abspath(image.filepath) if image.filepath else ""
    if source.lower().endswith(".png") and os.path.isfile(source):
        shutil.copyfile(source, path)
        return
    # Anything else is re-encoded from its pixels (image.copy() of a packed image has none,
    # MEMORY #packed-image-blank); the user's image datablock stays untouched.
    _save_pixels(_pixels(image), image.size, image.colorspace_settings.name, path)


def _pixels(image):
    pixels = np.empty(image.size[0] * image.size[1] * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    if not pixels.any():
        raise core.GateError(tr("fix.err.noPixels", name=image.name))
    return pixels


def _save_pixels(pixels, size, colorspace, path):
    temp = bpy.data.images.new("AssetGateExport", size[0], size[1], alpha=True)
    try:
        temp.colorspace_settings.name = colorspace
        temp.pixels.foreach_set(pixels)
        temp.filepath_raw = path
        temp.file_format = 'PNG'
        temp.save()
    finally:
        bpy.data.images.remove(temp)


def write_metallic_smoothness(image, path):
    """glTF / Meshy metallic-roughness (G = roughness, B = metallic) to URP metallic-smoothness
    (R = metallic, A = 1 - roughness), the same formula as Unity's ModelSetup.ConvertMetallicRoughness."""
    rgba = _pixels(image).reshape(-1, 4)
    out = np.zeros_like(rgba)
    out[:, 0] = rgba[:, 2]
    out[:, 3] = 1.0 - rgba[:, 1]
    _save_pixels(out.ravel(), image.size, 'Non-Color', path)


def export_to_unity(context, data_folder, project_path, pack, model, overwrite=False):
    """Returns (report, report_path, delivered_files). Nothing is delivered when Gate 1 fails."""
    if not data_folder or not os.path.isdir(data_folder):
        raise core.GateError(tr("err.noDataFolder"))
    cfg = core.load_config(data_folder)
    missing = [f"{section}.{key}" for section, keys in REQUIRED_CONFIG.items()
               for key in keys if key not in cfg.get(section, {})]
    if missing:
        raise core.GateError(tr("err.configMissing", keys=", ".join(missing)))
    check_unity(project_path, cfg)

    # Scene checks first: a model that fails them is never exported.
    report, _ = core.run_gate1(context, data_folder, pack, model)
    if not core.gate_passed(report, ignore=("m1-14",)):
        return report, None, []

    plan = targets(context, cfg, project_path, report["pack"], report["model"])
    clashes = existing(plan)
    if clashes and not overwrite:
        raise ExistingFiles(clashes)

    with tempfile.TemporaryDirectory() as staging:
        staged = os.path.join(staging, os.path.basename(plan["fbx"]))
        _export_fbx(staged, cfg)
        report, _ = core.run_gate1(context, data_folder, pack, model, staged,
                                   record_fbx_path=plan["fbx"], write=False)
        if not core.gate_passed(report):
            return report, None, []

        images = {image.name: image for image in bpy.data.images}
        delivered = []
        for name, path in plan["textures"].items():
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if path.endswith(CONVERTED_SUFFIX + ".png"):
                write_metallic_smoothness(images[name], path)
            else:
                _write_png(images[name], path)
            delivered.append(path)
        os.makedirs(os.path.dirname(plan["fbx"]), exist_ok=True)
        shutil.copyfile(staged, plan["fbx"])
        delivered.append(plan["fbx"])

    return report, core.write_report(data_folder, report), delivered
