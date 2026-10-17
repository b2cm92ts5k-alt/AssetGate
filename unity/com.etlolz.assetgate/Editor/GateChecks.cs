using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

namespace ETLOLZ.AssetGate
{
    /// <summary>
    /// Gate 2 checks (SPEC §5: m2-*, m3-* except the manual m3-4). Read-only towards the user's assets:
    /// it reimports the model to capture console output and renders a screenshot in a preview scene.
    /// </summary>
    public static class GateChecks
    {
        public const string ToolVersion = "1.0.0";
        const float FloatEps = 1e-4f;

        public static readonly string[] Order =
        {
            "m2-1", "m2-2", "m2-3", "m2-4", "m2-5", "m2-6", "m2-7", "m2-8", "m2-9", "m2-10", "m2-11", "m2-12",
            "m3-1", "m3-2", "m3-3", "m3-4", "m3-5", "m3-6", "m3-7", "m3-8",
            "m4-1", "m4-2", "m4-3", "m4-4",
        };

        public static string Title(string id) => Lang.T("title." + id);

        static Dictionary<string, object> Result(string status, string detail, Dictionary<string, object> values = null)
        {
            return new Dictionary<string, object>
            {
                { "status", status }, { "detail", detail ?? "" }, { "values", values ?? new Dictionary<string, object>() },
            };
        }

        static Dictionary<string, object> V(params object[] kv)
        {
            var d = new Dictionary<string, object>();
            for (var i = 0; i + 1 < kv.Length; i += 2) d[(string)kv[i]] = kv[i + 1];
            return d;
        }

        class Model
        {
            public GateContext Ctx;
            public ModelImporter Importer;
            public GameObject Asset;
            public List<Material> Materials = new List<Material>();
            public string PrefabPath;
            public Bounds Bounds;
            public List<string> ConsoleErrors = new List<string>();
            public List<string> ConsoleWarnings = new List<string>();
            public string ScreenshotPath;
            public string ScreenshotError;
        }

