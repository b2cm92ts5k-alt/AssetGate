# Blender extension (4.2+): name, version and permissions are in blender_manifest.toml.

# Always reload the submodules: after a reinstall (or a failed enable) Python may still hold
# the previous version of them in sys.modules, and Blender only re-runs this file.
# Import first so submodules that are new in this version exist before the reload.
import importlib  # noqa: E402

from . import i18n, mesh_checks, fbx_check, core, unity_export, fixes  # noqa: E402

for _module in (i18n, mesh_checks, fbx_check, core, unity_export, fixes):
    importlib.reload(_module)

import os
import textwrap

import bmesh
import bpy

STATUS_ICONS = {
    "pass": 'CHECKMARK',
    "fail": 'CANCEL',
    "review": 'QUESTION',
    "na": 'REMOVE',
    "pending": 'TIME',
}
tr = i18n.tr
# Problem checks first, so what needs fixing is at the top of the panel.
STATUS_ORDER = ("fail", "review", "pending")

# Measurement rows shown under a check, like the Result list of 3D-Print Toolbox: (label key, value key).
# A row becomes a Select button when the check recorded element indices for that key.
ROWS = {
    "m1-1": [("row.nonManifold", "nonManifold"), ("row.badContiguous", "badContiguous"),
             ("row.zeroFaces", "zeroFaces"), ("row.zeroEdges", "zeroEdges")],
    "m1-2": [("row.intersectingFaces", "intersectingFaces")],
    "m1-3": [("row.doubles", "doubles"), ("row.looseVerts", "looseVerts"),
             ("row.looseEdges", "looseEdges"), ("row.interiorFaces", "interiorFaces")],
    "m1-4": [("row.flippedFaces", "flippedFaces")],
    "m1-6": [("row.nonTris", "nonTris")],
    "m1-7": [("row.offset", "offset")],
    "m1-9": [("row.materials", "materials")],
    "m1-10": [("row.outsideFaces", "outsideFaces"), ("row.overlapFaces", "overlapFaces"),
              ("row.overlapPercent", "overlapPercent")],
    "m1-11": [("row.pxPerMeter", "pxPerMeter"), ("row.packMedian", "packMedian"),
              ("row.diffPercent", "diffPercent")],
    "m1-12": [("row.tex", "tex")],
    "m1-16": [("row.topology", "topology"), ("row.faces", "faces"), ("row.tris", "tris"),
              ("row.verts", "verts"), ("row.edges", "edges")],
    "m1-15": [("row.tris", "tris"), ("row.budget", "budget"), ("row.texStat", "tex"),
              ("row.mats", "mats"), ("row.objs", "objs")],
}
SELECT_UNITS = {"VERT": "vertex", "EDGE": "edge", "FACE": "face"}

# Last result, kept in memory only so the .blend is not modified by a check.
_last = {"report": None, "path": None, "error": "", "delivered": [], "confirmed": set(), "stale": False, "lang": ""}


@bpy.app.handlers.persistent
def _mark_stale(*_args):
    """Undo/Redo changes the scene behind the shown result; Fix/Confirm must not act on it."""
    if _last["report"]:
        _last["stale"] = True


def _set_language(prefs, _context=None):
    i18n.LANG = prefs.language
    # Results on the panel were written in the old language: check again so they follow the switch.
    if _last["report"] and not bpy.app.timers.is_registered(_recheck_in_new_language):
        bpy.app.timers.register(_recheck_in_new_language, first_interval=0.05)


def _recheck_in_new_language():
    try:
        _run_check(bpy.context)
    except Exception:   # nothing to show it on from a timer; the panel then shows the "check again" hint
        pass
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
    return None


class AssetGatePreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    language: bpy.props.EnumProperty(
        name="Language",
        description="Language of the panel and of check results written to reports",
        items=i18n.LANGUAGES,
        default=i18n.DEFAULT,
        update=_set_language,
    )

    mode: bpy.props.EnumProperty(
        name="Use",
        description="Game: models for your own game (Gate 1 + 2). Store: assets to sell on the Unity Asset Store (Gate 1 + 2 + 3)",
        items=(("game", "Game", "Models for your own game"), ("store", "Store", "Assets to sell on the Unity Asset Store")),
        default="game",
    )

    unity_project: bpy.props.StringProperty(
        name="Unity project",
        description="Unity project that Export to Unity delivers files into. Results are kept in its AssetGate folder",
        subtype='DIR_PATH',
    )

    data_folder: bpy.props.StringProperty(
        name="Data folder (optional)",
        description="Only if you keep results somewhere else. Empty = <Unity project>/AssetGate",
        subtype='DIR_PATH',
    )

    def draw(self, context):
        self.layout.prop(self, "language")
        self.layout.prop(self, "mode")
        self.layout.prop(self, "unity_project")
        self.layout.prop(self, "data_folder")


ASSET_TYPES = ("none", "smallProp", "mediumProp", "building", "foliage", "character", "npc", "vehicle", "heroProp")
PLATFORMS = ("none", "mobile", "pc", "vr")
_enum_cache = {}   # Blender needs the dynamic enum item strings kept alive


def _enum_items(prefix, keys):
    def items(_self, _context):
        cached = _enum_cache.setdefault((prefix, i18n.LANG), [(k, tr(f"{prefix}.{k}"), "") for k in keys])
        return cached
    return items


class AssetGateSettings(bpy.types.PropertyGroup):
    pack: bpy.props.StringProperty(name="Pack", description="Pack name, same as in the checklist page")
    model: bpy.props.StringProperty(name="Model", description="Model name (empty = FBX file name)")
    fbx_path: bpy.props.StringProperty(name="FBX", description="Exported FBX file", subtype='FILE_PATH')
    # Optional: makes the polygon-count advice of m1-16 specific (SPEC D22). Saved in the .blend.
    asset_type: bpy.props.EnumProperty(name="Type", description="What the model is used as in the game",
                                       items=_enum_items("type", ASSET_TYPES))
    platform: bpy.props.EnumProperty(name="Platform", description="Where the game runs",
                                     items=_enum_items("platform", PLATFORMS))


def _pref(context, name):
    addon = context.preferences.addons.get(__package__)
    value = getattr(addon.preferences, name) if addon else ""
    return os.path.normpath(bpy.path.abspath(value)) if value else ""


def _data_folder(context):
    return core.resolve_data_folder(_pref(context, "data_folder"), _pref(context, "unity_project"))


def _store_mode(context):
    addon = context.preferences.addons.get(__package__)
    return bool(addon) and addon.preferences.mode == "store"


def _sync_language(context):
    """Use the language from the preferences (falls back to the default when not installed as an add-on)."""
    addon = context.preferences.addons.get(__package__)
    i18n.LANG = addon.preferences.language if addon else i18n.LANG


def _model_name(settings):
    """Explicit name, else the FBX file name, else the .blend file name."""
    source = settings.model or settings.fbx_path or bpy.data.filepath
    return os.path.splitext(os.path.basename(source))[0]


def _check_model(settings):
    return settings.model or os.path.splitext(os.path.basename(settings.fbx_path))[0]


def _run_check(context):
    """Run Gate 1 like the Check button. Returns the number of failed checks; raises GateError."""
    settings = context.scene.asset_gate
    _last.update(report=None, path=None, error="", delivered=[], stale=False)
    try:
        report, path = core.run_gate1(context, _data_folder(context), settings.pack, _check_model(settings), settings.fbx_path)
    except core.GateError as exc:
        _last["error"] = str(exc)
        raise
    _last.update(report=report, path=path, lang=i18n.LANG)
    _load_confirmed(context)
    return sum(1 for c in report["checks"].values() if c["status"] == "fail")


class ASSETGATE_OT_check(bpy.types.Operator):
    bl_idname = "asset_gate.check"
    bl_label = "Check"
    bl_description = "Check Gate 1 on this scene and the FBX file, then write the report to the Data folder"

    def execute(self, context):
        _sync_language(context)
        try:
            failed = _run_check(context)
        except core.GateError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'WARNING'} if failed else {'INFO'},
                    tr("op.failed", n=failed) if failed else tr("op.noFails"))
        return {'FINISHED'}


