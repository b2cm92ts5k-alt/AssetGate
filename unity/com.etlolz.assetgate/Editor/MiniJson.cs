using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace ETLOLZ.AssetGate
{
    /// <summary>
    /// Small JSON reader/writer for config.json and reports (JsonUtility cannot handle dictionaries).
    /// Objects are Dictionary&lt;string, object&gt;, arrays List&lt;object&gt;, numbers double.
    /// </summary>
    public static class MiniJson
    {
        public static object Parse(string text)
        {
            var parser = new Parser(text);
            var value = parser.ReadValue();
            parser.SkipWhitespace();
            if (!parser.AtEnd) throw new FormatException("Unexpected data after the JSON value");
            return value;
        }

        public static string Write(object value)
        {
            var sb = new StringBuilder();
            WriteValue(sb, value, 0);
            return sb.ToString();
        }

        // ---------- typed access helpers ----------

        public static Dictionary<string, object> Obj(object node, string key)
        {
            return (node as Dictionary<string, object>) != null && ((Dictionary<string, object>)node).TryGetValue(key, out var v)
                ? v as Dictionary<string, object> : null;
        }

        public static List<object> Arr(object node, string key)
        {
            return (node as Dictionary<string, object>) != null && ((Dictionary<string, object>)node).TryGetValue(key, out var v)
                ? v as List<object> : null;
        }

        public static string Str(object node, string key, string fallback = null)
        {
            return (node as Dictionary<string, object>) != null && ((Dictionary<string, object>)node).TryGetValue(key, out var v) && v is string s
                ? s : fallback;
        }

        public static double Num(object node, string key, double fallback = double.NaN)
        {
            return (node as Dictionary<string, object>) != null && ((Dictionary<string, object>)node).TryGetValue(key, out var v) && v is double d
                ? d : fallback;
        }

        public static bool? Bool(object node, string key)
        {
            return (node as Dictionary<string, object>) != null && ((Dictionary<string, object>)node).TryGetValue(key, out var v) && v is bool b
                ? b : (bool?)null;
        }

        // ---------- writer ----------

        static void WriteValue(StringBuilder sb, object value, int indent)
        {
            switch (value)
            {
                case null: sb.Append("null"); break;
                case string s: WriteString(sb, s); break;
                case bool b: sb.Append(b ? "true" : "false"); break;
                case int i: sb.Append(i.ToString(CultureInfo.InvariantCulture)); break;
                case long l: sb.Append(l.ToString(CultureInfo.InvariantCulture)); break;
                case float f: sb.Append(Number(f)); break;
                case double d: sb.Append(Number(d)); break;
                case IDictionary dict:
                    if (dict.Count == 0) { sb.Append("{}"); break; }
                    sb.Append("{\n");
                    var first = true;
                    foreach (DictionaryEntry entry in dict)
                    {
                        if (!first) sb.Append(",\n");
                        first = false;
                        sb.Append(' ', indent + 2);
                        WriteString(sb, entry.Key.ToString());
                        sb.Append(": ");
                        WriteValue(sb, entry.Value, indent + 2);
                    }
                    sb.Append('\n').Append(' ', indent).Append('}');
                    break;
                case IEnumerable list:
                    sb.Append('[');
                    var firstItem = true;
                    foreach (var item in list)
                    {
                        if (!firstItem) sb.Append(", ");
                        firstItem = false;
                        WriteValue(sb, item, indent + 2);
                    }
                    sb.Append(']');
                    break;
                default: WriteString(sb, value.ToString()); break;
            }
        }

        static string Number(double d)
        {
            if (double.IsNaN(d) || double.IsInfinity(d)) return "null";
            return Math.Round(d, 6).ToString("0.######", CultureInfo.InvariantCulture);
        }

        static void WriteString(StringBuilder sb, string s)
        {
            sb.Append('"');
            foreach (var c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4"));
                        else sb.Append(c);
                        break;
                }
            }
            sb.Append('"');
        }

        // ---------- reader ----------

        sealed class Parser
        {
            readonly string _s;
            int _i;

            public Parser(string s) { _s = s; }

            public bool AtEnd => _i >= _s.Length;

            public void SkipWhitespace()
            {
                while (_i < _s.Length && char.IsWhiteSpace(_s[_i])) _i++;
            }

            public object ReadValue()
            {
                SkipWhitespace();
                if (AtEnd) throw new FormatException("Unexpected end of JSON");
                var c = _s[_i];
                switch (c)
                {
                    case '{': return ReadObject();
                    case '[': return ReadArray();
                    case '"': return ReadString();
                    case 't': Expect("true"); return true;
                    case 'f': Expect("false"); return false;
                    case 'n': Expect("null"); return null;
                    default: return ReadNumber();
                }
            }

            void Expect(string word)
            {
                if (string.CompareOrdinal(_s, _i, word, 0, word.Length) != 0) throw new FormatException("Invalid JSON at position " + _i);
                _i += word.Length;
            }

            Dictionary<string, object> ReadObject()
            {
                var result = new Dictionary<string, object>();
                _i++;
                SkipWhitespace();
                if (_s[_i] == '}') { _i++; return result; }
                while (true)
                {
                    SkipWhitespace();
                    var key = ReadString();
                    SkipWhitespace();
                    if (_s[_i] != ':') throw new FormatException("Expected ':' at position " + _i);
                    _i++;
                    result[key] = ReadValue();
                    SkipWhitespace();
                    if (_s[_i] == ',') { _i++; continue; }
                    if (_s[_i] == '}') { _i++; return result; }
                    throw new FormatException("Expected ',' or '}' at position " + _i);
                }
            }

            List<object> ReadArray()
            {
                var result = new List<object>();
                _i++;
                SkipWhitespace();
                if (_s[_i] == ']') { _i++; return result; }
                while (true)
                {
                    result.Add(ReadValue());
                    SkipWhitespace();
                    if (_s[_i] == ',') { _i++; continue; }
                    if (_s[_i] == ']') { _i++; return result; }
                    throw new FormatException("Expected ',' or ']' at position " + _i);
                }
            }

            string ReadString()
            {
                if (_s[_i] != '"') throw new FormatException("Expected a string at position " + _i);
                _i++;
                var sb = new StringBuilder();
                while (true)
                {
                    var c = _s[_i++];
                    if (c == '"') return sb.ToString();
                    if (c != '\\') { sb.Append(c); continue; }
                    var e = _s[_i++];
                    switch (e)
                    {
                        case 'n': sb.Append('\n'); break;
                        case 'r': sb.Append('\r'); break;
                        case 't': sb.Append('\t'); break;
                        case 'b': sb.Append('\b'); break;
                        case 'f': sb.Append('\f'); break;
                        case 'u':
                            sb.Append((char)Convert.ToInt32(_s.Substring(_i, 4), 16));
                            _i += 4;
                            break;
                        default: sb.Append(e); break;
                    }
                }
            }

            double ReadNumber()
            {
                var start = _i;
                while (_i < _s.Length && "+-0123456789.eE".IndexOf(_s[_i]) >= 0) _i++;
                if (start == _i) throw new FormatException("Invalid JSON at position " + _i);
                return double.Parse(_s.Substring(start, _i - start), NumberStyles.Float, CultureInfo.InvariantCulture);
            }
        }
    }
}