        /// <summary>Run every Gate 2 check and write reports/&lt;Pack&gt;/&lt;Model&gt;.unity.json. Returns the report.</summary>
        public static Dictionary<string, object> Run(GateContext ctx)
        {
            var m = new Model { Ctx = ctx, Importer = AssetImporter.GetAtPath(ctx.FbxPath) as ModelImporter };
            CaptureReimport(m);
            m.Asset = AssetDatabase.LoadAssetAtPath<GameObject>(ctx.FbxPath);
            if (m.Asset)
            {
                foreach (var r in m.Asset.GetComponentsInChildren<Renderer>())
                    foreach (var mat in r.sharedMaterials)
                        if (mat && !m.Materials.Contains(mat)) m.Materials.Add(mat);
                m.Bounds = RendererBounds(m.Asset);
            }
            m.PrefabPath = ctx.Folder("prefabFolder") + "/" + ctx.Model + ".prefab";
            RenderScreenshot(m);

            var checks = new Dictionary<string, object>();
            void Add(string id, Func<Dictionary<string, object>> check)
            {
                try { checks[id] = check(); }
                catch (Exception e) { checks[id] = Result("fail", Lang.T("res.crashed", e.GetType().Name + ": " + e.Message)); }
            }
            Add("m2-1", () => CheckImported(m));
            Add("m2-2", () => CheckModelImport(m));
            Add("m2-3", () => CheckExternalMaterials(m));
            Add("m2-4", () => CheckTextureImport(m));
            Add("m2-5", () => CheckShader(m));
            Add("m2-6", () => CheckSlots(m));
            Add("m2-7", () => CheckSmoothness(m));
            Add("m2-8", () => CheckSurface(m));
            Add("m2-9", CheckUrpAsset);
            Add("m2-10", () => CheckPrefab(m));
            Add("m2-11", () => CheckCollider(m));
            Add("m2-12", () => CheckLod(m));
            Add("m3-1", CheckColorSpace);
            Add("m3-2", () => m.ScreenshotPath != null
                ? Result("pass", "", V("settings", "unity.testScene", "width", MiniJson.Num(MiniJson.Obj(ctx.Unity, "testScene"), "width"), "height", MiniJson.Num(MiniJson.Obj(ctx.Unity, "testScene"), "height")))
                : Result("fail", Lang.T("res.sceneFailed", m.ScreenshotError)));
            Add("m3-3", () => CheckNormalMap(m));
            // m3-4: only a person can see z-fighting / artifacts; the confirmation resets when the FBX changes (SPEC D19)
            Add("m3-4", () => Result("review", Lang.T("res.m3-4"), V("fbxSha256", GateContext.Sha256(ctx.FbxPath))));
            Add("m3-5", () => CheckScale(m));
            Add("m3-6", () => CheckPivot(m));
            Add("m3-7", () => CheckConsole(m));
            Add("m3-8", () => m.ScreenshotPath != null
                ? Result("pass", "", V("path", m.ScreenshotPath))
                : Result("fail", Lang.T("res.shotFailed", m.ScreenshotError)));

            StoreInfo.AddChecks(ctx, checks);

            var report = new Dictionary<string, object>
            {
                { "schema", 1 }, { "tool", "unity" }, { "toolVersion", ToolVersion }, { "scope", "model" },
                { "pack", ctx.Pack }, { "model", ctx.Model },
                { "checkedAt", DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ") },
                { "source", V("fbxPath", ctx.FbxPath, "fbxSha256", GateContext.Sha256(ctx.FbxPath)) },
                { "checks", checks },
            };
            var path = ctx.ReportPath(".unity.json");
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            var tmp = path + ".tmp";
            File.WriteAllText(tmp, MiniJson.Write(report) + "\n");
            if (File.Exists(path)) File.Delete(path);
            File.Move(tmp, path);
            Confirms.Prune(path);
            return report;
        }

        // ---------- capture ----------

        static void CaptureReimport(Model m)
        {
            if (m.Importer == null) return;
            Application.LogCallback handler = (message, stack, type) =>
            {
                if (type == LogType.Warning) m.ConsoleWarnings.Add(message);
                else if (type != LogType.Log) m.ConsoleErrors.Add(message);
            };
            Application.logMessageReceived += handler;
            try
            {
                AssetDatabase.ImportAsset(m.Ctx.FbxPath, ImportAssetOptions.ForceUpdate);
                var textures = m.Ctx.MaterialTextures();
                if (textures != null)
                    foreach (var t in textures.Values.SelectMany(v => v).Distinct().Where(File.Exists))
                        AssetDatabase.ImportAsset(t, ImportAssetOptions.ForceUpdate);
            }
            finally { Application.logMessageReceived -= handler; }
        }

        static Bounds RendererBounds(GameObject go)
        {
            var renderers = go.GetComponentsInChildren<Renderer>();
            if (renderers.Length == 0) return new Bounds();
            var b = renderers[0].bounds;
            foreach (var r in renderers.Skip(1)) b.Encapsulate(r.bounds);
            return b;
        }

        static void RenderScreenshot(Model m)
        {
            if (!m.Asset) { m.ScreenshotError = Lang.T("res.loadFailed"); return; }
            var cfg = MiniJson.Obj(m.Ctx.Unity, "testScene");
            int width = (int)MiniJson.Num(cfg, "width"), height = (int)MiniJson.Num(cfg, "height");
            var scene = EditorSceneManager.NewPreviewScene();
            var rt = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32) { antiAliasing = 4 };
            Texture2D image = null;
            try
            {
                var instance = (GameObject)PrefabUtility.InstantiatePrefab(m.Asset, scene);
                var bounds = RendererBounds(instance);

                var lightGo = new GameObject("Asset Gate Light");
                SceneManager.MoveGameObjectToScene(lightGo, scene);
                var light = lightGo.AddComponent<Light>();
                light.type = LightType.Directional;
                light.intensity = (float)MiniJson.Num(cfg, "lightIntensity");
                var rot = MiniJson.Arr(cfg, "lightRotation").Select(v => (float)(double)v).ToArray();
                lightGo.transform.rotation = Quaternion.Euler(rot[0], rot[1], rot[2]);

                var camGo = new GameObject("Asset Gate Camera");
                SceneManager.MoveGameObjectToScene(camGo, scene);
                var cam = camGo.AddComponent<Camera>();
                cam.scene = scene;
                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = new Color(0.32f, 0.33f, 0.35f);
                cam.fieldOfView = 30f;
                cam.aspect = (float)width / height;
                // 3/4 view framed to the model's bounding sphere
                var dir = Quaternion.Euler((float)MiniJson.Num(cfg, "pitch"), (float)MiniJson.Num(cfg, "yaw"), 0f) * Vector3.back;
                var radius = Mathf.Max(bounds.extents.magnitude, 0.01f);
                var distance = radius / Mathf.Sin(Mathf.Deg2Rad * cam.fieldOfView * 0.5f) * 1.1f;
                cam.transform.position = bounds.center + dir * distance;
                cam.transform.LookAt(bounds.center);
                cam.nearClipPlane = Mathf.Max(0.01f, distance - radius * 2f);
                cam.farClipPlane = distance + radius * 2f;
                cam.targetTexture = rt;

                var request = new RenderPipeline.StandardRequest { destination = rt };
                if (RenderPipeline.SupportsRenderRequest(cam, request)) RenderPipeline.SubmitRenderRequest(cam, request);
                else cam.Render();

                var previous = RenderTexture.active;
                RenderTexture.active = rt;
                image = new Texture2D(width, height, TextureFormat.RGB24, false);
                image.ReadPixels(new Rect(0, 0, width, height), 0, 0);
                image.Apply();
                RenderTexture.active = previous;

                var path = Path.Combine(m.Ctx.DataFolder, "screenshots", m.Ctx.Pack, m.Ctx.Model + ".png");
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                File.WriteAllBytes(path, image.EncodeToPNG());
                m.ScreenshotPath = path;
                cam.targetTexture = null;
            }
            catch (Exception e) { m.ScreenshotError = e.Message; }
            finally
            {
                if (image) UnityEngine.Object.DestroyImmediate(image);
                rt.Release();
                UnityEngine.Object.DestroyImmediate(rt);
                EditorSceneManager.ClosePreviewScene(scene);
            }
        }