class ASSETGATE_OT_fix(bpy.types.Operator):
    bl_idname = "asset_gate.fix"
    bl_label = "Fix"
    bl_description = "Fix this check in the open scene (asks first; Ctrl+Z undoes it), then check again"
    bl_options = {'REGISTER', 'UNDO'}

    check_id: bpy.props.StringProperty(options={'HIDDEN'})
    variant: bpy.props.StringProperty(options={'HIDDEN'})

    def _context(self, context):
        report = _last["report"]
        if not report or self.check_id not in report["checks"]:
            raise core.GateError(tr("conf.noReport"))
        if _last["stale"]:
            raise core.GateError(tr("ui.staleAfterUndo"))
        settings = context.scene.asset_gate
        cfg = core.load_config(_data_folder(context))
        return cfg, fixes.find(self.check_id, self.variant), report["checks"][self.check_id], report["model"], settings.fbx_path

    def invoke(self, context, event):
        _sync_language(context)
        try:
            cfg, fix, check, model, fbx_path = self._context(context)
            self._lines = fixes.plan(context, cfg, fix, check, model, fbx_path)
        except core.GateError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        if fix.level == fixes.SAFE:
            self._lines.append(tr("fix.safeNote"))
        return context.window_manager.invoke_props_dialog(self, width=520, title=fix.label)

    def draw(self, context):
        col = self.layout.column(align=True)
        for line in getattr(self, "_lines", []):
            _wrap(col, context, line, icon='ERROR' if line.startswith("⚠") else 'NONE')

    def execute(self, context):
        _sync_language(context)
        try:
            cfg, fix, check, model, fbx_path = self._context(context)
            summary = fixes.apply(context, cfg, fix, check, model, fbx_path)
            _run_check(context)
        except core.GateError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, summary)
        return {'FINISHED'}


class ASSETGATE_OT_export_unity(bpy.types.Operator):
    bl_idname = "asset_gate.export_unity"
    bl_label = "Export to Unity"
    bl_description = "Check Gate 1, then deliver the FBX and textures to the open Unity project (only when it passes)"

    overwrite: bpy.props.BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def _args(self, context):
        settings = context.scene.asset_gate
        return _data_folder(context), _pref(context, "unity_project"), settings.pack, _model_name(settings)

    def _fail(self, exc):
        _last.update(report=None, path=None, error=str(exc), delivered=[])
        self.report({'ERROR'}, str(exc))
        return {'CANCELLED'}

    def invoke(self, context, event):
        # Ask before overwriting; every other problem is reported by execute().
        data_folder, project, pack, model = self._args(context)
        self._clashes = []
        try:
            cfg = core.load_config(data_folder)
            self._clashes = unity_export.existing(unity_export.targets(context, cfg, project, pack, model))
        except (core.GateError, OSError, KeyError):
            pass
        if self._clashes:
            self.overwrite = True
            return context.window_manager.invoke_props_dialog(self, width=420)
        return self.execute(context)

    def draw(self, context):
        col = self.layout.column()
        col.label(text=tr("ui.overwrite"), icon='ERROR')
        for path in self._clashes:
            col.label(text="    " + os.path.basename(path))

    def execute(self, context):
        data_folder, project, pack, model = self._args(context)
        _last.update(report=None, path=None, error="", delivered=[])
        try:
            report, path, delivered = unity_export.export_to_unity(
                context, data_folder, project, pack, model, overwrite=self.overwrite)
        except core.GateError as exc:
            return self._fail(exc)
        _last.update(report=report, path=path, delivered=delivered, lang=i18n.LANG)
        _load_confirmed(context)
        if not delivered:
            self.report({'WARNING'}, tr("op.notSent"))
            return {'FINISHED'}
        context.scene.asset_gate.fbx_path = delivered[-1]
        self.report({'INFO'}, tr("op.sent", n=len(delivered)))
        return {'FINISHED'}


def _load_confirmed(context):
    report = _last["report"]
    _last["confirmed"] = (core.valid_confirms(report, core.load_confirms(_data_folder(context), report["pack"], report["model"]))
                          if report else set())


