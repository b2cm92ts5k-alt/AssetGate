using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace ETLOLZ.AssetGate
{
    /// <summary>
    /// Polygon counts of the imported model and which kind of work they suit (SPEC D22). Display only:
    /// m1-16 is confirmed in Blender. Same guidance as Blender (config polycount); the model type and
    /// platform come from the Blender report's m1-16 values.
    /// </summary>
    public static class Polycount
    {
        public struct Counts { public int Tris, Verts, Meshes; }

        /// <summary>Triangles and GPU vertices of every mesh under the root (MeshFilter + SkinnedMeshRenderer).</summary>
        public static Counts Of(GameObject root)
        {
            var c = new Counts();
            if (!root) return c;
            var meshes = root.GetComponentsInChildren<MeshFilter>(true).Select(f => f.sharedMesh)
                .Concat(root.GetComponentsInChildren<SkinnedMeshRenderer>(true).Select(r => r.sharedMesh))
                .Where(m => m);
            foreach (var mesh in meshes)
            {
                c.Meshes++;
                c.Verts += mesh.vertexCount;
                for (var i = 0; i < mesh.subMeshCount; i++)
                    if (mesh.GetTopology(i) == MeshTopology.Triangles) c.Tris += (int)(mesh.GetIndexCount(i) / 3);
            }
            return c;
        }

        static string N(double n) => n.ToString("N0");

        /// <summary>One-paragraph advice, the same reasoning as Blender's mesh_checks.polycount_advice.</summary>
        public static string Advice(Dictionary<string, object> config, int tris, string assetType, string platform)
        {
            var guide = MiniJson.Obj(config, "polycount");
            if (guide == null) return "";
            var tier = MiniJson.Arr(guide, "tiers").OfType<Dictionary<string, object>>()
                .FirstOrDefault(t => !(t.TryGetValue("max", out var max) && max is double m) || tris <= m);
            var tierKey = MiniJson.Str(tier, "key", "veryHigh");
            var parts = new List<string> { Lang.T("poly.tier", N(tris), Lang.T("tier." + tierKey), Lang.T("tierHint." + tierKey)) };
            var byType = MiniJson.Obj(guide, "byType") ?? new Dictionary<string, object>();

            if (!string.IsNullOrEmpty(assetType) && assetType != "none" && !string.IsNullOrEmpty(platform) && platform != "none")
            {
                var plat = platform == "vr" ? MiniJson.Str(guide, "vrUses", "mobile") : platform;
                var span = MiniJson.Arr(MiniJson.Obj(byType, assetType), plat);
                string type = Lang.T("type." + assetType), where = Lang.T("platform." + platform);
                if (span == null || span.Count != 2) parts.Add(Lang.T("poly.noGuide", type, where));
                else
                {
                    double lo = (double)span[0], hi = (double)span[1];
                    var fit = tris < lo ? "below" : tris > hi ? "above" : "within";
                    parts.Add(Lang.T("poly." + fit, N(lo), N(hi), type, where));
                }
            }
            else
            {
                var fits = new List<string>();
                double lowest = double.MaxValue;
                foreach (var kind in byType)
                    foreach (var plat in (kind.Value as Dictionary<string, object>) ?? new Dictionary<string, object>())
                        if (plat.Value is List<object> s && s.Count == 2)
                        {
                            lowest = System.Math.Min(lowest, (double)s[0]);
                            if (tris >= (double)s[0] && tris <= (double)s[1]) fits.Add(Lang.T("type." + kind.Key) + " (" + Lang.T("platform." + plat.Key) + ")");
                        }
                parts.Add(fits.Count > 0 ? Lang.T("poly.fits", string.Join(", ", fits.Take(4)) + (fits.Count > 4 ? " …" : ""))
                    : tris < lowest ? Lang.T("poly.fitsTiny") : Lang.T("poly.fitsNone"));
            }
            if (platform == "vr")
            {
                var budget = MiniJson.Obj(guide, "vrSceneBudget");
                parts.Add(Lang.T("poly.vr", N(MiniJson.Num(budget, "quest2", 0)), N(MiniJson.Num(budget, "quest3", 0))));
            }
            return string.Join(" · ", parts);
        }
    }
}