        // ---------- textures by slot ----------

        static IEnumerable<(Material mat, string slot, Texture tex)> SlotTextures(Model m)
        {
            foreach (var mat in m.Materials)
                foreach (var slot in new[] { "_BaseMap", "_BumpMap", "_MetallicGlossMap" })
                    if (mat.HasProperty(slot) && mat.GetTexture(slot))
                        yield return (mat, slot, mat.GetTexture(slot));
        }

        // ---------- checks ----------

        static Dictionary<string, object> CheckImported(Model m)
        {
            if (m.Importer == null || !m.Asset) return Result("fail", Lang.T("res.notImported"));
            var textures = m.Ctx.MaterialTextures();
            if (textures == null) return Result("fail", m.Ctx.BlenderReportProblem() ?? Lang.T("res.noBlender"));
            var all = textures.Values.SelectMany(v => v).Distinct().ToList();
            var missing = all.Where(p => !m.Ctx.TextureAvailable(p)).Select(Path.GetFileName).ToList();
            if (missing.Count > 0) return Result("fail", m.Ctx.BlenderReportProblem() ?? Lang.T("res.textureMissing", string.Join(", ", missing)), V("missing", missing));
            return Result("pass", "", V("fbx", m.Ctx.FbxPath, "textures", all.Count));
        }

