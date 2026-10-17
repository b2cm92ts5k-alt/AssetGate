using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace ETLOLZ.AssetGate
{
    /// <summary>Tools > Asset Gate: Data folder, Setup and Check for the selected model, last result.</summary>
    public class AssetGateWindow : EditorWindow
    {
        string _title = "";
        string _resultLanguage;
        string _error = "";
        List<string> _setupLog;
        Dictionary<string, object> _report;
        string _reportPath;
        string _checkedPath;          // asset (model) or folder (pack) of the last check, to check again after a fix
        bool _isPack;
        List<string> _fixLog;
        HashSet<string> _confirmed = new HashSet<string>();
        Vector2 _scroll;

        [MenuItem("Tools/Asset Gate/Open Window", priority = 0)]
        public static AssetGateWindow Open()
        {
            var w = GetWindow<AssetGateWindow>();
            w.titleContent = new GUIContent("Asset Gate");
            w.minSize = new Vector2(360, 300);
            return w;
        }

        [MenuItem("Tools/Asset Gate/Set Data Folder…", priority = 20)]
        public static void PickDataFolder()
        {
            var path = EditorUtility.OpenFolderPanel("Asset Gate Data folder", GateContext.SavedDataFolder, "");
            if (!string.IsNullOrEmpty(path)) GateContext.SavedDataFolder = path;
        }

        [MenuItem("Tools/Asset Gate/Setup Selected Model", priority = 1)]
        [MenuItem("Assets/Asset Gate/Setup Model", priority = 1000)]
        public static void SetupSelected() => Open().Run(setup: true);

        [MenuItem("Tools/Asset Gate/Check Selected Model", priority = 2)]
        [MenuItem("Assets/Asset Gate/Check Model", priority = 1001)]
        public static void CheckSelected() => Open().Run(setup: false);

        [MenuItem("Tools/Asset Gate/Check Pack of Selection", priority = 3)]
        [MenuItem("Assets/Asset Gate/Check Pack", priority = 1002)]
        public static void CheckPackSelected() => Open().RunPack();

        // Gate 3 is for Store mode only (SPEC D17).
        [MenuItem("Tools/Asset Gate/Check Pack of Selection", true)]
        [MenuItem("Assets/Asset Gate/Check Pack", true)]
        public static bool CanCheckPack() => Mode.Store;

        StoreInfo _store;
        string _polyText = "";        // polygon counts + advice of the last check (SPEC D22)

        string[] _order = GateChecks.Order;
        Func<string, string> _titleOf = GateChecks.Title;

        void RunPack()
        {
            _error = "";
            _fixLog = null;
            _setupLog = null;
            _report = null;
            try
            {
                var pack = PackChecks.ForSelection();
                CheckPack(pack);
                Debug.Log("[Asset Gate] Check pack " + pack.Name);
            }
            catch (GateException e) { _error = e.Message; }
            catch (Exception e) { _error = e.GetType().Name + ": " + e.Message; Debug.LogException(e); }
            Repaint();
        }

        void CheckPack(PackChecks.Pack pack)
        {
            _title = pack.Name + " — " + Lang.T("ui.packTitle");
            _checkedPath = pack.Folder;
            _isPack = true;
            _store = null;
            _report = PackChecks.Run(pack);
            _polyText = PackPolycount(pack);
            _reportPath = PackChecks.ReportPath(pack);
            _confirmed = Confirms.Valid(_reportPath);
            _order = PackChecks.Order;
            _titleOf = PackChecks.Title;
            _resultLanguage = Lang.Current;
        }

        void CheckModel(GateContext ctx)
        {
            _store = Mode.Store ? StoreInfo.Load(ctx) : null;
            _report = GateChecks.Run(ctx);
            _polyText = ModelPolycount(ctx);
            _reportPath = ctx.ReportPath(".unity.json");
            _confirmed = Confirms.Valid(_reportPath);
            _order = GateChecks.Order;
            _titleOf = GateChecks.Title;
            _resultLanguage = Lang.Current;
            _checkedPath = ctx.FbxPath;
            _isPack = false;
        }

        /// <summary>Counts of the imported model plus advice, using the type/platform picked in Blender (m1-16).</summary>
        static string ModelPolycount(GateContext ctx)
        {
            var counts = Polycount.Of(AssetDatabase.LoadAssetAtPath<GameObject>(ctx.FbxPath));
            var m116 = MiniJson.Obj(MiniJson.Obj(MiniJson.Obj(ctx.BlenderReport, "checks"), "m1-16"), "values");
            return Lang.T("poly.counts", counts.Tris.ToString("N0"), counts.Verts.ToString("N0"), counts.Meshes) + "\n" +
                   Polycount.Advice(ctx.Config, counts.Tris, MiniJson.Str(m116, "assetType", "none"), MiniJson.Str(m116, "platform", "none"));
        }

        /// <summary>Totals over every model (FBX) in the pack.</summary>
        static string PackPolycount(PackChecks.Pack pack)
        {
            var fbxs = pack.Files.Where(p => p.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase)).ToList();
            int tris = 0, verts = 0;
            foreach (var path in fbxs)
            {
                var c = Polycount.Of(AssetDatabase.LoadAssetAtPath<GameObject>(path));
                tris += c.Tris;
                verts += c.Verts;
            }
            return Lang.T("poly.packTotal", fbxs.Count, tris.ToString("N0"), verts.ToString("N0"));
        }

        void RecheckInNewLanguage()
        {
            ClearMessages();
            try
            {
                if (_isPack) CheckPack(PackChecks.ForPath(_checkedPath));
                else CheckModel(GateContext.ForAsset(_checkedPath));
            }
            catch (GateException e) { _error = e.Message; }
            catch (Exception e) { _error = e.GetType().Name + ": " + e.Message; Debug.LogException(e); }
            Repaint();
        }

        /// <summary>Messages of the previous action (error, Setup log, Fix log).</summary>
        void ClearMessages()
        {
            _error = "";
            _setupLog = null;
            _fixLog = null;
        }

        /// <summary>The Clear button: messages and the last result, as if the window was just opened.</summary>
        void ClearAll()
        {
            ClearMessages();
            _report = null;
            _store = null;
            _polyText = "";
            _title = "";
            _checkedPath = null;
            _confirmed = new HashSet<string>();
            Repaint();
        }

        /// <summary>Ask with the list of changes, apply, then check again (SPEC §10).</summary>
        void RunFix(FixDef fix)
        {
            ClearMessages();
            try
            {
                if (_isPack)
                {
                    var pack = PackChecks.ForPath(_checkedPath);
                    if (!EditorUtility.DisplayDialog(fix.Label, Fixes.PlanPack(pack, fix), Lang.T("ui.fixOk"), Lang.T("ui.cancel"))) return;
                    _fixLog = Fixes.ApplyPack(pack, fix);
                    CheckPack(PackChecks.ForPath(_checkedPath));
                }
                else
                {
                    var ctx = GateContext.ForAsset(_checkedPath);
                    if (!EditorUtility.DisplayDialog(fix.Label, Fixes.PlanModel(ctx), Lang.T("ui.fixOk"), Lang.T("ui.cancel"))) return;
                    _fixLog = Fixes.ApplyModel(ctx);
                    CheckModel(GateContext.ForAsset(_checkedPath));
                }
                Debug.Log("[Asset Gate] " + fix.Label + ":\n" + string.Join("\n", _fixLog));
            }
            catch (GateException e) { _error = e.Message; }
            catch (Exception e) { _error = e.GetType().Name + ": " + e.Message; Debug.LogException(e); }
            Repaint();
        }

        void Run(bool setup)
        {
            _error = "";
            _fixLog = null;
            _setupLog = null;
            _report = null;
            try
            {
                var ctx = GateContext.ForSelection();
                _title = ctx.Pack + " / " + ctx.Model;
                if (setup)
                {
                    _setupLog = ModelSetup.Run(ctx);
                    Debug.Log("[Asset Gate] Setup " + _title + ":\n" + string.Join("\n", _setupLog));
                }
                else
                {
                    CheckModel(ctx);
                    Debug.Log("[Asset Gate] Check " + _title + " → " + ctx.ReportPath(".unity.json"));
                }
            }
            catch (GateException e) { _error = e.Message; }
            catch (Exception e) { _error = e.GetType().Name + ": " + e.Message; Debug.LogException(e); }
            Repaint();
        }

        void OnGUI()
        {
            var wrap = new GUIStyle(EditorStyles.label) { wordWrap = true };
            EditorGUILayout.Space(4);
            using (new EditorGUILayout.HorizontalScope())
            {
                EditorGUILayout.LabelField(Lang.T("ui.language"), GUILayout.Width(80));
                var index = System.Array.IndexOf(Lang.Codes, Lang.Current);
                var chosen = GUILayout.Toolbar(index, Lang.Names);
                if (chosen != index)
                {
                    Lang.Current = Lang.Codes[chosen];
                    // Results were written in the old language: check again so they follow the switch.
                    if (_report != null && _checkedPath != null) EditorApplication.delayCall += RecheckInNewLanguage;
                }
            }
            using (new EditorGUILayout.HorizontalScope())
            {
                EditorGUILayout.LabelField(Lang.T("ui.mode"), GUILayout.Width(80));
                var modeIndex = Array.IndexOf(Mode.Codes, Mode.Current);
                var chosenMode = GUILayout.Toolbar(modeIndex, new[] { Lang.T("ui.modeGame"), Lang.T("ui.modeStore") });
                if (chosenMode != modeIndex) { Mode.Current = Mode.Codes[chosenMode]; _report = null; _store = null; }
            }
            using (new EditorGUILayout.HorizontalScope())
            {
                EditorGUILayout.LabelField(Lang.T("ui.dataFolder"), GUILayout.Width(80));
                var folder = GateContext.DataFolderInUse;
                EditorGUILayout.SelectableLabel(string.IsNullOrEmpty(folder) ? Lang.T("ui.notSet") : folder, GUILayout.Height(18));
                if (GUILayout.Button(Lang.T("ui.browse"), GUILayout.Width(70))) PickDataFolder();
            }
            EditorGUILayout.HelpBox(Lang.T("ui.help"), MessageType.None);
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button(Lang.T("ui.setup"), GUILayout.Height(28))) Run(setup: true);
                if (GUILayout.Button(Lang.T("ui.check"), GUILayout.Height(28))) Run(setup: false);
            }
            using (new EditorGUILayout.HorizontalScope())
            {
                if (Mode.Store && GUILayout.Button(Lang.T("ui.checkPack"), GUILayout.Height(22))) RunPack();
                // Results and messages stay until the next action; this clears them (e.g. after deleting the model).
                if (GUILayout.Button(Lang.T("ui.clear"), GUILayout.Height(22), GUILayout.Width(Mode.Store ? 110 : 160))) ClearAll();
            }
            EditorGUILayout.Space(6);
            if (!string.IsNullOrEmpty(_error)) EditorGUILayout.HelpBox(_error, MessageType.Error);
            if (!string.IsNullOrEmpty(_title) && string.IsNullOrEmpty(_error)) EditorGUILayout.LabelField(_title, EditorStyles.boldLabel);

            _scroll = EditorGUILayout.BeginScrollView(_scroll);
            if (_setupLog != null)
            {
                EditorGUILayout.HelpBox(Lang.T("ui.setupDone"), MessageType.Info);
                foreach (var line in _setupLog) EditorGUILayout.LabelField("• " + line, wrap);
            }
            if (_fixLog != null && _fixLog.Count > 0)
            {
                EditorGUILayout.HelpBox(Lang.T("ui.fixDone"), MessageType.Info);
                foreach (var line in _fixLog) EditorGUILayout.LabelField("• " + line, wrap);
            }
            if (_report != null && !string.IsNullOrEmpty(_polyText)) EditorGUILayout.HelpBox(_polyText, MessageType.Info);
            if (_store != null && _report != null && !_isPack) DrawStoreInfo(wrap);
            if (_report != null) DrawReport(wrap);
            EditorGUILayout.EndScrollView();
        }

        /// <summary>Store mode: where the model came from (m4-1 … m4-4).</summary>
        void DrawStoreInfo(GUIStyle wrap)
        {
            EditorGUILayout.Space(4);
            EditorGUILayout.LabelField(Lang.T("ui.storeInfo"), EditorStyles.boldLabel);
            if (_store.FromChecklistPage) EditorGUILayout.HelpBox(Lang.T("ui.storeFromPage"), MessageType.Info);
            _store.Plan = EditorGUILayout.TextField(Lang.T("ui.storePlan"), _store.Plan);
            _store.GenDate = EditorGUILayout.TextField(Lang.T("ui.storeGenDate"), _store.GenDate);
            EditorGUILayout.LabelField(Lang.T("ui.storeManual"));
            // A text-area style (not a label style): with a label style the box had no frame and did not take typing.
            var area = new GUIStyle(EditorStyles.textArea) { wordWrap = true };
            _store.Manual = EditorGUILayout.TextArea(_store.Manual ?? "", area, GUILayout.MinHeight(48));
            if (GUILayout.Button(Lang.T("ui.storeSave"), GUILayout.Width(220)))
            {
                var info = _store;
                EditorApplication.delayCall += () =>
                {
                    ClearMessages();
                    try
                    {
                        var ctx = GateContext.ForAsset(_checkedPath);
                        info.Save(ctx);
                        CheckModel(ctx);
                    }
                    catch (GateException e) { _error = e.Message; }
                    Repaint();
                };
            }
            EditorGUILayout.Space(6);
        }

        void SetConfirm(string id, bool confirmed)
        {
            try { _confirmed = Confirms.Set(_reportPath, id, confirmed); }
            catch (GateException e) { _error = e.Message; }
            catch (Exception e) { _error = e.GetType().Name + ": " + e.Message; Debug.LogException(e); }
        }

        /// <summary>Status shown in the window: a confirmed review item shows as "confirmed".</summary>
        string Shown(string id, Dictionary<string, object> check)
        {
            var status = MiniJson.Str(check, "status");
            return status == "review" && _confirmed.Contains(id) ? "confirmed" : status;
        }

        void DrawReport(GUIStyle wrap)
        {
            var checks = MiniJson.Obj(_report, "checks");
            int fail = 0, review = 0;
            foreach (var id in _order)
            {
                var status = Shown(id, MiniJson.Obj(checks, id));
                if (status == "fail") fail++;
                if (status == "review") review++;
            }
            string pendingConfirm = null;
            bool pendingValue = false;
            FixDef pendingFix = null;
            if (_resultLanguage != null && _resultLanguage != Lang.Current) EditorGUILayout.HelpBox(Lang.T("ui.rerun"), MessageType.None);
            EditorGUILayout.HelpBox(fail > 0 ? Lang.T("ui.summaryFail", fail, review) : Lang.T("ui.summaryOk", review),
                fail > 0 ? MessageType.Warning : MessageType.Info);
            foreach (var order in new[] { "fail", "review", "confirmed", "pass", "na", "pending" })
                foreach (var id in _order)
                {
                    var check = MiniJson.Obj(checks, id);
                    var status = Shown(id, check);
                    if (status != order) continue;
                    var icon = status == "pass" || status == "confirmed" ? "TestPassed" : status == "fail" ? "TestFailed" : status == "review" ? "console.warnicon.sml" : "TestIgnored";
                    using (new EditorGUILayout.HorizontalScope())
                    {
                        GUILayout.Label(EditorGUIUtility.IconContent(icon), GUILayout.Width(18), GUILayout.Height(18));
                        EditorGUILayout.LabelField(id + "  " + _titleOf(id), EditorStyles.boldLabel);
                        EditorGUILayout.LabelField(Lang.Strings.ContainsKey("status." + status) ? Lang.T("status." + status) : status, GUILayout.Width(80));
                    }
                    var detail = MiniJson.Str(check, "detail");
                    if (!string.IsNullOrEmpty(detail)) EditorGUILayout.LabelField(detail, wrap);
                    if (status == "fail" || status == "review")
                    {
                        var fixes = Fixes.Available(_isPack, id, checks);
                        foreach (var fix in fixes)
                            using (new EditorGUILayout.HorizontalScope())
                            {
                                GUILayout.Space(22);
                                var content = fix.Risky
                                    ? new GUIContent(fix.Label + "  ⚠", Lang.T("fix.risky"))
                                    : new GUIContent(fix.Label);
                                if (GUILayout.Button(content, GUILayout.Width(300))) pendingFix = fix;
                                if (fix.Risky) GUILayout.Label(Lang.T("fix.risky"), EditorStyles.miniLabel);
                            }
                        var hint = fixes.Count == 0 ? Fixes.Hint(id) : null;
                        if (hint != null) EditorGUILayout.HelpBox(hint, MessageType.None);
                    }
                    if (status == "review" || status == "confirmed")
                        using (new EditorGUILayout.HorizontalScope())
                        {
                            GUILayout.Space(22);
                            var confirmed = status == "confirmed";
                            if (GUILayout.Button(Lang.T(confirmed ? "ui.unconfirm" : "ui.confirm"), GUILayout.Width(220)))
                            { pendingConfirm = id; pendingValue = !confirmed; }
                        }
                }
            // Applied after the loop so the layout of this repaint is not changed mid-draw.
            if (pendingConfirm != null) { SetConfirm(pendingConfirm, pendingValue); Repaint(); }
            if (pendingFix != null) EditorApplication.delayCall += () => RunFix(pendingFix);   // dialogs must not open mid-layout
            var shot = MiniJson.Str(MiniJson.Obj(MiniJson.Obj(checks, "m3-8"), "values"), "path");
            if (!string.IsNullOrEmpty(shot) && File.Exists(shot) && GUILayout.Button(Lang.T("ui.openScreenshot"))) EditorUtility.RevealInFinder(shot);
        }
    }
}
