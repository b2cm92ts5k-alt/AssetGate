using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace ETLOLZ.AssetGate
{
    /// <summary>A Fix button: shown under a check when its result matches Applies (SPEC §10).</summary>
    public class FixDef
    {
        public string Id, Key;
        public bool Risky;
        public Func<Dictionary<string, object>, Dictionary<string, object>, bool> Applies;   // (check, all checks)
        public string Label => Lang.T("fix." + Key);
    }

    /// <summary>
    /// Fix buttons of the Unity tool (SPEC §10). Each runs only when the user presses it and accepts a
    /// dialog that lists what will change; then the window checks again.
    /// Model fixes = Setup (this model's files only). Pack fixes create missing folders / a demo scene /
    /// README and notices templates, or move unused files to the trash (recoverable).
    /// Project-wide settings (URP asset, color space) are never changed: they get a hint instead.
    /// </summary>
    public static class Fixes
    {
        static string Status(Dictionary<string, object> check) => MiniJson.Str(check, "status");
        /// <summary>A list value of a check. The report in memory holds List&lt;string&gt;, a parsed one List&lt;object&gt;.</summary>
        static List<object> List(Dictionary<string, object> check, string key)
        {
            var values = MiniJson.Obj(check, "values");
            return values != null && values.TryGetValue(key, out var v) && v is System.Collections.IEnumerable e && !(v is string)
                ? e.Cast<object>().ToList() : new List<object>();
        }

        // Failures that Setup repairs (import settings, materials, textures, prefab, collider).
        static readonly HashSet<string> SetupIds = new HashSet<string> { "m2-2", "m2-3", "m2-4", "m2-5", "m2-6", "m2-7", "m2-8", "m2-10", "m2-11" };

        public static readonly List<FixDef> Model = SetupIds.Select(id => new FixDef
        {
            Id = id, Key = "setup", Risky = false, Applies = (c, _) => Status(c) == "fail",
        }).ToList();

        public static readonly List<FixDef> Pack = new List<FixDef>
        {
            new FixDef { Id = "k1-1", Key = "folders", Applies = (c, _) => Status(c) == "fail" && List(c, "missing").Count > 0 },
            new FixDef { Id = "k1-3", Key = "demoScene", Applies = (c, _) => Status(c) == "fail" },
            new FixDef { Id = "k3-6", Key = "demoScene", Applies = (c, all) => Status(c) == "fail" && Status(MiniJson.Obj(all, "k1-3")) == "fail" },
            new FixDef { Id = "k1-9", Key = "readme", Applies = (c, _) => Status(c) == "fail" },
            new FixDef { Id = "k1-4", Key = "readme", Applies = (c, all) => Status(c) == "fail" && Status(MiniJson.Obj(all, "k1-9")) == "fail" },
            new FixDef { Id = "k1-4", Key = "readmeLine", Risky = true,
                         Applies = (c, all) => Status(c) == "fail" && Status(MiniJson.Obj(all, "k1-9")) == "pass" && MiniJson.Obj(c, "values")?.ContainsKey("urp") == true },
            new FixDef { Id = "k1-6", Key = "notices", Applies = (c, _) => Status(c) == "review" && List(c, "files").Count == 0 },
            new FixDef { Id = "k3-7", Key = "trashUnused", Risky = true, Applies = (c, _) => Status(c) == "fail" && List(c, "unused").Count > 0 },
        };

        // Shown when no button fits: things a person has to fix (or project settings we never touch).
        static readonly Dictionary<string, string> Hints = new Dictionary<string, string>
        {
            { "m2-1", "hint.m2-1" }, { "m2-9", "hint.m2-9" }, { "m2-12", "hint.m2-12" }, { "m3-1", "hint.m3-1" },
            { "m3-6", "hint.m3-6" }, { "m3-7", "hint.m3-7" }, { "k1-2", "hint.k1-2" }, { "k3-6", "hint.k3-6" },
        };

        public static List<FixDef> Available(bool pack, string id, Dictionary<string, object> checks)
        {
            var check = MiniJson.Obj(checks, id);
            return (pack ? Pack : Model).Where(f => f.Id == id && f.Applies(check, checks)).ToList();
        }

        public static string Hint(string id) => Hints.TryGetValue(id, out var key) ? Lang.T(key) : null;

        // ---------------------------------------------------------------- model

        public static string PlanModel(GateContext ctx) => Lang.T("fix.setup.plan", ctx.Model, ctx.PackFolder);

        public static List<string> ApplyModel(GateContext ctx) => ModelSetup.Run(ctx);

        // ---------------------------------------------------------------- pack

        static string ReadmePath(PackChecks.Pack pack) => pack.Folder + "/README.txt";
        static string NoticesPath(PackChecks.Pack pack) => pack.Folder + "/" + MiniJson.Str(pack.PackConfig, "noticesName") + ".txt";
        static string DemoPath(PackChecks.Pack pack) => pack.DemoFolder + "/" + string.Concat(pack.Name.Where(char.IsLetterOrDigit)) + "_Demo.unity";
        static List<string> MissingFolders(PackChecks.Pack pack) =>
            MiniJson.Arr(pack.PackConfig, "folders").OfType<string>().Where(f => !AssetDatabase.IsValidFolder(pack.Folder + "/" + f)).ToList();
        static List<string> Prefabs(PackChecks.Pack pack) => pack.Files.Where(p => p.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase)).ToList();
        static string ReadmeToExtend(PackChecks.Pack pack) =>
            PackChecks.Readmes(pack).FirstOrDefault(p => !p.EndsWith(".pdf", StringComparison.OrdinalIgnoreCase));

        /// <summary>Text for the confirmation dialog. Throws GateException when there is nothing to do.</summary>
        public static string PlanPack(PackChecks.Pack pack, FixDef fix)
        {
            var lines = new List<string>();
            switch (fix.Key)
            {
                case "folders":
                    var missing = MissingFolders(pack);
                    if (missing.Count == 0) throw new GateException(Lang.T("fix.err.nothing"));
                    lines.Add(Lang.T("fix.folders.plan"));
                    lines.AddRange(missing.Select(f => "• " + pack.Folder + "/" + f));
                    break;
                case "demoScene":
                    lines.Add(Lang.T("fix.demoScene.plan", DemoPath(pack), Prefabs(pack).Count));
                    break;
                case "readme":
                    if (AssetDatabase.LoadMainAssetAtPath(ReadmePath(pack)) != null) throw new GateException(Lang.T("fix.err.exists", ReadmePath(pack)));
                    lines.Add(Lang.T("fix.readme.plan", ReadmePath(pack), Application.unityVersion));
                    break;
                case "readmeLine":
                    var readme = ReadmeToExtend(pack) ?? throw new GateException(Lang.T("fix.err.nothing"));
                    lines.Add(Lang.T("fix.readmeLine.plan", readme));
                    lines.Add("  " + ReadmeLine());
                    break;
                case "notices":
                    if (AssetDatabase.LoadMainAssetAtPath(NoticesPath(pack)) != null) throw new GateException(Lang.T("fix.err.exists", NoticesPath(pack)));
                    lines.Add(Lang.T("fix.notices.plan", NoticesPath(pack)));
                    break;
                case "trashUnused":
                    var unused = PackChecks.UnusedFiles(pack);
                    if (unused.Count == 0) throw new GateException(Lang.T("fix.err.nothing"));
                    lines.Add(Lang.T("fix.trashUnused.plan", unused.Count));
                    lines.AddRange(unused.Take(15).Select(p => "• " + p));
                    if (unused.Count > 15) lines.Add(Lang.T("fix.more", unused.Count - 15));
                    break;
            }
            lines.Add(fix.Risky ? Lang.T("fix.riskyNote") : Lang.T("fix.safeNote"));
            return string.Join("\n", lines);
        }

        public static List<string> ApplyPack(PackChecks.Pack pack, FixDef fix)
        {
            var done = new List<string>();
            switch (fix.Key)
            {
                case "folders":
                    foreach (var f in MissingFolders(pack))
                    {
                        GateContext.EnsureAssetFolder(pack.Folder + "/" + f);
                        done.Add(Lang.T("fix.done.created", pack.Folder + "/" + f));
                    }
                    break;
                case "demoScene":
                    done.Add(Lang.T("fix.done.created", CreateDemoScene(pack)));
                    break;
                case "readme":
                    WriteText(ReadmePath(pack), ReadmeTemplate(pack));
                    done.Add(Lang.T("fix.done.created", ReadmePath(pack)));
                    break;
                case "readmeLine":
                    var readme = ReadmeToExtend(pack) ?? throw new GateException(Lang.T("fix.err.nothing"));
                    File.AppendAllText(Path.GetFullPath(readme), Environment.NewLine + Environment.NewLine + ReadmeLine() + Environment.NewLine);
                    AssetDatabase.ImportAsset(readme);
                    done.Add(Lang.T("fix.done.appended", readme));
                    break;
                case "notices":
                    WriteText(NoticesPath(pack), NoticesTemplate());
                    done.Add(Lang.T("fix.done.created", NoticesPath(pack)));
                    break;
                case "trashUnused":
                    var unused = PackChecks.UnusedFiles(pack);
                    var failed = new List<string>();
                    AssetDatabase.MoveAssetsToTrash(unused.ToArray(), failed);
                    done.Add(Lang.T("fix.done.trashed", unused.Count - failed.Count));
                    if (failed.Count > 0) done.Add(Lang.T("fix.done.trashFailed", string.Join(", ", failed)));
                    break;
            }
            AssetDatabase.SaveAssets();
            return done;
        }

        static void WriteText(string assetPath, string text)
        {
            File.WriteAllText(Path.GetFullPath(assetPath), text);
            AssetDatabase.ImportAsset(assetPath);
        }

        // Templates are store-page English (the Asset Store is English), not UI text, so they are not in Lang.
        static string ReadmeLine() => "Render pipeline: URP (Universal Render Pipeline) only. Tested with Unity " + Application.unityVersion + ".";

        static string ReadmeTemplate(PackChecks.Pack pack)
        {
            var prefabs = Prefabs(pack);
            return string.Join(Environment.NewLine, new[]
            {
                pack.Name,
                new string('=', pack.Name.Length),
                "",
                ReadmeLine(),
                "",
                "Contents",
                "- " + prefabs.Count + " prefabs in " + pack.Folder + "/" + MiniJson.Str(MiniJson.Obj(MiniJson.Obj(pack.Config, "unity"), "export"), "prefabFolder"),
                "- Demo scene in " + pack.DemoFolder,
                "",
                "How to use",
                "1. Open the demo scene in " + pack.DemoFolder + " to see every model.",
                "2. Drag prefabs into your own scene. Each prefab has a Box Collider.",
                "",
                "Support",
                "(add your contact e-mail or website)",
                "",
            });
        }

        static string NoticesTemplate() => string.Join(Environment.NewLine, new[]
        {
            "Third-Party Notices",
            "",
            "This package does not include third-party fonts, audio, code or other assets.",
            "",
            "(If it does, list each one here: name, author, license and link.)",
            "",
        });

        /// <summary>A new scene with every prefab of the pack in a row, saved without touching the open scenes.</summary>
        static string CreateDemoScene(PackChecks.Pack pack)
        {
            var path = DemoPath(pack);
            if (File.Exists(Path.GetFullPath(path))) throw new GateException(Lang.T("fix.err.exists", path));
            GateContext.EnsureAssetFolder(pack.DemoFolder);
            UnityEngine.SceneManagement.Scene scene;
            try { scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Additive); }
            catch (InvalidOperationException) { throw new GateException(Lang.T("fix.err.saveScene")); }
            try
            {
                float x = 0, height = 1;
                foreach (var prefabPath in Prefabs(pack))
                {
                    var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
                    if (!prefab) continue;
                    var go = (GameObject)PrefabUtility.InstantiatePrefab(prefab, scene);
                    var renderers = go.GetComponentsInChildren<Renderer>();
                    var bounds = renderers.Length > 0 ? renderers[0].bounds : new Bounds(go.transform.position, Vector3.one);
                    foreach (var r in renderers.Skip(1)) bounds.Encapsulate(r.bounds);
                    var gap = bounds.size.x * 0.5f;   // layout only, not a pass/fail value
                    go.transform.position += new Vector3(x - bounds.min.x, 0, 0);
                    x += bounds.size.x + gap;
                    height = Mathf.Max(height, bounds.size.y);
                }
                var cam = scene.GetRootGameObjects().Select(g => g.GetComponent<Camera>()).FirstOrDefault(c => c);
                if (cam)
                {
                    var centre = new Vector3(x / 2, height / 2, 0);
                    cam.transform.position = centre + new Vector3(0, height * 0.5f, -Mathf.Max(x, height) * 1.2f);
                    cam.transform.LookAt(centre);
                }
                if (!EditorSceneManager.SaveScene(scene, path)) throw new GateException(Lang.T("fix.err.saveScene"));
            }
            finally { EditorSceneManager.CloseScene(scene, true); }
            return path;
        }
    }
}