        static Dictionary<string, object> CheckModelImport(Model m)
        {
            if (m.Importer == null) return Result("fail", Lang.T("res.noImporter"));
            var cfg = MiniJson.Obj(m.Ctx.Unity, "modelImport");
            var problems = new List<string>();
            var want = (float)MiniJson.Num(cfg, "scaleFactor");
            if (Mathf.Abs(m.Importer.globalScale - want) > FloatEps) problems.Add(Lang.T("res.mustBe", "Scale Factor", m.Importer.globalScale.ToString("g"), want.ToString("g")));
            if (m.Importer.importNormals.ToString() != MiniJson.Str(cfg, "normals")) problems.Add(Lang.T("res.mustBe", "Normals", m.Importer.importNormals, MiniJson.Str(cfg, "normals")));
            var tangents = ModelSetup.TangentsFromConfig(MiniJson.Str(cfg, "tangents"));
            if (m.Importer.importTangents != tangents) problems.Add(Lang.T("res.mustBe", "Tangents", m.Importer.importTangents, tangents));
            if (m.Importer.meshCompression.ToString() != MiniJson.Str(cfg, "meshCompression")) problems.Add(Lang.T("res.mustBe", "Mesh Compression", m.Importer.meshCompression, MiniJson.Str(cfg, "meshCompression")));
            if (m.Importer.isReadable != (MiniJson.Bool(cfg, "readWrite") ?? false)) problems.Add(Lang.T("res.mustBe", "Read/Write", Lang.T(m.Importer.isReadable ? "res.on" : "res.off"), Lang.T((MiniJson.Bool(cfg, "readWrite") ?? false) ? "res.on" : "res.off")));
            var values = V("scaleFactor", m.Importer.globalScale, "normals", m.Importer.importNormals.ToString(),
                "tangents", m.Importer.importTangents.ToString(), "meshCompression", m.Importer.meshCompression.ToString(), "readWrite", m.Importer.isReadable);
            return problems.Count > 0 ? Result("fail", Lang.T("res.pressSetup", string.Join(" · ", problems)), values) : Result("pass", "", values);
        }

        static Dictionary<string, object> CheckExternalMaterials(Model m)
        {
            if (m.Materials.Count == 0) return Result("fail", Lang.T("res.noMaterial"));
            var embedded = m.Materials.Where(mat => AssetDatabase.GetAssetPath(mat) == m.Ctx.FbxPath).Select(mat => mat.name).ToList();
            if (embedded.Count > 0) return Result("fail", Lang.T("res.pressSetup", Lang.T("res.embedded", string.Join(", ", embedded))), V("embedded", embedded));
            return Result("pass", "", V("materials", m.Materials.Select(AssetDatabase.GetAssetPath).ToList()));
        }

        static Dictionary<string, object> CheckTextureImport(Model m)
        {
            var slots = SlotTextures(m).ToList();
            if (slots.Count == 0) return Result("fail", Lang.T("res.pressSetup", Lang.T("res.noTextures")));
            var want = (int)MiniJson.Num(m.Ctx.BlenderReport != null ? MiniJson.Obj(m.Ctx.BlenderReport, "stats") : null, "tex", 0);
            var problems = new List<string>();
            foreach (var (_, slot, tex) in slots)
            {
                var ti = AssetImporter.GetAtPath(AssetDatabase.GetAssetPath(tex)) as TextureImporter;
                if (ti == null) continue;
                var name = tex.name;
                if (slot == "_BumpMap" && ti.textureType != TextureImporterType.NormalMap) problems.Add(Lang.T("res.needNormal", name));
                if (slot == "_BaseMap" && !ti.sRGBTexture) problems.Add(Lang.T("res.needSrgb", name));
                if (slot == "_MetallicGlossMap" && ti.sRGBTexture) problems.Add(Lang.T("res.needLinear", name));
                if (want > 0 && ti.maxTextureSize < want) problems.Add(Lang.T("res.maxSize", name, ti.maxTextureSize, want));
            }
            var values = V("textures", slots.Count, "maxSizeWanted", want);
            return problems.Count > 0 ? Result("fail", string.Join(" · ", problems), values) : Result("pass", "", values);
        }