def _is_confirmed(check_id, check):
    return check["status"] == "review" and check_id in _last["confirmed"]


class ASSETGATE_OT_confirm(bpy.types.Operator):
    bl_idname = "asset_gate.confirm"
    bl_label = "Confirm"
    bl_description = "Confirm this review item after checking it yourself (saved next to the report; shown in the checklist page)"

    check_id: bpy.props.StringProperty(options={'HIDDEN'})
    confirmed: bpy.props.BoolProperty(options={'HIDDEN'})

    def execute(self, context):
        _sync_language(context)
        report = _last["report"]
        if not report or _last["stale"]:
            self.report({'ERROR'}, tr("ui.staleAfterUndo") if report else tr("conf.noReport"))
            return {'CANCELLED'}
        try:
            _last["confirmed"] = core.set_confirm(_data_folder(context), report, self.check_id, self.confirmed)
        except (core.GateError, OSError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, tr("op.confirmed" if self.confirmed else "op.unconfirmed", id=self.check_id))
        return {'FINISHED'}


class ASSETGATE_OT_select(bpy.types.Operator):
    bl_idname = "asset_gate.select"
    bl_label = "Select"
    bl_description = "Select the problem geometry in Edit Mode"
    bl_options = {'REGISTER', 'UNDO'}

    check_id: bpy.props.StringProperty(options={'HIDDEN'})
    key: bpy.props.StringProperty(options={'HIDDEN'})

    def execute(self, context):
        sel = core.last_selection.get((self.check_id, self.key))
        if not sel:
            self.report({'ERROR'}, tr("sel.none"))
            return {'CANCELLED'}
        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        objects = []
        for name, wanted in sel["counts"].items():
            obj = context.scene.objects.get(name)
            current = (len(obj.data.vertices), len(obj.data.edges), len(obj.data.polygons)) if obj else None
            if current != tuple(wanted):
                self.report({'ERROR'}, tr("sel.stale", name=name))
                return {'CANCELLED'}
            objects.append(obj)

        for obj in context.view_layer.objects:
            obj.select_set(False)
        for obj in objects:
            obj.select_set(True)
        context.view_layer.objects.active = objects[0]
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.reveal(select=False)
        bpy.ops.mesh.select_mode(type=sel["mode"])
        bpy.ops.mesh.select_all(action='DESELECT')
        attr = {"VERT": "verts", "EDGE": "edges", "FACE": "faces"}[sel["mode"]]
        total = 0
        for obj in objects:
            bm = bmesh.from_edit_mesh(obj.data)
            elements = getattr(bm, attr)
            elements.ensure_lookup_table()
            for i in sel["objects"][obj.name]:
                elements[i].select_set(True)
                total += 1
            bm.select_flush_mode()
            bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, tr("sel.done", n=total, unit=SELECT_UNITS[sel['mode']]))
        return {'FINISHED'}


def _wrap(layout, context, text, icon='NONE'):
    """Blender labels do not wrap; split by the sidebar width so long Thai text stays readable."""
    width = context.region.width if context.region else 300
    chars = max(18, int(width / (7 * context.preferences.view.ui_scale)))
    col = layout.column(align=True)
    col.scale_y = 0.8
    indent = 'NONE' if icon == 'NONE' else 'BLANK1'
    for part in text.split(" · "):
        for line in textwrap.wrap(part, chars) or [""]:
            col.label(text=line, icon=icon)
            icon = indent


def _format(value):
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, list):
        return " × ".join(_format(v) for v in value)
    return str(value)


