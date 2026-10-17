// Batch test for the Unity tool. Copied into Assets/Editor of a throwaway copy of the URP test project:
//   Unity.exe -batchmode -projectPath <copy> -executeMethod AssetGateBatchTest.Run -logFile <log> -quit
// Arguments after -agData <folder> -agOut <result.json> -agFbx <Assets/...fbx>
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using ETLOLZ.AssetGate;
using UnityEditor;
using UnityEngine;

public static class AssetGateBatchTest
{
    static string Arg(string name)
    {
        var args = Environment.GetCommandLineArgs();
        var i = Array.IndexOf(args, name);
        return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
    }

    static Dictionary<string, object> Statuses(Dictionary<string, object> report)
    {
        var result = new Dictionary<string, object>();
        foreach (var pair in MiniJson.Obj(report, "checks"))
            result[pair.Key] = MiniJson.Str(pair.Value, "status") + " | " + MiniJson.Str(pair.Value, "detail");
        return result;
    }

    public static void Run()
    {
        var previous = GateContext.SavedDataFolder;   // EditorPrefs are machine-wide: restore afterwards
        var previousLanguage = Lang.Current;
        var previousMode = Mode.Current;
        var output = new Dictionary<string, object>();
        try
        {
            GateContext.SavedDataFolder = Arg("-agData");
            Lang.Current = "en";
            var fbx = Arg("-agFbx");
            output["before"] = Statuses(GateChecks.Run(GateContext.ForAsset(fbx)));
            output["setup1"] = ModelSetup.Run(GateContext.ForAsset(fbx));
            output["setup2"] = ModelSetup.Run(GateContext.ForAsset(fbx));
            var report = GateChecks.Run(GateContext.ForAsset(fbx));
            output["after"] = Statuses(report);
            output["source"] = MiniJson.Obj(report, "source");
            var mat = AssetDatabase.LoadAssetAtPath<Material>("Assets/Frostpunk Settlement Kit/Materials/Shovel_material.mat");
            output["material"] = mat ? mat.shader.name + " base=" + (mat.GetTexture("_BaseMap") ? mat.GetTexture("_BaseMap").name : "none")
                + " normal=" + (mat.GetTexture("_BumpMap") ? mat.GetTexture("_BumpMap").name : "none")
                + " metal=" + (mat.GetTexture("_MetallicGlossMap") ? mat.GetTexture("_MetallicGlossMap").name : "none") : "missing";
            var normal = (TextureImporter)AssetImporter.GetAtPath("Assets/Frostpunk Settlement Kit/Textures/Shovel_normal.png");
            output["normalImporter"] = normal.textureType.ToString();
            output["generated"] = AssetDatabase.FindAssets("MetallicSmoothness", new[] { "Assets/Frostpunk Settlement Kit/Textures" })
                .Select(AssetDatabase.GUIDToAssetPath).ToList();
            // converted pixel: R = source B (metallic), A = 255 - source G (roughness)
            var src = new Texture2D(2, 2); src.LoadImage(File.ReadAllBytes("Assets/Frostpunk Settlement Kit/Textures/Shovel_metallic_roughness.png"));
            var dst = new Texture2D(2, 2); dst.LoadImage(File.ReadAllBytes("Assets/Frostpunk Settlement Kit/Textures/Shovel_metallic_roughness_MetallicSmoothness.png"));
            var bad = 0; var s = src.GetPixels32(); var d = dst.GetPixels32();
            for (var i = 0; i < s.Length; i += 997) if (d[i].r != s[i].b || d[i].a != 255 - s[i].g) bad++;
            output["conversionMismatches"] = bad;
            try { GateContext.ForAsset("Assets/Scenes/SampleScene.unity"); output["wrongSelection"] = "no error"; }
            catch (GateException e) { output["wrongSelection"] = e.Message; }
            var thai = new System.Text.RegularExpressions.Regex("[\u0E00-\u0E7F]");
            output["englishReportHasThai"] = thai.IsMatch(File.ReadAllText(GateContext.ForAsset(fbx).ReportPath(".unity.json")));
            output["englishSample"] = MiniJson.Str(MiniJson.Obj(MiniJson.Obj(report, "checks"), "m3-5"), "detail");
            Lang.Current = "th";
            var thaiReport = GateChecks.Run(GateContext.ForAsset(fbx));
            output["thaiSample"] = MiniJson.Str(MiniJson.Obj(MiniJson.Obj(thaiReport, "checks"), "m3-5"), "detail");
            output["thaiTitle"] = GateChecks.Title("m3-2");
            Lang.Current = "en";
            // ---- confirmations made in the window (SPEC D11)
            var reportPath = GateContext.ForAsset(fbx).ReportPath(".unity.json");
            Confirms.Set(reportPath, "m3-5", true);
            GateChecks.Run(GateContext.ForAsset(fbx));
            output["confirmKeptAfterRecheck"] = Confirms.Valid(reportPath).Contains("m3-5");
            try { Confirms.Set(reportPath, "m2-1", true); output["confirmNonReview"] = "no error"; }
            catch (GateException e) { output["confirmNonReview"] = e.Message; }
            var confirmsPath = Confirms.PathFor(reportPath);
            var stored = (Dictionary<string, object>)MiniJson.Parse(File.ReadAllText(confirmsPath));   // pretend the size was different when confirmed
            MiniJson.Obj(MiniJson.Obj(MiniJson.Obj(stored, "confirms"), "m3-5"), "values")["size"] = new List<object> { 9.0, 9.0, 9.0 };
            File.WriteAllText(confirmsPath, MiniJson.Write(stored));
            output["confirmChangedValid"] = Confirms.Valid(reportPath).Contains("m3-5");
            output["confirmChangedPruned"] = !Confirms.Prune(reportPath).Contains("m3-5") && !File.ReadAllText(confirmsPath).Contains("m3-5");
            Confirms.Set(reportPath, "m3-5", true);
            output["confirmsFile"] = confirmsPath;
            // ---- Gate 3: pack check before and after adding README + demo scene
            Selection.activeObject = AssetDatabase.LoadAssetAtPath<UnityEngine.Object>("Assets/Frostpunk Settlement Kit");
            output["packBefore"] = Statuses(PackChecks.Run(PackChecks.ForSelection()));
            File.WriteAllText("Assets/Frostpunk Settlement Kit/README.txt", "Frostpunk Settlement Kit\nRender pipeline: URP only. Tested with Unity 6000.3.22f1.\n");
            if (!AssetDatabase.IsValidFolder("Assets/Frostpunk Settlement Kit/Demo Scenes")) AssetDatabase.CreateFolder("Assets/Frostpunk Settlement Kit", "Demo Scenes");
            var scene = UnityEditor.SceneManagement.EditorSceneManager.NewScene(UnityEditor.SceneManagement.NewSceneSetup.EmptyScene, UnityEditor.SceneManagement.NewSceneMode.Single);
            PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>("Assets/Frostpunk Settlement Kit/Prefabs/SHOVEL.prefab"));
            UnityEditor.SceneManagement.EditorSceneManager.SaveScene(scene, "Assets/Frostpunk Settlement Kit/Demo Scenes/Demo.unity");
            AssetDatabase.Refresh();
            Selection.activeObject = AssetDatabase.LoadAssetAtPath<UnityEngine.Object>("Assets/Frostpunk Settlement Kit/Demo Scenes");
            var packReport = PackChecks.Run(PackChecks.ForSelection());
            output["packAfter"] = Statuses(packReport);
            var packPath = Path.Combine(Arg("-agData"), "reports", "Frostpunk Settlement Kit", "_pack.unity.json");
            Confirms.Set(packPath, "k1-6", true);
            Selection.activeObject = AssetDatabase.LoadAssetAtPath<UnityEngine.Object>("Assets/Frostpunk Settlement Kit");
            PackChecks.Run(PackChecks.ForSelection());
            output["packConfirmKept"] = Confirms.Valid(packPath).Contains("k1-6");
            Confirms.Set(packPath, "k1-6", false);
            output["packUnconfirmed"] = !Confirms.Valid(packPath).Contains("k1-6");
            Confirms.Set(packPath, "k1-6", true);
            output["packReportPath"] = Path.Combine(Arg("-agData"), "reports", "Frostpunk Settlement Kit", "_pack.unity.json");
            Selection.activeObject = AssetDatabase.LoadAssetAtPath<UnityEngine.Object>("Assets/Scenes/SampleScene.unity");
            try { PackChecks.ForSelection(); output["packWrongSelection"] = "no error"; }
            catch (GateException e) { output["packWrongSelection"] = e.Message; }
            // ---- M6: Fix buttons (SPEC §10) on a pack without README, notices and demo scene
            const string kit = "Assets/Frostpunk Settlement Kit";
            foreach (var p in new[] { kit + "/README.txt", kit + "/Third-Party Notices.txt", kit + "/Demo Scenes" })
                AssetDatabase.DeleteAsset(p);
            var fixPack = PackChecks.ForPath(kit);
            var fixReport = PackChecks.Run(fixPack);
            output["fixBefore"] = Statuses(fixReport);
            var applied = new List<object>();
            output["fixApplied"] = applied;   // filled as fixes run, so a failure still shows the steps
            for (var round = 0; round < 10; round++)
            {
                var checks = MiniJson.Obj(fixReport, "checks");
                var next = PackChecks.Order.SelectMany(id => Fixes.Available(true, id, checks)).FirstOrDefault();
                if (next == null) break;
                Fixes.PlanPack(fixPack, next);
                applied.Add(next.Id + ":" + next.Key + " -> " + string.Join(" | ", Fixes.ApplyPack(fixPack, next)));
                fixPack = PackChecks.ForPath(kit);
                fixReport = PackChecks.Run(fixPack);
                applied.Add("  files: " + string.Join(", ", fixPack.Files.Select(Path.GetFileName)));
            }
            output["fixApplied"] = applied;
            output["fixAfter"] = Statuses(fixReport);
            output["readmeText"] = File.ReadAllText(kit + "/README.txt");
            // README without the URP line -> append fix
            File.WriteAllText(kit + "/README.txt", "Frostpunk Settlement Kit\nLow poly buildings.\n");
            AssetDatabase.ImportAsset(kit + "/README.txt");
            var k14 = MiniJson.Obj(MiniJson.Obj(PackChecks.Run(PackChecks.ForPath(kit)), "checks"), "k1-4");
            output["readmeLineBefore"] = MiniJson.Str(k14, "status");
            var lineFix = Fixes.Available(true, "k1-4", MiniJson.Obj(PackChecks.Run(PackChecks.ForPath(kit)), "checks")).Select(f => f.Key).ToList();
            output["readmeLineFixes"] = lineFix.Cast<object>().ToList();
            Fixes.ApplyPack(PackChecks.ForPath(kit), Fixes.Pack.First(f => f.Key == "readmeLine"));
            output["readmeLineAfter"] = MiniJson.Str(MiniJson.Obj(MiniJson.Obj(PackChecks.Run(PackChecks.ForPath(kit)), "checks"), "k1-4"), "status");
            // model: prefab deleted -> m2-10 fails -> Fix with Setup
            AssetDatabase.DeleteAsset(kit + "/Prefabs/SHOVEL.prefab");
            var broken = GateChecks.Run(GateContext.ForAsset(fbx));
            output["modelFixBefore"] = MiniJson.Str(MiniJson.Obj(MiniJson.Obj(broken, "checks"), "m2-10"), "status");
            // k3-7's fix removed Shovel_metallic_roughness.png: the converted file must still count (m2-1, Setup)
            output["originalMrExists"] = File.Exists(kit + "/Textures/Shovel_metallic_roughness.png");
            output["m2-1AfterTrash"] = MiniJson.Str(MiniJson.Obj(MiniJson.Obj(broken, "checks"), "m2-1"), "status");
            output["modelFixOffered"] = Fixes.Available(false, "m2-10", MiniJson.Obj(broken, "checks")).Count;
            output["hintColorSpace"] = Fixes.Hint("m3-1");
            Fixes.ApplyModel(GateContext.ForAsset(fbx));
            output["modelFixAfter"] = MiniJson.Str(MiniJson.Obj(MiniJson.Obj(GateChecks.Run(GateContext.ForAsset(fbx)), "checks"), "m2-10"), "status");
            // ---- M7: Game / Store mode, m3-4, m4-* typed in Unity, Data folder inside the project
            Mode.Current = "game";
            var gameChecks = MiniJson.Obj(GateChecks.Run(GateContext.ForAsset(fbx)), "checks");
            output["gameM4"] = string.Join(",", new[] { "m4-1", "m4-2", "m4-3", "m4-4" }.Select(id => MiniJson.Str(MiniJson.Obj(gameChecks, id), "status")));
            output["gameM34"] = MiniJson.Str(MiniJson.Obj(gameChecks, "m3-4"), "status");
            output["gameCanCheckPack"] = AssetGateWindow.CanCheckPack();
            Mode.Current = "store";
            output["storeCanCheckPack"] = AssetGateWindow.CanCheckPack();
            var storeCtx = GateContext.ForAsset(fbx);
            File.Delete(StoreInfo.PathFor(storeCtx));
            File.WriteAllText(Path.Combine(storeCtx.DataFolder, "state.json"), MiniJson.Write(new Dictionary<string, object> { { "models", new Dictionary<string, object> {
                { "mS", new Dictionary<string, object> { { "name", "SHOVEL" }, { "pack", "Frostpunk Settlement Kit" },
                    { "lic", new Dictionary<string, object> { { "plan", "Meshy Pro" }, { "genDate", "2026-09-01" }, { "manual", "Retopology and new UVs" } } } } } } } }));
            var unsaved = MiniJson.Obj(GateChecks.Run(storeCtx), "checks");
            output["storeBeforeSave"] = string.Join(",", new[] { "m4-1", "m4-2", "m4-3", "m4-4" }.Select(id => MiniJson.Str(MiniJson.Obj(unsaved, id), "status")));
            var info = StoreInfo.Load(storeCtx);
            var manualTyped = info.Manual;
            info.Manual = "";
            info.Save(storeCtx);
            var emptyManual = MiniJson.Obj(MiniJson.Obj(GateChecks.Run(storeCtx), "checks"), "m4-4");
            output["storeEmptyManual"] = MiniJson.Str(emptyManual, "status") + " | " + MiniJson.Str(emptyManual, "detail");
            info.Manual = manualTyped;
            output["storePrefilled"] = info.FromChecklistPage + " " + info.Plan + " / " + info.Manual;
            info.Save(storeCtx);
            var savedChecks = MiniJson.Obj(GateChecks.Run(storeCtx), "checks");
            output["storeAfterSave"] = string.Join(",", new[] { "m4-1", "m4-2", "m4-3", "m4-4" }.Select(id => MiniJson.Str(MiniJson.Obj(savedChecks, id), "status")));
            output["storeManual"] = MiniJson.Str(MiniJson.Obj(MiniJson.Obj(savedChecks, "m4-4"), "values"), "manual");
            output["storeFile"] = StoreInfo.PathFor(storeCtx);
            GateContext.SavedDataFolder = "";
            var auto = GateContext.ForData();
            output["autoDataFolder"] = auto.DataFolder;
            output["autoConfigCopied"] = File.Exists(Path.Combine(auto.DataFolder, "config.json"));
            GateContext.SavedDataFolder = Arg("-agData");
            // ---- m1-16 polygon counts in Unity (SPEC D22): same triangles as Blender, advice text
            {
                var polyCtx = GateContext.ForAsset(fbx);
                var counts = Polycount.Of(AssetDatabase.LoadAssetAtPath<GameObject>(fbx));
                output["polyUnityTris"] = counts.Tris;
                output["polyBlenderTris"] = MiniJson.Num(MiniJson.Obj(polyCtx.BlenderReport, "stats"), "tris");
                output["polyVerts"] = counts.Verts;
                output["polyAdviceGeneral"] = Polycount.Advice(polyCtx.Config, counts.Tris, "none", "none");
                output["polyAdviceTyped"] = Polycount.Advice(polyCtx.Config, counts.Tris, "smallProp", "vr");
            }
            // ---- Blender and Unity on different Data folders : say so instead of "texture not found"
            {
                var ctxA = GateContext.ForAsset(fbx);
                var goodReport = File.ReadAllText(ctxA.ReportPath(".blender.json"));
                var parsed = (Dictionary<string, object>)MiniJson.Parse(goodReport);
                // the Data folder this window uses holds an older result (other FBX, other texture names)
                MiniJson.Obj(parsed, "source")["fbxSha256"] = new string('0', 64);
                var tex = MiniJson.Obj(MiniJson.Obj(MiniJson.Obj(parsed, "checks"), "m1-9"), "values");
                tex["textures"] = new Dictionary<string, object> { { "Shovel_material", new List<object> { "Shovel_base_color_1024" } } };
                File.WriteAllText(ctxA.ReportPath(".blender.json"), MiniJson.Write(parsed));
                // ... while Blender wrote the current one into <project>/AssetGate
                var projectReport = Path.Combine(GateContext.ProjectDataFolder, "reports", ctxA.Pack, ctxA.Model + ".blender.json");
                Directory.CreateDirectory(Path.GetDirectoryName(projectReport));
                File.WriteAllText(projectReport, goodReport);
                var mismatch = MiniJson.Obj(MiniJson.Obj(GateChecks.Run(GateContext.ForAsset(fbx)), "checks"), "m2-1");
                output["otherFolderCheck"] = MiniJson.Str(mismatch, "status") + " | " + MiniJson.Str(mismatch, "detail");
                try { ModelSetup.Run(GateContext.ForAsset(fbx)); output["otherFolderSetup"] = "no error"; }
                catch (GateException e) { output["otherFolderSetup"] = e.Message; }
                File.Delete(projectReport);
                try { ModelSetup.Run(GateContext.ForAsset(fbx)); output["oldReportSetup"] = "no error"; }
                catch (GateException e) { output["oldReportSetup"] = e.Message; }
                File.WriteAllText(ctxA.ReportPath(".blender.json"), goodReport);
                output["goodReportProblem"] = GateContext.ForAsset(fbx).BlenderReportProblem() ?? "none";
            }
            // ---- Export to Unity delivers metallic-roughness already converted (no original in the project)
            var delivered = Arg("-agDelivered");
            if (delivered != null)
            {
                var original = kit + "/Textures/Shovel_metallic_roughness.png";
                var converted = GateContext.ConvertedPath(original);
                AssetDatabase.DeleteAsset(original);
                AssetDatabase.DeleteAsset(converted);
                File.Copy(delivered, converted);
                AssetDatabase.ImportAsset(converted);
                output["deliveredSrgbBefore"] = ((TextureImporter)AssetImporter.GetAtPath(converted)).sRGBTexture;
                ModelSetup.Run(GateContext.ForAsset(fbx));
                var ti = (TextureImporter)AssetImporter.GetAtPath(converted);
                output["deliveredSrgbAfter"] = ti.sRGBTexture;
                output["deliveredAlphaSource"] = ti.alphaSource.ToString();
                var deliveredChecks = MiniJson.Obj(GateChecks.Run(GateContext.ForAsset(fbx)), "checks");
                output["deliveredStatuses"] = string.Join(",", new[] { "m2-1", "m2-4", "m2-6" }.Select(id => id + "=" + MiniJson.Str(MiniJson.Obj(deliveredChecks, id), "status")));
                var deliveredMat = AssetDatabase.LoadAssetAtPath<Material>(kit + "/Materials/Shovel_material.mat");
                output["deliveredMetal"] = deliveredMat.GetTexture("_MetallicGlossMap") ? deliveredMat.GetTexture("_MetallicGlossMap").name : "none";
                output["deliveredOriginalBack"] = File.Exists(original);
            }
            output["ok"] = true;
        }
        catch (Exception e) { output["exception"] = e.ToString(); }
        finally
        {
            GateContext.SavedDataFolder = previous;
            Lang.Current = previousLanguage;
            Mode.Current = previousMode;
            File.WriteAllText(Arg("-agOut"), MiniJson.Write(output));
        }
    }
}