        static Dictionary<string, object> CheckShader(Model m)
        {
            var want = MiniJson.Str(m.Ctx.Unity, "shader");
            var wrong = m.Materials.Where(mat => !mat.shader || mat.shader.name != want).Select(mat => mat.name + " (" + (mat.shader ? mat.shader.name : Lang.T("res.noShader")) + ")").ToList();
            if (m.Materials.Count == 0) return Result("fail", Lang.T("res.noMaterial"));
            return wrong.Count > 0 ? Result("fail", Lang.T("res.wrongShader", want, string.Join(", ", wrong)), V("wrong", wrong)) : Result("pass", "", V("shader", want));
        }

        static Dictionary<string, object> CheckSlots(Model m)
        {
            var textures = m.Ctx.MaterialTextures();
            if (textures == null) return Result("fail", Lang.T("res.noBlenderShort"));
            var problems = new List<string>();
            foreach (var mat in m.Materials)
            {
                if (!textures.TryGetValue(mat.name, out var expected)) continue;
                var roles = expected.Select(p => m.Ctx.RoleOf(Path.GetFileNameWithoutExtension(p))).ToList();
                if (roles.Contains("baseMap") && (!mat.HasProperty("_BaseMap") || !mat.GetTexture("_BaseMap"))) problems.Add(Lang.T("res.missingMap", mat.name, "Base Map"));
                if (roles.Contains("normalMap") && (!mat.HasProperty("_BumpMap") || !mat.GetTexture("_BumpMap"))) problems.Add(Lang.T("res.missingMap", mat.name, "Normal Map"));
                if (roles.Contains("metallicRoughness") && (!mat.HasProperty("_MetallicGlossMap") || !mat.GetTexture("_MetallicGlossMap"))) problems.Add(Lang.T("res.missingMap", mat.name, "Metallic Map"));
            }
            foreach (var (mat, slot, tex) in SlotTextures(m))
            {
                var role = m.Ctx.RoleOf(tex.name);
                var expectedSlot = role == "normalMap" ? "_BumpMap" : role == "metallicRoughness" ? "_MetallicGlossMap" : role == "baseMap" ? "_BaseMap" : null;
                if (expectedSlot != null && expectedSlot != slot) problems.Add(Lang.T("res.wrongSlot", mat.name, tex.name, slot));
            }
            if (m.Materials.Count == 0) problems.Add(Lang.T("res.noMaterial"));
            var values = V("slots", SlotTextures(m).Select(s => s.slot + "=" + s.tex.name).ToList());
            return problems.Count > 0 ? Result("fail", Lang.T("res.pressSetup", string.Join(" · ", problems)), values) : Result("pass", "", values);
        }

        static Dictionary<string, object> CheckSmoothness(Model m)
        {
            var parts = new List<string>();
            foreach (var mat in m.Materials.Where(x => x.HasProperty("_Smoothness")))
            {
                var map = mat.HasProperty("_MetallicGlossMap") ? mat.GetTexture("_MetallicGlossMap") : null;
                var channel = mat.HasProperty("_SmoothnessTextureChannel") ? mat.GetFloat("_SmoothnessTextureChannel") : 0f;
                parts.Add(map && channel < 0.5f
                    ? Lang.T("res.smoothMap", mat.name, map.name, mat.GetFloat("_Smoothness").ToString("0.##"))
                    : Lang.T("res.smoothValue", mat.name, mat.GetFloat("_Smoothness").ToString("0.##")));
            }
            if (parts.Count == 0) return Result("fail", Lang.T("res.noUrpMaterial"));
            return Result("review", Lang.T("res.smoothReview", string.Join(" · ", parts)), V("materials", parts.Count));
        }

