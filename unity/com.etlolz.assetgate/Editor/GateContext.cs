using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace ETLOLZ.AssetGate
{
    /// <summary>A problem the user has to fix before Setup/Check can run.</summary>
    public class GateException : Exception
    {
        public GateException(string message) : base(message) { }
    }

    /// <summary>
    /// Everything Setup and Check need about one model: the Data folder, config.json,
    /// where the model's files live under Assets/&lt;Pack&gt;/ and the Gate 1 report from Blender.
    /// </summary>
    public class GateContext
    {
        const string DataFolderPref = "ETLOLZ.AssetGate.DataFolder";

        public string DataFolder;
        public Dictionary<string, object> Config;
        public string Pack;
        public string Model;
        public string FbxPath;              // Assets/<Pack>/<meshFolder>/<Model>.fbx
        public string PackFolder;           // Assets/<Pack>
        public Dictionary<string, object> BlenderReport;

        public static string SavedDataFolder
        {
            get => EditorPrefs.GetString(DataFolderPref, "");
            set => EditorPrefs.SetString(DataFolderPref, value ?? "");
        }

        /// <summary>Data folder in use: the one set by the user, else &lt;this project&gt;/AssetGate (SPEC D18).
        /// Outside Assets/, so Unity does not import it.</summary>
        public static string DataFolderInUse => string.IsNullOrEmpty(SavedDataFolder) ? ProjectDataFolder : SavedDataFolder;

        public static string ProjectDataFolder => Path.Combine(Path.GetDirectoryName(UnityEngine.Application.dataPath), "AssetGate");

        /// <summary>
        /// Why the Blender result does not fit the FBX in this project, or null when it does (or when there
        /// is simply none). Explains the common causes instead of "texture not found": Blender writing to the
        /// other Data folder, or a result made before the FBX was exported again.
        /// </summary>
        public string BlenderReportProblem()
        {
            var fbxHash = Sha256(FbxPath);
            string HashOf(Dictionary<string, object> report) => MiniJson.Str(MiniJson.Obj(report, "source"), "fbxSha256");
            if (BlenderReport != null && HashOf(BlenderReport) == fbxHash) return null;
            var other = string.Equals(Path.GetFullPath(DataFolder).TrimEnd('/', '\\'), Path.GetFullPath(ProjectDataFolder).TrimEnd('/', '\\'),
                StringComparison.OrdinalIgnoreCase) ? null : ProjectDataFolder;
            if (other != null)
            {
                var there = ReadJson(Path.Combine(other, "reports", Pack, Model + ".blender.json"));
                if (there != null && HashOf(there) == fbxHash) return Lang.T("err.blenderOtherFolder", other, DataFolder);
            }
            return BlenderReport == null ? null : Lang.T("err.blenderOld", DataFolder);
        }

        public Dictionary<string, object> Unity => MiniJson.Obj(Config, "unity");
        public Dictionary<string, object> ExportFolders => MiniJson.Obj(Unity, "export");
        public string Folder(string key) => PackFolder + "/" + MiniJson.Str(ExportFolders, key);
        public string ReportPath(string suffix) => Path.Combine(DataFolder, "reports", Pack, Model + suffix);

        /// <summary>Resolve the FBX at assetPath (or the FBX a selected prefab comes from).</summary>
        /// <summary>Data folder and config only (pack-level checks).</summary>
        public static GateContext ForData()
        {
            var dataFolder = DataFolderInUse;
            if (string.IsNullOrEmpty(SavedDataFolder)) Directory.CreateDirectory(dataFolder);
            else if (!Directory.Exists(dataFolder)) throw new GateException(Lang.T("err.noDataFolder"));
            return new GateContext { DataFolder = dataFolder, Config = LoadConfig(dataFolder) };
        }

        public static GateContext ForAsset(string assetPath)
        {
            var ctx = ForData();

            if (string.IsNullOrEmpty(assetPath))
                throw new GateException(Lang.T("err.noSelection"));
            if (assetPath.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase))
            {
                var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(assetPath);
                var source = prefab ? PrefabUtility.GetCorrespondingObjectFromOriginalSource(prefab) : null;
                assetPath = source ? AssetDatabase.GetAssetPath(source) : assetPath;
            }
            if (!assetPath.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase))
                throw new GateException(Lang.T("err.notFbx", assetPath));

            // Layout from Export to Unity: Assets/<Pack>/<meshFolder>/<Model>.fbx
            var parts = assetPath.Split('/');
            var meshFolder = MiniJson.Str(ctx.ExportFolders, "meshFolder");
            if (parts.Length != 4 || parts[0] != "Assets" || parts[2] != meshFolder)
                throw new GateException(Lang.T("err.layout", meshFolder, assetPath));

            ctx.Pack = parts[1];
            ctx.Model = Path.GetFileNameWithoutExtension(parts[3]);
            ctx.PackFolder = "Assets/" + ctx.Pack;
            ctx.FbxPath = assetPath;
            ctx.BlenderReport = ReadJson(ctx.ReportPath(".blender.json"));
            return ctx;
        }

        public static GateContext ForSelection()
        {
            var obj = Selection.activeObject;
            return ForAsset(obj ? AssetDatabase.GetAssetPath(obj) : null);
        }

        static Dictionary<string, object> LoadConfig(string dataFolder)
        {
            var path = Path.Combine(dataFolder, "config.json");
            var package = UnityEditor.PackageManager.PackageInfo.FindForAssembly(typeof(GateContext).Assembly);
            var shipped = package != null ? Path.Combine(package.resolvedPath, "default.config.json") : null;
            if (!File.Exists(path))
            {
                // First run on this machine: start from the default config shipped in the package.
                if (shipped == null || !File.Exists(shipped)) throw new GateException(Lang.T("err.noConfig"));
                File.Copy(shipped, path);
            }
            Dictionary<string, object> cfg;
            try { cfg = MiniJson.Parse(File.ReadAllText(path)) as Dictionary<string, object>; }
            catch (FormatException e) { throw new GateException(Lang.T("err.configUnreadable", e.Message)); }
            // Sections added in later versions (e.g. polycount, SPEC D22) come from the shipped default when an
            // older config.json lacks them. Only in memory: the user's config.json is not changed.
            if (shipped != null && File.Exists(shipped) && MiniJson.Parse(File.ReadAllText(shipped)) is Dictionary<string, object> defaults)
                foreach (var pair in defaults)
                {
                    if (!cfg.ContainsKey(pair.Key)) cfg[pair.Key] = pair.Value;
                    else if (pair.Value is Dictionary<string, object> section && cfg[pair.Key] is Dictionary<string, object> mine)
                        foreach (var inner in section)
                            if (!mine.ContainsKey(inner.Key)) mine[inner.Key] = inner.Value;   // keys inside a section too
                }

            var missing = new List<string>();
            void Need(object node, string path2, params string[] keys)
            {
                foreach (var k in keys)
                    if (!(node is Dictionary<string, object> d) || !d.ContainsKey(k)) missing.Add(path2 + k);
            }
            var unity = MiniJson.Obj(cfg, "unity");
            Need(cfg, "", "unity", "collider", "texture");
            Need(unity, "unity.", "shader", "colorSpace", "materialsLocation", "modelImport", "export", "textureRoles", "testScene");
            Need(MiniJson.Obj(unity, "export"), "unity.export.", "meshFolder", "textureFolder", "materialFolder", "prefabFolder");
            Need(MiniJson.Obj(unity, "modelImport"), "unity.modelImport.", "scaleFactor", "normals", "tangents", "meshCompression", "readWrite");
            Need(MiniJson.Obj(unity, "textureRoles"), "unity.textureRoles.", "baseMap", "normalMap", "metallicRoughness");
            Need(MiniJson.Obj(unity, "testScene"), "unity.testScene.", "width", "height", "yaw", "pitch", "lightRotation", "lightIntensity");
            Need(MiniJson.Obj(cfg, "collider"), "collider.", "boundsTolerancePercent");
            Need(cfg, "", "pack");
            Need(MiniJson.Obj(cfg, "pack"), "pack.", "maxPathLength", "folders", "demoFolder", "readmeNames", "docExtensions", "noticesName");
            if (missing.Count > 0)
                throw new GateException(Lang.T("err.configMissing", string.Join(", ", missing)));
            return cfg;
        }

        public static Dictionary<string, object> ReadJson(string path)
        {
            if (!File.Exists(path)) return null;
            try { return MiniJson.Parse(File.ReadAllText(path)) as Dictionary<string, object>; }
            catch (FormatException) { return null; }
        }

        // ---------- textures delivered by Blender ----------

        /// <summary>
        /// Texture role from its file name, using unity.textureRoles patterns. Patterns match whole
        /// "_"-separated words, case-insensitive: "orm" matches "Shovel_ORM" but not "Shovel_normal".
        /// </summary>
        public string RoleOf(string textureName)
        {
            var name = "_" + textureName.ToLowerInvariant().Replace('-', '_').Replace(' ', '_') + "_";
            var roles = MiniJson.Obj(Unity, "textureRoles");
            foreach (var role in new[] { "metallicRoughness", "normalMap", "baseMap" })
                if (MiniJson.Arr(roles, role).OfType<string>().Any(p => name.Contains("_" + p.ToLowerInvariant() + "_")))
                    return role;
            return null;
        }

        /// <summary>Material name -> texture asset paths, from m1-9 of the Blender report.</summary>
        public Dictionary<string, List<string>> MaterialTextures()
        {
            var result = new Dictionary<string, List<string>>();
            var values = MiniJson.Obj(MiniJson.Obj(MiniJson.Obj(BlenderReport, "checks"), "m1-9"), "values");
            var textures = MiniJson.Obj(values, "textures");
            if (textures == null) return null;
            foreach (var pair in textures)
            {
                var paths = new List<string>();
                foreach (var name in (pair.Value as List<object> ?? new List<object>()).OfType<string>())
                {
                    var file = name.EndsWith(".png", StringComparison.OrdinalIgnoreCase) ? name : name + ".png";
                    paths.Add(Folder("textureFolder") + "/" + file);
                }
                result[pair.Key] = paths;
            }
            return result;
        }

        /// <summary>Where Setup writes the URP metallic-smoothness version of a metallic-roughness texture.</summary>
        public static string ConvertedPath(string sourcePath) =>
            Path.GetDirectoryName(sourcePath).Replace('\\', '/') + "/" + Path.GetFileNameWithoutExtension(sourcePath) + "_MetallicSmoothness.png";

        /// <summary>The texture is in the project — or, for metallic-roughness, its converted file is
        /// (the original may be removed from the pack once converted, k3-7).</summary>
        public bool TextureAvailable(string path) =>
            AssetDatabase.LoadAssetAtPath<Texture2D>(path) != null
            || (RoleOf(Path.GetFileNameWithoutExtension(path)) == "metallicRoughness" && AssetDatabase.LoadAssetAtPath<Texture2D>(ConvertedPath(path)) != null);

        public static string Sha256(string assetPath)
        {
            using (var sha = System.Security.Cryptography.SHA256.Create())
            using (var stream = File.OpenRead(Path.GetFullPath(assetPath)))
                return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }

        public static void EnsureAssetFolder(string folder)
        {
            if (AssetDatabase.IsValidFolder(folder)) return;
            var parent = Path.GetDirectoryName(folder).Replace('\\', '/');
            EnsureAssetFolder(parent);
            AssetDatabase.CreateFolder(parent, Path.GetFileName(folder));
        }
    }
}
