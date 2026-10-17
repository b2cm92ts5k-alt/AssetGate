using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace ETLOLZ.AssetGate
{
    /// <summary>
    /// One-click setup of a model delivered by Blender's Export to Unity (SPEC D9):
    /// import settings, texture settings, URP/Lit material with textures, prefab with a box collider.
    /// Touches only this model's files under Assets/&lt;Pack&gt;/ and only when the user runs it.
    /// </summary>
    public static class ModelSetup
    {
        static readonly int BaseMap = Shader.PropertyToID("_BaseMap");
        static readonly int BumpMap = Shader.PropertyToID("_BumpMap");
        static readonly int MetallicGlossMap = Shader.PropertyToID("_MetallicGlossMap");
        static readonly int SmoothnessChannel = Shader.PropertyToID("_SmoothnessTextureChannel");
        static readonly int Smoothness = Shader.PropertyToID("_Smoothness");

        public static List<string> Run(GateContext ctx)
        {
            var done = new List<string>();
            var materialTextures = ctx.MaterialTextures();
            if (ctx.BlenderReport == null || materialTextures == null)
                throw new GateException(ctx.BlenderReportProblem() ?? Lang.T("err.noBlenderReport"));

            var unity = ctx.Unity;
            var shader = Shader.Find(MiniJson.Str(unity, "shader"));
            if (!shader) throw new GateException(Lang.T("err.noShader", MiniJson.Str(unity, "shader")));

            var missing = materialTextures.Values.SelectMany(v => v).Where(p => !ctx.TextureAvailable(p)).ToList();
            if (missing.Count > 0)
                throw new GateException(ctx.BlenderReportProblem() ?? Lang.T("err.texturesMissing", string.Join(", ", missing.Select(Path.GetFileName))));

            AssetDatabase.StartAssetEditing();
            var importer = (ModelImporter)AssetImporter.GetAtPath(ctx.FbxPath);
            try
            {
                ApplyModelImport(importer, MiniJson.Obj(unity, "modelImport"));
                done.Add(Lang.T("setup.model", Path.GetFileName(ctx.FbxPath)));
                foreach (var path in materialTextures.Values.SelectMany(v => v).Distinct().Where(p => AssetDatabase.LoadAssetAtPath<Texture2D>(p) != null))
                {
                    ApplyTextureImport(path, ctx.RoleOf(Path.GetFileNameWithoutExtension(path)));
                    done.Add(Lang.T("setup.texture", Path.GetFileName(path)));
                }
            }
            finally { AssetDatabase.StopAssetEditing(); }

            GateContext.EnsureAssetFolder(ctx.Folder("materialFolder"));
            foreach (var pair in materialTextures)
            {
                var material = SetupMaterial(ctx, shader, pair.Key, pair.Value, done);
                importer.AddRemap(new AssetImporter.SourceAssetIdentifier(typeof(Material), pair.Key), material);
            }
            importer.SaveAndReimport();
            done.Add(Lang.T("setup.remap"));

            SetupPrefab(ctx, done);
            AssetDatabase.SaveAssets();
            return done;
        }

        static void ApplyModelImport(ModelImporter importer, Dictionary<string, object> cfg)
        {
            importer.globalScale = (float)MiniJson.Num(cfg, "scaleFactor");
            importer.importNormals = Enum.TryParse(MiniJson.Str(cfg, "normals"), out ModelImporterNormals n) ? n : ModelImporterNormals.Import;
            importer.importTangents = TangentsFromConfig(MiniJson.Str(cfg, "tangents"));
            importer.meshCompression = Enum.TryParse(MiniJson.Str(cfg, "meshCompression"), out ModelImporterMeshCompression c) ? c : ModelImporterMeshCompression.Off;
            importer.isReadable = MiniJson.Bool(cfg, "readWrite") ?? false;
            importer.SaveAndReimport();
        }

        public static ModelImporterTangents TangentsFromConfig(string value)
        {
            switch (value)
            {
                case "Import": return ModelImporterTangents.Import;
                case "None": return ModelImporterTangents.None;
                default: return ModelImporterTangents.CalculateMikk;   // "Calculate" in the Inspector
            }
        }

        static void ApplyTextureImport(string path, string role)
        {
            var ti = (TextureImporter)AssetImporter.GetAtPath(path);
            ti.GetSourceTextureWidthAndHeight(out var w, out var h);
            ti.maxTextureSize = Mathf.NextPowerOfTwo(Mathf.Max(w, h));
            switch (role)
            {
                case "normalMap":
                    ti.textureType = TextureImporterType.NormalMap;
                    break;
                case "metallicRoughness":
                    ti.textureType = TextureImporterType.Default;
                    ti.sRGBTexture = false;
                    break;
                default:
                    ti.textureType = TextureImporterType.Default;
                    ti.sRGBTexture = true;
                    break;
            }
            ti.SaveAndReimport();
        }

        static Material SetupMaterial(GateContext ctx, Shader shader, string name, List<string> textures, List<string> done)
        {
            var path = ctx.Folder("materialFolder") + "/" + name + ".mat";
            var material = AssetDatabase.LoadAssetAtPath<Material>(path);
            var created = material == null;
            if (created)
            {
                material = new Material(shader) { name = name };
                AssetDatabase.CreateAsset(material, path);
            }
            material.shader = shader;

            foreach (var texPath in textures)
            {
                var role = ctx.RoleOf(Path.GetFileNameWithoutExtension(texPath));
                switch (role)
                {
                    case "baseMap":
                        material.SetTexture(BaseMap, AssetDatabase.LoadAssetAtPath<Texture2D>(texPath));
                        material.mainTexture = material.GetTexture(BaseMap);
                        break;
                    case "normalMap":
                        material.SetTexture(BumpMap, AssetDatabase.LoadAssetAtPath<Texture2D>(texPath));
                        material.EnableKeyword("_NORMALMAP");
                        break;
                    case "metallicRoughness":
                        // Export to Unity delivers it already converted (no original), and an original may have
                        // been removed after an earlier conversion (k3-7): then set up the converted file as it is.
                        string converted;
                        if (AssetDatabase.LoadAssetAtPath<Texture2D>(texPath) != null)
                            converted = ConvertMetallicRoughness(texPath, done);
                        else
                        {
                            converted = GateContext.ConvertedPath(texPath);
                            ApplyConvertedImport(converted);
                            done.Add(Lang.T("setup.texture", Path.GetFileName(converted)));
                        }
                        material.SetTexture(MetallicGlossMap, AssetDatabase.LoadAssetAtPath<Texture2D>(converted));
                        material.SetFloat(SmoothnessChannel, 0f);   // smoothness from the metallic map's alpha
                        material.SetFloat(Smoothness, 1f);          // acts as a multiplier when a map is set
                        material.EnableKeyword("_METALLICSPECGLOSSMAP");
                        break;
                }
            }
            EditorUtility.SetDirty(material);
            done.Add(Lang.T(created ? "setup.materialCreated" : "setup.materialUpdated", Path.GetFileName(path)));
            return material;
        }

        /// <summary>
        /// Meshy/glTF metallic-roughness (G = roughness, B = metallic) to URP metallic-smoothness
        /// (R = metallic, A = smoothness). Writes a new file next to the source; the source is untouched.
        /// </summary>
        public static string ConvertMetallicRoughness(string sourcePath, List<string> done)
        {
            var target = GateContext.ConvertedPath(sourcePath);
            var src = new Texture2D(2, 2, TextureFormat.RGBA32, false, true);
            src.LoadImage(File.ReadAllBytes(Path.GetFullPath(sourcePath)));
            var pixels = src.GetPixels32();
            for (var i = 0; i < pixels.Length; i++)
            {
                var p = pixels[i];
                pixels[i] = new Color32(p.b, 0, 0, (byte)(255 - p.g));
            }
            var dst = new Texture2D(src.width, src.height, TextureFormat.RGBA32, false, true);
            dst.SetPixels32(pixels);
            File.WriteAllBytes(Path.GetFullPath(target), dst.EncodeToPNG());
            UnityEngine.Object.DestroyImmediate(src);
            UnityEngine.Object.DestroyImmediate(dst);

            AssetDatabase.ImportAsset(target, ImportAssetOptions.ForceUpdate);
            ApplyConvertedImport(target);
            done.Add(Lang.T("setup.converted", Path.GetFileName(target)));
            return target;
        }

        /// <summary>Import settings of a metallic-smoothness map: linear, alpha from the file (= smoothness).</summary>
        static void ApplyConvertedImport(string path)
        {
            var ti = (TextureImporter)AssetImporter.GetAtPath(path);
            ti.textureType = TextureImporterType.Default;
            ti.sRGBTexture = false;
            ti.alphaSource = TextureImporterAlphaSource.FromInput;
            ti.alphaIsTransparency = false;
            ti.GetSourceTextureWidthAndHeight(out var w, out var h);
            ti.maxTextureSize = Mathf.NextPowerOfTwo(Mathf.Max(w, h));
            ti.SaveAndReimport();
        }

        static void SetupPrefab(GateContext ctx, List<string> done)
        {
            GateContext.EnsureAssetFolder(ctx.Folder("prefabFolder"));
            var path = ctx.Folder("prefabFolder") + "/" + ctx.Model + ".prefab";
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(ctx.FbxPath);

            if (AssetDatabase.LoadAssetAtPath<GameObject>(path) == null)
            {
                // Built in a preview scene so the user's open scene is never touched.
                var scene = UnityEditor.SceneManagement.EditorSceneManager.NewPreviewScene();
                try
                {
                    var instance = (GameObject)PrefabUtility.InstantiatePrefab(model, scene);
                    instance.name = ctx.Model;
                    FitBoxCollider(instance);
                    PrefabUtility.SaveAsPrefabAsset(instance, path);
                }
                finally { UnityEditor.SceneManagement.EditorSceneManager.ClosePreviewScene(scene); }
                done.Add(Lang.T("setup.prefabCreated", Path.GetFileName(path)));
                return;
            }

            var root = PrefabUtility.LoadPrefabContents(path);
            try
            {
                FitBoxCollider(root);
                PrefabUtility.SaveAsPrefabAsset(root, path);
            }
            finally { PrefabUtility.UnloadPrefabContents(root); }
            done.Add(Lang.T("setup.prefabUpdated", Path.GetFileName(path)));
        }

        /// <summary>Box collider on the root sized to all renderers (root-local space).</summary>
        static void FitBoxCollider(GameObject root)
        {
            var renderers = root.GetComponentsInChildren<Renderer>();
            if (renderers.Length == 0) return;
            var bounds = renderers[0].bounds;
            foreach (var r in renderers.Skip(1)) bounds.Encapsulate(r.bounds);
            var box = root.GetComponent<BoxCollider>();
            if (!box)
            {
                if (root.GetComponent<Collider>()) return;   // the user chose another collider type
                box = root.AddComponent<BoxCollider>();
            }
            box.center = root.transform.InverseTransformPoint(bounds.center);
            var scale = root.transform.lossyScale;
            box.size = new Vector3(bounds.size.x / scale.x, bounds.size.y / scale.y, bounds.size.z / scale.z);
        }
    }
}