        static Dictionary<string, object> CheckSurface(Model m)
        {
            var parts = new List<string>();
            foreach (var mat in m.Materials.Where(x => x.HasProperty("_Surface")))
            {
                var transparent = mat.GetFloat("_Surface") > 0.5f;
                var baseMap = mat.HasProperty("_BaseMap") ? mat.GetTexture("_BaseMap") : null;
                var ti = baseMap ? AssetImporter.GetAtPath(AssetDatabase.GetAssetPath(baseMap)) as TextureImporter : null;
                var alpha = ti != null && ti.DoesSourceTextureHaveAlpha();
                parts.Add($"{mat.name}: {(transparent ? "Transparent" : "Opaque")}" + (alpha ? Lang.T("res.baseAlpha") : ""));
            }
            if (parts.Count == 0) return Result("fail", Lang.T("res.noUrpMaterial"));
            return Result("review", string.Join(" · ", parts), V("materials", parts.Count));
        }

        static Dictionary<string, object> CheckUrpAsset()
        {
            var pipeline = GraphicsSettings.defaultRenderPipeline;
            var isUrp = pipeline && pipeline.GetType().Name.Contains("Universal");
            var levels = new List<string>();
            var names = QualitySettings.names;
            for (var i = 0; i < names.Length; i++)
            {
                var q = QualitySettings.GetRenderPipelineAssetAt(i);
                if (q && !q.GetType().Name.Contains("Universal")) levels.Add(names[i]);
            }
            var values = V("graphics", pipeline ? pipeline.name : "none");
            if (!isUrp) return Result("fail", Lang.T("res.noUrpAsset"), values);
            if (levels.Count > 0) return Result("fail", Lang.T("res.nonUrpQuality", string.Join(", ", levels)), values);
            return Result("pass", "", values);
        }

        static Dictionary<string, object> CheckPrefab(Model m)
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(m.PrefabPath);
            if (!prefab) return Result("fail", Lang.T("res.pressSetup", Lang.T("res.noPrefab", m.PrefabPath)));
            var problems = new List<string>();
            if (prefab.name != m.Ctx.Model) problems.Add(Lang.T("res.prefabName"));
            var missingScripts = prefab.GetComponentsInChildren<Transform>(true).Sum(t => GameObjectUtility.GetMonoBehavioursWithMissingScriptCount(t.gameObject));
            if (missingScripts > 0) problems.Add(Lang.T("res.missingScripts", missingScripts));
            var emptySlots = prefab.GetComponentsInChildren<Renderer>(true).Sum(r => r.sharedMaterials.Count(x => !x));
            if (emptySlots > 0) problems.Add(Lang.T("res.emptySlots", emptySlots));
            var noMesh = prefab.GetComponentsInChildren<MeshFilter>(true).Count(f => !f.sharedMesh);
            if (noMesh > 0) problems.Add(Lang.T("res.noMeshCount", noMesh));
            var values = V("path", m.PrefabPath);
            return problems.Count > 0 ? Result("fail", string.Join(" · ", problems), values) : Result("pass", "", values);
        }

        static Dictionary<string, object> CheckCollider(Model m)
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(m.PrefabPath);
            if (!prefab) return Result("fail", Lang.T("res.pressSetup", Lang.T("res.noPrefab", m.PrefabPath)));
            var colliders = prefab.GetComponentsInChildren<Collider>(true);
            if (colliders.Length == 0) return Result("fail", Lang.T("res.pressSetup", Lang.T("res.noCollider")));
            var box = colliders.OfType<BoxCollider>().FirstOrDefault();
            if (!box) return Result("review", Lang.T("res.otherCollider", colliders[0].GetType().Name), V("type", colliders[0].GetType().Name));

