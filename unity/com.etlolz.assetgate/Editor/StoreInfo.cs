using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;

namespace ETLOLZ.AssetGate
{
    /// <summary>Game: models for your own game (Gate 1 + 2). Store: assets to sell (Gate 1 + 2 + 3) — SPEC D17.</summary>
    public static class Mode
    {
        const string Pref = "ETLOLZ.AssetGate.Mode";
        public static readonly string[] Codes = { "game", "store" };

        public static string Current
        {
            get => EditorPrefs.GetString(Pref, "game") == "store" ? "store" : "game";
            set => EditorPrefs.SetString(Pref, value == "store" ? "store" : "game");
        }

        public static bool Store => Current == "store";
    }

    /// <summary>
    /// Where a model came from, typed in the Asset Gate window in Store mode (m4-1 … m4-4, SPEC D19).
    /// Saved next to the report as &lt;Model&gt;.unity.store.json (owned by the Unity tool). The first time,
    /// values the user had typed in the checklist page (state.json, models[].lic) are offered instead.
    /// </summary>
    public class StoreInfo
    {
        public string Plan = "", GenDate = "", Manual = "";
        public bool FromChecklistPage;   // not saved yet: values came from state.json

        public static string PathFor(GateContext ctx) => ctx.ReportPath(".unity.store.json");

        public static StoreInfo Load(GateContext ctx)
        {
            var saved = GateContext.ReadJson(PathFor(ctx));
            if (saved != null)
                return new StoreInfo { Plan = MiniJson.Str(saved, "plan", ""), GenDate = MiniJson.Str(saved, "genDate", ""), Manual = MiniJson.Str(saved, "manual", "") };
            return FromState(ctx) ?? new StoreInfo();
        }

        static StoreInfo FromState(GateContext ctx)
        {
            var models = MiniJson.Obj(GateContext.ReadJson(Path.Combine(ctx.DataFolder, "state.json")), "models");
            if (models == null) return null;
            foreach (var model in models.Values.OfType<Dictionary<string, object>>())
            {
                if ((MiniJson.Str(model, "name", "") ?? "").Trim() != ctx.Model || (MiniJson.Str(model, "pack", "") ?? "").Trim() != ctx.Pack) continue;
                var lic = MiniJson.Obj(model, "lic");
                return new StoreInfo
                {
                    Plan = MiniJson.Str(lic, "plan", ""), GenDate = MiniJson.Str(lic, "genDate", ""), Manual = MiniJson.Str(lic, "manual", ""),
                    FromChecklistPage = true,
                };
            }
            return null;
        }

        public void Save(GateContext ctx)
        {
            var data = new Dictionary<string, object>
            {
                { "schema", 1 }, { "tool", "unity" }, { "pack", ctx.Pack }, { "model", ctx.Model },
                { "plan", Plan ?? "" }, { "genDate", GenDate ?? "" }, { "manual", Manual ?? "" },
            };
            var path = PathFor(ctx);
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            var tmp = path + ".tmp";
            File.WriteAllText(tmp, MiniJson.Write(data) + "\n");
            if (File.Exists(path)) File.Delete(path);
            File.Move(tmp, path);
            FromChecklistPage = false;
        }

        static Dictionary<string, object> Result(string status, string detail, Dictionary<string, object> values) =>
            new Dictionary<string, object> { { "status", status }, { "detail", detail ?? "" }, { "values", values } };

        /// <summary>m4-1 … m4-4. Game mode: not relevant (na). Review items reset when what they confirm changes.</summary>
        public static void AddChecks(GateContext ctx, Dictionary<string, object> checks)
        {
            if (!Mode.Store)
            {
                foreach (var id in new[] { "m4-1", "m4-2", "m4-3", "m4-4" })
                    checks[id] = Result("na", Lang.T("res.gameMode"), new Dictionary<string, object>());
                return;
            }
            var info = Load(ctx);
            var saved = File.Exists(PathFor(ctx));
            checks["m4-1"] = string.IsNullOrWhiteSpace(info.Plan) || !saved
                ? Result("fail", Lang.T("res.m4Fill"), new Dictionary<string, object>())
                : Result("review", Lang.T("res.m4-1", info.Plan), new Dictionary<string, object> { { "plan", info.Plan } });
            checks["m4-2"] = Result("review", Lang.T("res.m4-2"), new Dictionary<string, object> { { "plan", info.Plan }, { "genDate", info.GenDate } });
            checks["m4-3"] = Result("review", Lang.T("res.m4-3"), new Dictionary<string, object>());
            checks["m4-4"] = !saved ? Result("fail", Lang.T("res.m4Fill"), new Dictionary<string, object>())
                : string.IsNullOrWhiteSpace(info.Manual) ? Result("fail", Lang.T("res.m4Manual"), new Dictionary<string, object>())
                : Result("pass", "", new Dictionary<string, object> { { "manual", info.Manual.Trim() } });
        }
    }
}
