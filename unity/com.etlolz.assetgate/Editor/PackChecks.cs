using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace ETLOLZ.AssetGate
{
    /// <summary>
    /// Gate 3 checks done in Unity (SPEC §5: k1-1, k1-2, k1-3, k1-4, k1-6, k1-9, k3-6, k3-7).
    /// Read-only: demo scenes are opened as preview scenes, the user's open scene is never touched.
    /// Writes reports/&lt;Pack&gt;/_pack.unity.json.
    /// </summary>
    public static class PackChecks
    {
        public static readonly string[] Order = { "k1-1", "k1-2", "k1-3", "k1-4", "k1-6", "k1-9", "k3-6", "k3-7" };

        public static string Title(string id) => Lang.T("title." + id);

        // Most specific first so "Unity 6000.3.22f1" reports the full version.
        static readonly Regex UnityVersion = new Regex(@"\b6000\.\d+(\.\d+\w*)?|\b20\d\d\.\d+(\.\d+\w*)?|Unity\s*6\b", RegexOptions.IgnoreCase);

        static Dictionary<string, object> Result(string status, string detail, Dictionary<string, object> values = null) =>
            new Dictionary<string, object> { { "status", status }, { "detail", detail ?? "" }, { "values", values ?? new Dictionary<string, object>() } };

        static Dictionary<string, object> V(params object[] kv)
        {
            var d = new Dictionary<string, object>();
            for (var i = 0; i + 1 < kv.Length; i += 2) d[(string)kv[i]] = kv[i + 1];
            return d;
        }

        public class Pack
        {
            public string DataFolder;
            public Dictionary<string, object> Config;
            public string Name;
            public string Folder;           // Assets/<Pack>
            public List<string> Files;      // every asset file under the pack folder

            public Dictionary<string, object> PackConfig => MiniJson.Obj(Config, "pack");
            public string DemoFolder => Folder + "/" + MiniJson.Str(PackConfig, "demoFolder");
        }

        /// <summary>The pack of the selected asset or folder (Assets/&lt;Pack&gt;/...).</summary>
        public static Pack ForSelection()
        {
            var obj = Selection.activeObject;
            return ForPath(obj ? AssetDatabase.GetAssetPath(obj) : null);
        }

        /// <summary>The pack of an asset or folder path (Assets/&lt;Pack&gt;/...).</summary>
        public static Pack ForPath(string path)
        {
            var parts = (path ?? "").Split('/');
            if (parts.Length < 2 || parts[0] != "Assets") throw new GateException(Lang.T("err.noPackSelection"));
            var ctx = GateContext.ForData();
            var pack = new Pack { DataFolder = ctx.DataFolder, Config = ctx.Config, Name = parts[1], Folder = "Assets/" + parts[1] };
            // A pack folder is one that Export to Unity created: it has the mesh folder.
            var meshFolder = MiniJson.Str(MiniJson.Obj(MiniJson.Obj(ctx.Config, "unity"), "export"), "meshFolder");
            if (!AssetDatabase.IsValidFolder(pack.Folder + "/" + meshFolder))
                throw new GateException(Lang.T("err.notPackFolder", pack.Folder, meshFolder));
            pack.Files = AssetDatabase.FindAssets("", new[] { pack.Folder })
                .Select(AssetDatabase.GUIDToAssetPath)
                .Where(p => !AssetDatabase.IsValidFolder(p))
                .Distinct().OrderBy(p => p, StringComparer.Ordinal).ToList();
            return pack;
        }

        public static Dictionary<string, object> Run(Pack pack)
        {
            var checks = new Dictionary<string, object>();
            void Add(string id, Func<Dictionary<string, object>> check)
            {
                try { checks[id] = check(); }
                catch (Exception e) { checks[id] = Result("fail", Lang.T("res.crashed", e.GetType().Name + ": " + e.Message)); }
            }
            var readme = Readmes(pack);
            var notices = Notices(pack);

            Add("k1-1", () => CheckFolders(pack));
            Add("k1-2", () => CheckPathLength(pack));
            Add("k1-3", () => CheckDemoScene(pack));
            Add("k1-4", () => CheckReadmeContent(readme));
            Add("k1-6", () => notices.Count > 0
                ? Result("review", Lang.T("pack.noticesFound", string.Join(", ", notices.Select(Path.GetFileName))), V("files", notices))
                : Result("review", Lang.T("pack.noticesMissing"), V("files", new List<object>())));
            Add("k1-9", () => readme.Count > 0
                ? Result("pass", "", V("files", readme))
                : Result("fail", Lang.T("pack.noReadme", string.Join(" / ", MiniJson.Arr(pack.PackConfig, "readmeNames").OfType<string>())), V("files", new List<object>())));
            Add("k3-6", () => CheckDemoConsole(pack));
            Add("k3-7", () => CheckUnused(pack));

            var report = new Dictionary<string, object>
            {
                { "schema", 1 }, { "tool", "unity" }, { "toolVersion", GateChecks.ToolVersion }, { "scope", "pack" },
                { "pack", pack.Name }, { "checkedAt", DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ") },
                { "checks", checks },
            };
            var path = ReportPath(pack);
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            var tmp = path + ".tmp";
            File.WriteAllText(tmp, MiniJson.Write(report) + "\n");
            if (File.Exists(path)) File.Delete(path);
            File.Move(tmp, path);
            Confirms.Prune(path);
            return report;
        }

        public static string ReportPath(Pack pack) => Path.Combine(pack.DataFolder, "reports", pack.Name, "_pack.unity.json");

        public static List<string> Readmes(Pack pack) => Docs(pack, MiniJson.Arr(pack.PackConfig, "readmeNames").OfType<string>());
        public static List<string> Notices(Pack pack) => Docs(pack, new[] { MiniJson.Str(pack.PackConfig, "noticesName") });

        /// <summary>Files no prefab or scene of the pack depends on (README / notices excluded).</summary>
        public static List<string> UnusedFiles(Pack pack)
        {
            var roots = pack.Files.Where(p => p.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase) || p.EndsWith(".unity", StringComparison.OrdinalIgnoreCase)).ToArray();
            var used = new HashSet<string>(AssetDatabase.GetDependencies(roots, true), StringComparer.Ordinal);
            var exempt = new HashSet<string>(Readmes(pack).Concat(Notices(pack)), StringComparer.Ordinal);
            return pack.Files.Where(p => !used.Contains(p) && !exempt.Contains(p)).ToList();
        }

        /// <summary>Documentation files named like one of the names (any configured extension).</summary>
        static List<string> Docs(Pack pack, IEnumerable<string> names)
        {
            var exts = MiniJson.Arr(pack.PackConfig, "docExtensions").OfType<string>().Select(e => e.ToLowerInvariant()).ToList();
            var wanted = names.Select(n => n.ToLowerInvariant()).ToList();
            return pack.Files.Where(p => exts.Contains(Path.GetExtension(p).ToLowerInvariant())
                                         && wanted.Contains(Path.GetFileNameWithoutExtension(p).ToLowerInvariant())).ToList();
        }

        static Dictionary<string, object> CheckFolders(Pack pack)
        {
            var folders = MiniJson.Arr(pack.PackConfig, "folders").OfType<string>().ToList();
            var missing = folders.Where(f => !AssetDatabase.IsValidFolder(pack.Folder + "/" + f)).ToList();
            return missing.Count > 0
                ? Result("fail", Lang.T("pack.missingFolders", string.Join(", ", missing)), V("missing", missing))
                : Result("pass", "", V("folders", folders));
        }

        static Dictionary<string, object> CheckPathLength(Pack pack)
        {
            var limit = (int)MiniJson.Num(pack.PackConfig, "maxPathLength");
            if (pack.Files.Count == 0) return Result("fail", Lang.T("pack.empty"));
            var tooLong = pack.Files.Where(p => p.Length > limit).ToList();
            var longest = pack.Files.Max(p => p.Length);
            var values = V("longest", longest, "limit", limit, "tooLong", tooLong.Take(10).ToList());
            return tooLong.Count > 0
                ? Result("fail", Lang.T("pack.pathTooLong", tooLong.Count, limit, tooLong[0]), values)
                : Result("pass", "", values);
        }

        static List<string> DemoScenes(Pack pack) =>
            pack.Files.Where(p => p.StartsWith(pack.DemoFolder + "/", StringComparison.Ordinal) && p.EndsWith(".unity", StringComparison.OrdinalIgnoreCase)).ToList();

        static Dictionary<string, object> CheckDemoScene(Pack pack)
        {
            var scenes = DemoScenes(pack);
            return scenes.Count > 0
                ? Result("pass", "", V("scenes", scenes))
                : Result("fail", Lang.T("pack.noDemo", pack.DemoFolder), V("scenes", new List<object>()));
        }

        static Dictionary<string, object> CheckReadmeContent(List<string> readme)
        {
            if (readme.Count == 0) return Result("fail", Lang.T("pack.readmeMissingForContent"));
            var text = readme.Where(p => !p.EndsWith(".pdf", StringComparison.OrdinalIgnoreCase))
                             .Select(p => File.ReadAllText(Path.GetFullPath(p))).FirstOrDefault();
            if (text == null) return Result("review", Lang.T("pack.readmePdf"), V("files", readme));
            var urp = Regex.IsMatch(text, @"\bURP\b|Universal Render Pipeline", RegexOptions.IgnoreCase);
            var version = UnityVersion.Match(text);
            var values = V("urp", urp, "unityVersion", version.Success ? version.Value : "");
            if (!urp || !version.Success)
                return Result("fail", Lang.T("pack.readmeLacks", (!urp ? "URP " : "") + (!version.Success ? Lang.T("pack.unityVersion") : "")).Trim(), values);
            return Result("review", Lang.T("pack.readmeFound", version.Value), values);
        }

        static Dictionary<string, object> CheckDemoConsole(Pack pack)
        {
            var scenes = DemoScenes(pack);
            if (scenes.Count == 0) return Result("fail", Lang.T("pack.noDemo", pack.DemoFolder));
            var errors = new List<string>();
            var warnings = new List<string>();
            var missingScripts = 0;
            Application.LogCallback handler = (message, stack, type) =>
            {
                if (type == LogType.Warning) warnings.Add(message);
                else if (type != LogType.Log) errors.Add(message);
            };
            Application.logMessageReceived += handler;
            try
            {
                foreach (var path in scenes)
                {
                    var scene = EditorSceneManager.OpenPreviewScene(path);
                    try
                    {
                        foreach (var root in scene.GetRootGameObjects())
                            foreach (var t in root.GetComponentsInChildren<Transform>(true))
                                missingScripts += GameObjectUtility.GetMonoBehavioursWithMissingScriptCount(t.gameObject);
                    }
                    finally { EditorSceneManager.ClosePreviewScene(scene); }
                }
            }
            finally { Application.logMessageReceived -= handler; }
            var values = V("scenes", scenes.Count, "errors", errors.Count, "warnings", warnings.Count, "missingScripts", missingScripts,
                "messages", errors.Concat(warnings).Take(5).ToList());
            if (errors.Count + warnings.Count + missingScripts == 0) return Result("pass", "", values);
            return Result("fail", Lang.T("pack.demoConsole", errors.Count, warnings.Count, missingScripts,
                errors.Concat(warnings).FirstOrDefault() ?? ""), values);
        }

        /// <summary>Assets no prefab or scene of the pack depends on (docs excluded).</summary>
        static Dictionary<string, object> CheckUnused(Pack pack)
        {
            if (!pack.Files.Any(p => p.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase) || p.EndsWith(".unity", StringComparison.OrdinalIgnoreCase)))
                return Result("fail", Lang.T("pack.noRoots"));
            var unused = UnusedFiles(pack);
            var values = V("checked", pack.Files.Count, "unused", unused.Take(20).ToList(), "unusedCount", unused.Count);
            return unused.Count > 0
                ? Result("fail", Lang.T("pack.unused", unused.Count, string.Join(", ", unused.Take(5).Select(Path.GetFileName))), values)
                : Result("pass", "", values);
        }
    }
}