def _draw_rows(layout, check_id, check):
    values = check["values"]
    rows = [(label, key) for label, key in ROWS.get(check_id, []) if key in values]
    extra = []
    if check_id == "m1-8":
        extra = [(name.replace(":", ": ", 1), reason) for name, reason in values.get("bad", {}).items()]
    elif check_id == "m1-5":
        extra = [(name, tr("row.notApplied")) for name in values.get("unapplied", {})]
    if not rows and not extra:
        return
    col = layout.column(align=True)
    for label, key in rows:
        split = col.split(factor=0.62, align=True)
        split.label(text=tr(label))
        sel = core.last_selection.get((check_id, key))
        if sel:
            op = split.operator(ASSETGATE_OT_select.bl_idname, text=_format(values[key]), icon='RESTRICT_SELECT_OFF')
            op.check_id, op.key = check_id, key
        elif key == "topology":
            split.label(text=tr("topology." + values[key]))
        elif check_id == "m1-16":
            split.label(text=f"{values[key]:,}")   # thousands separators, like Meshy
        else:
            split.label(text=_format(values[key]))
    for label, value in extra:
        split = col.split(factor=0.5, align=True)
        split.label(text=label)
        split.label(text=value)


class ASSETGATE_PT_panel(bpy.types.Panel):
    bl_idname = "ASSETGATE_PT_panel"
    bl_label = "Asset Gate — Gate 1"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Asset Gate"

    def draw(self, context):
        _sync_language(context)
        layout = self.layout
        settings = context.scene.asset_gate
        addon = context.preferences.addons.get(__package__)
        if addon:
            prefs = addon.preferences
            layout.row().prop(prefs, "language", text=tr("ui.language"), expand=True)
            layout.row().prop(prefs, "mode", text=tr("ui.mode"), expand=True)
            data_folder = _data_folder(context)
            if not data_folder:
                _wrap(layout, context, tr("ui.setUnityProject"), icon='ERROR')
                layout.prop(prefs, "unity_project", text=tr("ui.unityProject"))
            else:
                # Shown so a mismatch with the Unity window's Data folder is easy to spot.
                _wrap(layout, context, tr("ui.dataIn", path=data_folder), icon='FILE_FOLDER')
        col = layout.column()
        col.prop(settings, "pack", text=tr("ui.pack") if _store_mode(context) else tr("ui.folder"))
        col.prop(settings, "model", text=tr("ui.model"))
        col.prop(settings, "fbx_path", text=tr("ui.fbx"))
        row = col.row(align=True)
        row.prop(settings, "asset_type", text="")
        row.prop(settings, "platform", text="")
        row = layout.row(align=True)
        row.scale_y = 1.3
        row.operator(ASSETGATE_OT_check.bl_idname, text=tr("ui.check"), icon='VIEWZOOM')
        row.operator(ASSETGATE_OT_export_unity.bl_idname, text=tr("ui.export"), icon='EXPORT')

        if _last["error"]:
            _wrap(layout.box(), context, _last["error"], icon='ERROR')
        report = _last["report"]
        if report and _last["stale"]:
            _wrap(layout.box(), context, tr("ui.staleAfterUndo"), icon='ERROR')
        elif report and _last["lang"] and _last["lang"] != i18n.LANG:
            _wrap(layout.box(), context, tr("ui.rerun"), icon='INFO')
        if report:
            self.draw_report(context, layout, report, settings)

    def draw_report(self, context, layout, report, settings):
        checks = [(cid, report["checks"][cid]) for cid in core.CHECK_IDS if cid in report["checks"]]
        counts = {s: sum(1 for cid, c in checks if c["status"] == s and not _is_confirmed(cid, c)) for s in STATUS_ICONS}
        counts["confirmed"] = sum(1 for cid, c in checks if _is_confirmed(cid, c))

        box = layout.box()
        if _last["delivered"]:
            _wrap(box, context, tr("ui.sentBanner", n=len(_last['delivered'])), icon='EXPORT')
        if counts["fail"]:
            box.label(text=tr("ui.gateFail"), icon='CANCEL')
        elif not _last["path"]:
            box.label(text=tr("ui.sceneOk"), icon='INFO')
        else:
            box.label(text=tr("ui.gatePass"), icon='CHECKMARK')
        box.label(text=" · ".join(f"{tr('status.' + s)} {counts[s]}" for s in ("fail", "review", "confirmed", "pass") if counts[s]))
        if not _last["path"]:
            box.label(text=tr("ui.noReport"), icon='BLANK1')

        # Each check is a collapsible layout panel: header in Blender's panel-title style, open/closed
        # state remembered per sidebar. Problems start open, passed checks start closed.
        for status in STATUS_ORDER:
            for check_id, check in checks:
                if check["status"] == status and not _is_confirmed(check_id, check):
                    _draw_check_panel(layout, context, check_id, check, default_closed=False)

        done = [(cid, c) for cid, c in checks if c["status"] not in STATUS_ORDER or _is_confirmed(cid, c)]
        if not done:
            return
        header, body = layout.panel("asset_gate_passed", default_closed=True)
        header.label(text=tr("ui.passedGroup", n=len(done)), icon='CHECKMARK')
        if body:
            for check_id, check in done:
                _draw_check_panel(body, context, check_id, check, default_closed=True)