            var tolerance = (float)MiniJson.Num(MiniJson.Obj(m.Ctx.Config, "collider"), "boundsTolerancePercent") / 100f;
            var renderBounds = RendererBounds(prefab);
            var boxSize = Vector3.Scale(box.size, box.transform.lossyScale);
            var worst = 0f;
            for (var i = 0; i < 3; i++)
            {
                var r = Mathf.Max(renderBounds.size[i], 0.001f);
                worst = Mathf.Max(worst, Mathf.Abs(boxSize[i] - renderBounds.size[i]) / r);
            }
            var values = V("type", "BoxCollider", "size", new List<object> { boxSize.x, boxSize.y, boxSize.z },
                "bounds", new List<object> { renderBounds.size.x, renderBounds.size.y, renderBounds.size.z }, "diffPercent", Math.Round(worst * 100, 1));
            return worst > tolerance
                ? Result("fail", Lang.T("res.pressSetup", Lang.T("res.colliderSize", (worst * 100).ToString("0.#"), (tolerance * 100).ToString("0.#"))), values)
                : Result("pass", "", values);
        }

        static Dictionary<string, object> CheckLod(Model m)
        {
            if (!m.Asset) return Result("fail", Lang.T("res.loadFailed"));
            var lodMeshes = m.Asset.GetComponentsInChildren<MeshFilter>(true).Count(f => f.name.IndexOf("_LOD", StringComparison.OrdinalIgnoreCase) >= 0);
            if (lodMeshes == 0) return Result("na", Lang.T("res.noLod"));
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(m.PrefabPath);
            return prefab && prefab.GetComponentInChildren<LODGroup>(true)
                ? Result("pass", "", V("lodMeshes", lodMeshes))
                : Result("fail", Lang.T("res.lodMissing", lodMeshes), V("lodMeshes", lodMeshes));
        }

        static Dictionary<string, object> CheckColorSpace()
        {
            var cs = PlayerSettings.colorSpace.ToString();
            return cs == "Linear" ? Result("pass", "", V("colorSpace", cs)) : Result("fail", Lang.T("res.colorSpace", cs), V("colorSpace", cs));
        }

        static Dictionary<string, object> CheckNormalMap(Model m)
        {
            var hasNormal = SlotTextures(m).Any(s => s.slot == "_BumpMap");
            return hasNormal
                ? Result("review", Lang.T("res.normalReview"), V("screenshot", m.ScreenshotPath ?? ""))
                : Result("na", Lang.T("res.noNormal"));
        }

        static Dictionary<string, object> CheckScale(Model m)
        {
            if (!m.Asset) return Result("fail", Lang.T("res.loadFailed"));
            var s = m.Bounds.size;
            return Result("review", Lang.T("res.size", s.x.ToString("0.###"), s.y.ToString("0.###"), s.z.ToString("0.###")), V("size", new List<object> { s.x, s.y, s.z }));
        }

        static Dictionary<string, object> CheckPivot(Model m)
        {
            if (!m.Asset) return Result("fail", Lang.T("res.loadFailed"));
            var b = m.Bounds;
            var baseCenter = new Vector3(b.center.x, b.min.y, b.center.z);
            var offset = m.Asset.transform.position - baseCenter;
            var values = V("offset", Math.Round(offset.magnitude, 4), "offsets", new List<object> { offset.x, offset.y, offset.z });
            return offset.magnitude <= FloatEps
                ? Result("pass", "", values)
                : Result("review", Lang.T("res.pivot", offset.magnitude.ToString("0.###")), values);
        }

        static Dictionary<string, object> CheckConsole(Model m)
        {
            var values = V("errors", m.ConsoleErrors.Count, "warnings", m.ConsoleWarnings.Count,
                "messages", m.ConsoleErrors.Concat(m.ConsoleWarnings).Take(5).ToList());
            if (m.ConsoleErrors.Count + m.ConsoleWarnings.Count == 0) return Result("pass", "", values);
            return Result("fail", Lang.T("res.console", m.ConsoleErrors.Count, m.ConsoleWarnings.Count, m.ConsoleErrors.Concat(m.ConsoleWarnings).FirstOrDefault() ?? ""), values);
        }
    }
}
