using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace ETLOLZ.AssetGate
{
    /// <summary>
    /// Review items confirmed in the Asset Gate window (SPEC D11). Stored next to the report:
    /// &lt;Model&gt;.unity.json → &lt;Model&gt;.unity.confirms.json, _pack.unity.json → _pack.unity.confirms.json.
    /// A confirmation counts only while the check is still "review" with the values that were confirmed.
    /// </summary>
    public static class Confirms
    {
        public static string PathFor(string reportPath) =>
            reportPath.Substring(0, reportPath.Length - ".json".Length) + ".confirms.json";

        static Dictionary<string, object> ReadReport(string reportPath)
        {
            try { return File.Exists(reportPath) ? MiniJson.Parse(File.ReadAllText(reportPath)) as Dictionary<string, object> : null; }
            catch (Exception) { return null; }
        }

        static Dictionary<string, object> Load(string reportPath)
        {
            try
            {
                var path = PathFor(reportPath);
                var data = File.Exists(path) ? MiniJson.Parse(File.ReadAllText(path)) as Dictionary<string, object> : null;
                return MiniJson.Obj(data, "confirms") ?? new Dictionary<string, object>();
            }
            catch (Exception) { return new Dictionary<string, object>(); }
        }

        /// <summary>Values compared as written JSON; both sides come from parsed files, so numbers format the same.</summary>
        static bool Matches(Dictionary<string, object> report, string id, object entry)
        {
            var check = MiniJson.Obj(MiniJson.Obj(report, "checks"), id);
            return check != null && MiniJson.Str(check, "status") == "review"
                && MiniJson.Write(MiniJson.Obj(check, "values")) == MiniJson.Write(MiniJson.Obj(entry, "values"));
        }

        /// <summary>Check ids whose confirmation still matches the report on disk.</summary>
        public static HashSet<string> Valid(string reportPath)
        {
            var report = ReadReport(reportPath);
            if (report == null) return new HashSet<string>();
            return new HashSet<string>(Load(reportPath).Where(p => Matches(report, p.Key, p.Value)).Select(p => p.Key));
        }

        /// <summary>After a new check, drop confirmations whose result changed (they have to be confirmed again).</summary>
        public static HashSet<string> Prune(string reportPath)
        {
            var report = ReadReport(reportPath);
            var confirms = Load(reportPath);
            var keep = report == null ? new HashSet<string>() : new HashSet<string>(confirms.Where(p => Matches(report, p.Key, p.Value)).Select(p => p.Key));
            if (report != null && keep.Count != confirms.Count)
                Write(reportPath, report, confirms.Where(p => keep.Contains(p.Key)).ToDictionary(p => p.Key, p => p.Value));
            return keep;
        }

        /// <summary>Confirm (or undo) one review check. Returns the valid check ids.</summary>
        public static HashSet<string> Set(string reportPath, string id, bool confirmed)
        {
            var report = ReadReport(reportPath);
            if (report == null) throw new GateException(Lang.T("err.confirmNoReport"));
            var confirms = Load(reportPath).Where(p => Matches(report, p.Key, p.Value)).ToDictionary(p => p.Key, p => p.Value);
            if (confirmed)
            {
                var check = MiniJson.Obj(MiniJson.Obj(report, "checks"), id);
                if (check == null || MiniJson.Str(check, "status") != "review") throw new GateException(Lang.T("err.confirmNotReview"));
                confirms[id] = new Dictionary<string, object>
                {
                    { "values", MiniJson.Obj(check, "values") ?? new Dictionary<string, object>() },
                    { "confirmedAt", DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ") },
                };
            }
            else confirms.Remove(id);
            Write(reportPath, report, confirms);
            return new HashSet<string>(confirms.Keys);
        }

        static void Write(string reportPath, Dictionary<string, object> report, Dictionary<string, object> confirms)
        {
            var data = new Dictionary<string, object>
            {
                { "schema", 1 }, { "tool", "unity" }, { "scope", MiniJson.Str(report, "scope") }, { "pack", MiniJson.Str(report, "pack") },
            };
            var model = MiniJson.Str(report, "model");
            if (!string.IsNullOrEmpty(model)) data["model"] = model;
            data["confirms"] = confirms;
            var path = PathFor(reportPath);
            var tmp = path + ".tmp";
            File.WriteAllText(tmp, MiniJson.Write(data) + "\n");
            if (File.Exists(path)) File.Delete(path);
            File.Move(tmp, path);
        }
    }
}