def _fbx_in_unity(context):
    """True when the FBX field points inside the Unity project (set by Export to Unity)."""
    fbx = context.scene.asset_gate.fbx_path
    project = _pref(context, "unity_project")
    if not fbx or not project:
        return False
    fbx = os.path.normcase(os.path.normpath(bpy.path.abspath(fbx)))
    return fbx.startswith(os.path.normcase(os.path.normpath(project)) + os.sep)


def _draw_fixes(layout, context, check_id, check):
    if check["status"] not in ("fail", "review") or _is_confirmed(check_id, check):
        return
    available = fixes.available(check_id, check)
    if check_id == "m1-14" and _fbx_in_unity(context):
        # The FBX is the one Export to Unity delivered: export it again with the textures and the report,
        # not just the FBX (the FBX field never has to be cleared for that).
        _wrap(layout, context, tr("hint.m1-14unity"), icon='INFO')
        return
    for fix in available:
        row = layout.row(align=True)
        op = row.operator(ASSETGATE_OT_fix.bl_idname, text=fix.label,
                          icon='ERROR' if fix.level == fixes.RISKY else 'MODIFIER')
        op.check_id, op.variant = check_id, fix.variant
        if fix.level == fixes.RISKY:
            hint = layout.row()
            hint.scale_y = 0.7
            hint.label(text=tr("fix.risky"), icon='BLANK1')
    if not available and check_id in fixes.HINTS:
        _wrap(layout, context, tr(fixes.HINTS[check_id]), icon='INFO')


def _draw_check_panel(layout, context, check_id, check, default_closed):
    status = check["status"]
    confirmed = _is_confirmed(check_id, check)
    header, body = layout.panel(f"asset_gate_{check_id}", default_closed=default_closed)
    header.label(text=f"{check_id}  {core.title(check_id)}", icon='CHECKMARK' if confirmed else STATUS_ICONS[status])
    right = header.row()
    right.alignment = 'RIGHT'
    right.label(text=tr("status.confirmed" if confirmed else "status." + status))
    if not body:
        return
    if check["detail"]:
        _wrap(body, context, check["detail"])
    _draw_rows(body, check_id, check)
    if _last["stale"]:
        return
    _draw_fixes(body, context, check_id, check)
    if status == "review":
        op = body.operator(ASSETGATE_OT_confirm.bl_idname, icon='LOOP_BACK' if confirmed else 'CHECKMARK',
                           text=tr("ui.unconfirm" if confirmed else "ui.confirm"))
        op.check_id, op.confirmed = check_id, not confirmed


classes = (AssetGatePreferences, AssetGateSettings, ASSETGATE_OT_check, ASSETGATE_OT_fix, ASSETGATE_OT_export_unity,
           ASSETGATE_OT_confirm, ASSETGATE_OT_select, ASSETGATE_PT_panel)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    addon = bpy.context.preferences.addons.get(__package__)
    if addon:
        i18n.LANG = addon.preferences.language
    bpy.types.Scene.asset_gate = bpy.props.PointerProperty(type=AssetGateSettings)
    for handlers in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if _mark_stale not in handlers:
            handlers.append(_mark_stale)


def unregister():
    for handlers in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        for fn in [f for f in handlers if getattr(f, "__name__", "") == "_mark_stale"]:
            handlers.remove(fn)
    del bpy.types.Scene.asset_gate
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
