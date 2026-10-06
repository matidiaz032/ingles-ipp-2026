"""Servidor local de práctica (solo biblioteca estándar).

Uso:  python app/server.py           → abre http://127.0.0.1:8765
"""
import ai
import feedback
import hashlib
import json
import os
import random
import re
import shutil
import sqlite3
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
DATA = ROOT / "data"
DB_PATH = Path(os.environ.get("IPP_DB") or DATA / "progress.sqlite")
PORT = 8765

SHUFFLE_FORMATS = {"discrete_cloze", "sentence_choice", "mc_cloze", "reading_discrete", "comprehension", "vocab_def"}
DECAY = 0.85          # peso de un intento por posición (más nuevo pesa más)
PRIOR = 2.0           # suavizado: pocos datos → score bajo
WEAK, WATCH = 0.30, 0.15

_lock = threading.Lock()


# ---------- contenido ----------
def load_content():
    rules = json.loads((DATA / "rules.json").read_text(encoding="utf-8"))
    exercises = []
    for d in sorted(DATA.glob("unit*")):
        unit = int(d.name.replace("unit", ""))
        for f in sorted(d.glob("*.json")):
            for ex in json.loads(f.read_text(encoding="utf-8")):
                ex["unit"] = unit
                exercises.append(ex)
    for r in rules.values():
        r.setdefault("unit", 1)
    return rules, exercises


RULES, EXERCISES = load_content()
BY_ID = {e["id"]: e for e in EXERCISES}
for _e in EXERCISES:
    for _it in _e["items"]:
        assert _it["r"] in RULES, f"regla desconocida {_it['r']} en {_e['id']}"
        for _r in list(_it.get("wr", {}).values()) + [p[1] for p in _it.get("pat", [])]:
            assert _r in RULES, f"regla desconocida {_r} en {_e['id']}"


def is_choice(ex, item):
    return "o" in item or "options" in ex or "bank" in ex


# ---------- normalización / corrección ----------
_CONTR = [(r"\b(do|does|did|is|are|was|were|have|has|had|would|could|should) not\b", r"\1n't"),
          (r"\bcannot\b", "can't"), (r"\bwill not\b", "won't")]


def norm(s):
    s = (s or "").lower().replace("’", "'").replace("‘", "'").strip()
    s = re.sub(r"^\([a-z]\)\s*", "", s)
    s = re.sub(r"[.!?,;]+$", "", s)
    s = re.sub(r"'ve\b", " have", s)
    s = re.sub(r"'m\b", " am", s)
    s = re.sub(r"'re\b", " are", s)
    s = re.sub(r"\s+", " ", s).strip()
    for pat, rep in _CONTR:
        s = re.sub(pat, rep, s)
    return s


def grade(ex, item, given):
    """→ (correct, tagged_rule, note)"""
    answers = item["a"] if isinstance(item["a"], list) else [item["a"]]
    if is_choice(ex, item):
        if given == answers[0]:
            return True, item["r"], None
        if given in item.get("alt", []):           # válida en inglés real: correcta, con aviso de contexto
            return True, item["r"], item.get("altnote") or "Válida en inglés real, pero el ejercicio pedía: " + answers[0]
        return False, item.get("wr", {}).get(given, item["r"]), None
    g = norm(given)
    if not g:
        return False, item["r"], None
    if g in [norm(a) for a in answers]:
        return True, item["r"], None
    if g in [norm(a) for a in item.get("alt", [])]:
        return True, item["r"], item.get("altnote") or "También válida, pero la respuesta esperada era: " + answers[0]
    for pr in item.get("pat", []):
        if re.search(pr[0], g):
            return False, pr[1], None
    return False, item["r"], None


# ---------- base de datos ----------
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def attempt_uid(ts, exercise_id, n, rule, correct, given, source):
    """ID estable (igual en cualquier dispositivo) para poder fusionar historiales sin duplicar."""
    raw = "|".join(str(x) for x in (ts, exercise_id, n, rule, int(correct), given or "", source))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def sim_uid(ts, unit, minutes_limit, elapsed_s, score, total, tasks):
    raw = "|".join(str(x) for x in ("sim", ts, unit, minutes_limit, elapsed_s, score, total, tasks))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _columns(con, table):
    return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS attempts(
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, exercise_id TEXT, n INTEGER,
            rule TEXT NOT NULL, correct INTEGER NOT NULL, given TEXT, source TEXT NOT NULL DEFAULT 'app', uid TEXT)""")
        con.execute("""CREATE TABLE IF NOT EXISTS simulacros(
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, unit TEXT, minutes_limit INTEGER,
            elapsed_s INTEGER, score INTEGER, total INTEGER, tasks INTEGER, uid TEXT)""")
        # migración de bases anteriores (sin uid): copia de seguridad + backfill determinista
        if "uid" not in _columns(con, "attempts") or "uid" not in _columns(con, "simulacros"):
            con.commit()
            if DB_PATH.exists() and DB_PATH.stat().st_size > 0:
                shutil.copy2(DB_PATH, DB_PATH.with_name(DB_PATH.stem + ".pre-sync-backup.sqlite"))
            if "uid" not in _columns(con, "attempts"):
                con.execute("ALTER TABLE attempts ADD COLUMN uid TEXT")
            if "uid" not in _columns(con, "simulacros"):
                con.execute("ALTER TABLE simulacros ADD COLUMN uid TEXT")
        used = {r[0] for r in con.execute("SELECT uid FROM attempts WHERE uid IS NOT NULL")}
        for r in con.execute("SELECT * FROM attempts WHERE uid IS NULL ORDER BY id").fetchall():
            uid = base = attempt_uid(r["ts"], r["exercise_id"], r["n"], r["rule"], r["correct"], r["given"], r["source"])
            k = 1
            while uid in used:                       # filas idénticas (mismo segundo): las distingo con un sufijo
                k += 1
                uid = f"{base}-{k}"
            used.add(uid)
            con.execute("UPDATE attempts SET uid=? WHERE id=?", (uid, r["id"]))
        used = {r[0] for r in con.execute("SELECT uid FROM simulacros WHERE uid IS NOT NULL")}
        for r in con.execute("SELECT * FROM simulacros WHERE uid IS NULL ORDER BY id").fetchall():
            uid = base = sim_uid(r["ts"], r["unit"], r["minutes_limit"], r["elapsed_s"], r["score"], r["total"], r["tasks"])
            k = 1
            while uid in used:
                k += 1
                uid = f"{base}-{k}"
            used.add(uid)
            con.execute("UPDATE simulacros SET uid=? WHERE id=?", (uid, r["id"]))
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_attempts_uid ON attempts(uid)")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_sim_uid ON simulacros(uid)")
        con.execute("""CREATE TABLE IF NOT EXISTS glossary(
            id TEXT PRIMARY KEY, term TEXT NOT NULL, term_norm TEXT NOT NULL, sentence TEXT, body TEXT NOT NULL,
            notes TEXT, ts TEXT NOT NULL, saved INTEGER NOT NULL DEFAULT 0, saved_ts TEXT)""")
        con.execute("CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT NOT NULL, ts INTEGER NOT NULL)")
        seed_f = DATA / "history-seed.json"
        seed = json.loads(seed_f.read_text(encoding="utf-8")) if seed_f.exists() else []
        have = {r[0] for r in con.execute("SELECT DISTINCT source FROM attempts")}
        for s_ in seed:
            if s_["source"] in have:
                continue
            con.execute("INSERT OR IGNORE INTO attempts(ts,exercise_id,n,rule,correct,given,source,uid) VALUES(?,?,?,?,0,?,?,?)",
                        (s_["ts"], None, s_["question"], s_["rule"], s_["given"], s_["source"],
                         attempt_uid(s_["ts"], None, s_["question"], s_["rule"], 0, s_["given"], s_["source"])))


def rule_stats(con):
    stats = {}
    rows = con.execute("SELECT rule, correct, ts FROM attempts ORDER BY id DESC").fetchall()
    per = {}
    for r in rows:
        per.setdefault(r["rule"], []).append(r["correct"])
    for rid in RULES:
        seq = per.get(rid, [])
        w_total = sum(DECAY ** i for i in range(len(seq)))
        w_wrong = sum(DECAY ** i for i, c in enumerate(seq) if not c)
        score = w_wrong / (w_total + PRIOR) if seq else 0.0
        n = len(seq)
        wrong = sum(1 for c in seq if not c)
        if n == 0:
            status = "new"
        elif score >= WEAK and n >= 3:
            status = "weak"
        elif score >= WATCH or (wrong and n < 3):
            status = "watch"
        else:
            status = "ok"
        stats[rid] = {"id": rid, **RULES[rid], "attempts": n, "wrong": wrong, "score": round(score, 3), "status": status}
    return stats


# ---------- API ----------
def public_exercise(ex, seen):
    out = {k: ex[k] for k in ("id", "unit", "format", "level", "linguaskill", "title", "instructions", "text", "bank") if k in ex}
    items = []
    for it in ex["items"]:
        p = {"n": it["n"]}
        if "q" in it:
            p["q"] = it["q"]
        o = it.get("o") or ex.get("options")
        if o:
            o = list(o)
            if ex["format"] in SHUFFLE_FORMATS:
                random.shuffle(o)
            p["o"] = o
        items.append(p)
    out["items"] = items
    out["seen"] = seen.get(ex["id"])
    return out


def api_exercises():
    with db() as con:
        rows = con.execute("""SELECT exercise_id, MAX(ts) last_ts, SUM(correct) ok, COUNT(*) total FROM attempts
                              WHERE exercise_id IS NOT NULL GROUP BY exercise_id""").fetchall()
        seen = {r["exercise_id"]: {"last": r["last_ts"], "ok": r["ok"], "total": r["total"]} for r in rows}
    return [public_exercise(e, seen) for e in EXERCISES]


def _first_answers(ex):
    return {it["n"]: (it["a"][0] if isinstance(it["a"], list) else it["a"]) for it in ex["items"]}


def api_check(body):
    ex = BY_ID.get(body.get("exercise_id"))
    if not ex:
        return {"error": "ejercicio desconocido"}, 404
    answers = body.get("answers", {})
    first = _first_answers(ex)
    results, ts = [], time.strftime("%Y-%m-%dT%H:%M:%S")
    with _lock, db() as con:
        for it in ex["items"]:
            given = str(answers.get(str(it["n"]), "")).strip()
            ok, rule, note = grade(ex, it, given)
            a = it["a"] if isinstance(it["a"], list) else [it["a"]]
            fx = feedback.explain(ex, it, given, ok, note, norm(given), first, is_choice(ex, it))
            results.append({"n": it["n"], "correct": ok, "given": given, "answer": a[0], "rule": rule,
                            "rule_name": RULES[rule]["name"], "explanation": it.get("e", ""), "note": note,
                            "sentence": fx["sentence"], "parts": fx["parts"], "alt": fx["alt"], "irr": fx["irr"]})
            con.execute("INSERT OR IGNORE INTO attempts(ts,exercise_id,n,rule,correct,given,uid) VALUES(?,?,?,?,?,?,?)",
                        (ts, ex["id"], it["n"], rule, int(ok), given,
                         attempt_uid(ts, ex["id"], it["n"], rule, ok, given, "app")))
    return {"results": results, "score": sum(r["correct"] for r in results), "total": len(results)}, 200


def api_queue(qs):
    fmt = qs.get("format", [""])[0]
    rule = qs.get("rule", [""])[0]
    mode = qs.get("mode", ["all"])[0]
    unit = qs.get("unit", [""])[0]
    with db() as con:
        stats = rule_stats(con)
        seen = {r["exercise_id"]: r["m"] for r in con.execute(
            "SELECT exercise_id, MAX(id) m FROM attempts WHERE exercise_id IS NOT NULL GROUP BY exercise_id")}
        last_id = con.execute("SELECT COALESCE(MAX(id),0) FROM attempts").fetchone()[0]
    scored = []
    for ex in EXERCISES:
        if fmt and ex["format"] != fmt:
            continue
        if unit and str(ex["unit"]) != unit:
            continue
        rules_in = {it["r"] for it in ex["items"]} | {r for it in ex["items"] for r in it.get("wr", {}).values()}
        if rule and rule not in rules_in:
            continue
        weak = max(stats[r]["score"] for r in rules_in)
        if mode == "weak" and not any(stats[r]["status"] in ("weak", "watch") for r in rules_in):
            continue
        w = 1 + 6 * weak
        if ex["id"] not in seen:
            w += 1.5
        else:
            w -= 2.0 * max(0, 1 - (last_id - seen[ex["id"]]) / 40)   # recién hecho → baja
        scored.append((w + random.random() * 0.8, ex["id"]))
    scored.sort(reverse=True)
    return [i for _, i in scored]


def api_stats():
    with db() as con:
        rules = rule_stats(con)
        total = con.execute("SELECT COUNT(*) c, COALESCE(SUM(correct),0) ok FROM attempts WHERE source='app'").fetchone()
        by_format = {}
        for r in con.execute("SELECT exercise_id, correct FROM attempts WHERE exercise_id IS NOT NULL"):
            f = BY_ID[r["exercise_id"]]["format"]
            d = by_format.setdefault(f, {"format": f, "total": 0, "ok": 0})
            d["total"] += 1
            d["ok"] += r["correct"]
        recent = []
        for r in con.execute("SELECT * FROM attempts WHERE correct=0 ORDER BY id DESC LIMIT 25"):
            recent.append({"ts": r["ts"], "rule": r["rule"], "rule_name": RULES[r["rule"]]["name"],
                           "given": r["given"], "source": r["source"], "exercise_id": r["exercise_id"], "n": r["n"]})
    groups = {}
    for r in rules.values():
        groups.setdefault(r["group"], []).append(r)
    return {"total": total["c"], "ok": total["ok"], "rules": sorted(rules.values(), key=lambda r: -r["score"]),
            "groups": groups, "by_format": list(by_format.values()), "recent_errors": recent}


# ---------- simulacro ----------
SIM_COMPOSITION = [("reading_discrete", 2), ("discrete_cloze", 2), ("open_cloze", 3), ("mc_cloze", 3),
                   ("comprehension", 3), ("gapped", 1), ("cross_text", 1)]   # 15 tareas para 59 min
SIM_DISCRETE_ITEMS = 5


def _sim_family(ex):
    return "gapped" if ex["format"] in ("gapped_sentences", "gapped_paragraphs") else ex["format"]


def public_task(ex, ns=None):
    """Como public_exercise pero (opcional) con un subconjunto de ítems y numeración visible 1..k."""
    p = public_exercise(ex, {})
    if ns is not None:
        keep = [it for it in p["items"] if it["n"] in ns]
        for k, it in enumerate(keep, 1):
            it["disp"] = k
        p["items"] = keep
    p["ns"] = [it["n"] for it in p["items"]]
    return p


def api_sim_start(body):
    unit = str(body.get("unit") or "")
    minutes = int(body.get("minutes") or 59)
    weak = bool(body.get("weak"))
    scale = min(1.0, minutes / 59)
    with db() as con:
        stats = rule_stats(con)
        seen = {r[0] for r in con.execute("SELECT DISTINCT exercise_id FROM attempts WHERE exercise_id IS NOT NULL")}
    tasks = []
    for fam, count in SIM_COMPOSITION:
        count = max(1, round(count * scale))
        pool = [e for e in EXERCISES if _sim_family(e) == fam and (not unit or str(e["unit"]) == unit)]
        if fam == "comprehension":            # mezcla de 5 y 2 ítems, como en el examen
            long_ = [e for e in pool if len(e["items"]) >= 5]
            short = [e for e in pool if len(e["items"]) < 5]
            random.shuffle(long_); random.shuffle(short)
            picked = (long_[:1] + short[:count - 1] + long_[1:] + short[count - 1:])[:count]
        else:
            def w(e):
                rules_in = {it["r"] for it in e["items"]}
                base = 1 + (6 * max(stats[r]["score"] for r in rules_in) if weak else 0)
                return base + (1.5 if e["id"] not in seen else 0) + random.random()
            picked = sorted(pool, key=w, reverse=True)[:count]
        for e in picked:
            ns = None
            if e["format"] == "discrete_cloze" and len(e["items"]) > SIM_DISCRETE_ITEMS:
                ns = sorted(random.sample([it["n"] for it in e["items"]], SIM_DISCRETE_ITEMS))
            tasks.append(public_task(e, ns))
    random.shuffle(tasks)
    if not tasks:
        return {"error": "No hay ejercicios de formato Linguaskill para esa selección."}, 404
    return {"minutes": minutes, "unit": unit, "tasks": tasks,
            "total_items": sum(len(t["items"]) for t in tasks)}, 200


def api_sim_finish(body):
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    out_tasks, by_format, by_rule = [], {}, {}
    score = total = 0
    with _lock, db() as con:
        for t in body.get("tasks", []):
            ex = BY_ID.get(t.get("exercise_id"))
            if not ex:
                continue
            answers = t.get("answers", {})
            ns = t.get("ns") or [it["n"] for it in ex["items"]]
            results = []
            for k, it in enumerate([i for i in ex["items"] if i["n"] in ns], 1):
                given = str(answers.get(str(it["n"]), "")).strip()
                ok, rule, note = grade(ex, it, given)
                a = it["a"] if isinstance(it["a"], list) else [it["a"]]
                fx = feedback.explain(ex, it, given, ok, note, norm(given), _first_answers(ex), is_choice(ex, it))
                results.append({"n": k, "orig_n": it["n"], "correct": ok, "given": given, "answer": a[0],
                                "rule_name": RULES[rule]["name"], "rule": rule, "explanation": it.get("e", ""),
                                "sentence": fx["sentence"], "parts": fx["parts"], "alt": fx["alt"], "irr": fx["irr"]})
                total += 1
                score += int(ok)
                bf = by_format.setdefault(ex["format"], {"format": ex["format"], "ok": 0, "total": 0})
                bf["total"] += 1
                bf["ok"] += int(ok)
                if not ok:
                    by_rule[rule] = by_rule.get(rule, 0) + 1
                if given:   # sin responder (p. ej. por tiempo) no se le carga a la regla
                    con.execute("INSERT OR IGNORE INTO attempts(ts,exercise_id,n,rule,correct,given,source,uid) VALUES(?,?,?,?,?,?,'simulacro',?)",
                                (ts, ex["id"], it["n"], rule, int(ok), given,
                                 attempt_uid(ts, ex["id"], it["n"], rule, ok, given, "simulacro")))
            out_tasks.append({"exercise_id": ex["id"], "title": ex["title"], "format": ex["format"], "unit": ex["unit"],
                              "text": ex.get("text"), "bank": ex.get("bank"), "results": results})
        unit_s, mins, el = str(body.get("unit") or ""), int(body.get("minutes") or 59), int(body.get("elapsed") or 0)
        con.execute("INSERT OR IGNORE INTO simulacros(ts,unit,minutes_limit,elapsed_s,score,total,tasks,uid) VALUES(?,?,?,?,?,?,?,?)",
                    (ts, unit_s, mins, el, score, total, len(out_tasks),
                     sim_uid(ts, unit_s, mins, el, score, total, len(out_tasks))))
    top = sorted(by_rule.items(), key=lambda kv: -kv[1])[:6]
    return {"score": score, "total": total, "tasks": out_tasks, "by_format": list(by_format.values()),
            "top_rules": [{"rule": r, "rule_name": RULES[r]["name"], "errors": n} for r, n in top]}, 200


def api_sim_history():
    with db() as con:
        rows = con.execute("SELECT * FROM simulacros ORDER BY id DESC LIMIT 10").fetchall()
    return [dict(r) for r in rows]


# ---------- retomar donde lo dejaste (se sincroniza entre dispositivos; gana el más reciente) ----------
def get_resume():
    with db() as con:
        r = con.execute("SELECT value, ts FROM kv WHERE key='resume'").fetchone()
    if not r:
        return None
    try:
        v = json.loads(r["value"])
    except ValueError:
        return None
    v["ts"] = r["ts"]
    return v


def _valid_resume(b):
    if not isinstance(b, dict):
        return None
    try:
        ts = int(b["ts"])
        ids = b.get("ids") or []
        if not isinstance(ids, list) or len(ids) > 3000 or not all(isinstance(x, str) and len(x) <= 80 for x in ids):
            return None
        i = int(b.get("i") or 0)
        qs = str(b.get("qs") or "")[:600]
    except (KeyError, TypeError, ValueError):
        return None
    return {"ids": ids, "i": max(0, i), "qs": qs, "ts": ts}


def set_resume(b):
    """Guarda solo si es más nuevo que lo que hay. ids vacío = descartado. Devuelve True si lo guardó."""
    v = _valid_resume(b)
    if not v:
        return False
    with _lock, db() as con:
        cur = con.execute("SELECT ts FROM kv WHERE key='resume'").fetchone()
        if cur and cur["ts"] >= v["ts"]:
            return False
        con.execute("INSERT OR REPLACE INTO kv(key,value,ts) VALUES('resume',?,?)",
                    (json.dumps({"ids": v["ids"], "i": v["i"], "qs": v["qs"]}, ensure_ascii=False), v["ts"]))
    return True


def api_resume_get():
    r = get_resume()
    return r if r and r["ids"] and r["i"] < len(r["ids"]) else {}


def api_resume_save(body):
    if not _valid_resume(body):
        return {"error": "Datos inválidos"}, 400
    return {"saved": set_resume(body)}, 200


# ---------- sincronización (exportar / importar) ----------
EXPORT_VERSION = 1


def api_export():
    with db() as con:
        att = [dict(ts=r["ts"], exercise_id=r["exercise_id"], n=r["n"], rule=r["rule"], correct=r["correct"],
                    given=r["given"], source=r["source"], uid=r["uid"])
               for r in con.execute("SELECT * FROM attempts ORDER BY id")]
        sims = [dict(ts=r["ts"], unit=r["unit"], minutes_limit=r["minutes_limit"], elapsed_s=r["elapsed_s"],
                     score=r["score"], total=r["total"], tasks=r["tasks"], uid=r["uid"])
                for r in con.execute("SELECT * FROM simulacros ORDER BY id")]
    return {"app": "ipp-english", "version": EXPORT_VERSION, "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "attempts": att, "simulacros": sims, "resume": get_resume()}


def api_import(body):
    if not isinstance(body, dict) or body.get("app") != "ipp-english" or body.get("version") != EXPORT_VERSION:
        return {"error": "Archivo no reconocido: tiene que ser un export de esta app."}, 400
    added = dup = invalid = sims_added = 0
    with _lock, db() as con:
        for a in body.get("attempts", []):
            try:
                rule = a["rule"]
                ex_id = a.get("exercise_id")
                if rule not in RULES or (ex_id is not None and ex_id not in BY_ID):
                    invalid += 1
                    continue
                ts, n, correct = str(a["ts"]), a.get("n"), int(bool(a["correct"]))
                given, source = a.get("given") or "", str(a.get("source") or "app")
                uid = a.get("uid") if isinstance(a.get("uid"), str) and 8 <= len(a["uid"]) <= 40 else attempt_uid(ts, ex_id, n, rule, correct, given, source)
                cur = con.execute("INSERT OR IGNORE INTO attempts(ts,exercise_id,n,rule,correct,given,source,uid) VALUES(?,?,?,?,?,?,?,?)",
                                  (ts, ex_id, n, rule, correct, given, source, uid))
                added += cur.rowcount
                dup += 1 - cur.rowcount
            except (KeyError, TypeError, ValueError):
                invalid += 1
        for m in body.get("simulacros", []):
            try:
                args = (str(m["ts"]), str(m.get("unit") or ""), int(m["minutes_limit"]), int(m["elapsed_s"]),
                        int(m["score"]), int(m["total"]), int(m["tasks"]))
                uid = m.get("uid") if isinstance(m.get("uid"), str) and 8 <= len(m["uid"]) <= 40 else sim_uid(*args)
                cur = con.execute("INSERT OR IGNORE INTO simulacros(ts,unit,minutes_limit,elapsed_s,score,total,tasks,uid) VALUES(?,?,?,?,?,?,?,?)",
                                  args + (uid,))
                sims_added += cur.rowcount
            except (KeyError, TypeError, ValueError):
                invalid += 1
    resume_updated = set_resume(body.get("resume"))
    return {"attempts_added": added, "attempts_duplicated": dup, "invalid": invalid, "simulacros_added": sims_added,
            "resume_updated": resume_updated}, 200


# ---------- sincronización automática por carpeta compartida ----------
# Cada dispositivo escribe SOLO su archivo (ipp-sync-<nombre>.json) e importa los de los demás. Una herramienta
# externa (Syncthing, Drive...) copia la carpeta entre dispositivos. La importación es idempotente (uid), así que
# archivos repetidos, viejos o "conflict copies" no duplican ni borran nada.
SYNC_CONF = DATA / "sync.json"
SYNC_EVERY_S = 45
_sync_lock = threading.Lock()
_sync_state = {"last": None, "msg": "Sin configurar", "ok": False, "written": None, "seen": {}, "added_total": 0}


def sync_config():
    try:
        c = json.loads(SYNC_CONF.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        c = {}
    return {"dir": (os.environ.get("IPP_SYNC_DIR") or c.get("dir") or "").strip(),
            "device": re.sub(r"[^A-Za-z0-9_-]", "", os.environ.get("IPP_DEVICE") or c.get("device") or "")}


def sync_now():
    with _sync_lock:
        cfg = sync_config()
        st = _sync_state
        if not cfg["dir"] or not cfg["device"]:
            st.update(ok=False, msg="Sin configurar: falta la carpeta o el nombre del dispositivo.")
            return dict(st, config=cfg)
        try:
            folder = Path(cfg["dir"]).expanduser()
            folder.mkdir(parents=True, exist_ok=True)
            mine = folder / f"ipp-sync-{cfg['device']}.json"
            exp = api_export()
            sig = hashlib.sha1(json.dumps({k: v for k, v in exp.items() if k != "exported_at"}, sort_keys=True).encode()).hexdigest()
            wrote = False
            if sig != st["written"] or not mine.exists():
                tmp = folder / f".ipp-sync-{cfg['device']}.tmp"
                tmp.write_text(json.dumps(dict(exp, device=cfg["device"]), ensure_ascii=False), encoding="utf-8")
                os.replace(tmp, mine)
                st["written"], wrote = sig, True
            added = files = 0
            for f in sorted(folder.glob("ipp-sync-*.json")):
                if f.name == mine.name:
                    continue
                fs = f.stat()
                key = (fs.st_mtime_ns, fs.st_size)
                if st["seen"].get(f.name) == key:
                    continue
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                except ValueError:
                    continue                       # copia a medias: se reintenta en el próximo ciclo
                res, code = api_import(data)
                if code == 200:
                    st["seen"][f.name] = key
                    files += 1
                    added += res["attempts_added"] + res["simulacros_added"]
            st["added_total"] += added
            st.update(ok=True, last=time.strftime("%Y-%m-%d %H:%M:%S"),
                      msg=f"Sincronizado. Archivos de otros dispositivos: {len(list(folder.glob('ipp-sync-*.json'))) - 1}"
                          f"{'; importadas ' + str(added) + ' respuestas nuevas' if added else ''}"
                          f"{'; tu archivo se actualizó' if wrote else ''}.")
        except OSError as e:
            st.update(ok=False, msg=f"No se pudo usar la carpeta: {e}")
        return dict(st, config=cfg)


def _sync_loop():
    while True:
        try:
            if sync_config()["dir"]:
                sync_now()
        except Exception as e:          # el hilo nunca debe morir
            _sync_state.update(ok=False, msg=f"Error inesperado: {e}")
        time.sleep(SYNC_EVERY_S)


def api_sync_status():
    return {k: v for k, v in dict(_sync_state, config=sync_config()).items() if k not in ("seen", "written")}


def api_sync_config(body):
    dev = re.sub(r"[^A-Za-z0-9_-]", "", str(body.get("device") or ""))
    d = str(body.get("dir") or "").strip()
    if not dev or not d:
        return {"error": "Completá el nombre del dispositivo (letras y números, ej. pc o celu) y la carpeta."}, 400
    SYNC_CONF.write_text(json.dumps({"dir": d, "device": dev}, ensure_ascii=False), encoding="utf-8")
    _sync_state["written"] = None
    sync_now()
    return api_sync_status(), 200


# ---------- Consultor con IA (Hugging Face) + glosario — aislado del motor de ejercicios ----------
GLOSSARY_MD = Path(os.environ.get("IPP_GLOSSARY") or ROOT / "obsidian-notes" / "Referencia-General" / "99 Glosario y dudas.md")
GLOSSARY_FALLBACK = DATA / "glosario-pendiente.md"
GLOSSARY_HEADER = """# 📒 Glosario y dudas

> [!abstract] Cómo usar esta nota
> Entradas guardadas desde la app de práctica (pantalla *Consultar*). Nacen como **sugerencia de IA sin revisar**:
> cuando las investigues y las corrijas, cambiá el callout `[!warning]` por `[!tip]` y pulí el texto.
> La app **solo agrega entradas al final** de este archivo; nunca modifica lo que ya editaste.
"""


def _norm_term(t):
    return re.sub(r"\s+", " ", (t or "").lower()).strip()


def api_ai_lookup(body):
    term, sentence, force = str(body.get("term", "")), str(body.get("sentence", "")), bool(body.get("force"))
    tn = _norm_term(term)
    if tn and not sentence.strip() and not force:          # consulta repetida sin contexto: sale de la base, sin gastar cupo
        with db() as con:
            r = con.execute("SELECT * FROM glossary WHERE term_norm=? AND COALESCE(sentence,'')='' ORDER BY ts DESC LIMIT 1", (tn,)).fetchone()
        if r:
            return {"id": r["id"], "term": r["term"], "sentence": "", "body": r["body"], "needs_context": False,
                    "notes": json.loads(r["notes"] or "[]"), "model": "(guardada antes)", "cached": True, "saved": bool(r["saved"])}, 200
    try:
        res = ai.lookup(term, sentence)
    except ai.HFError as e:
        return {"error": str(e)}, 400
    if res["needs_context"]:
        return res, 200
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    gid = hashlib.sha1(f"{tn}|{sentence}|{ts}|{random.random()}".encode("utf-8")).hexdigest()[:10]
    with db() as con:
        con.execute("INSERT INTO glossary(id,term,term_norm,sentence,body,notes,ts) VALUES(?,?,?,?,?,?,?)",
                    (gid, res["term"], tn, res["sentence"], res["body"], json.dumps(res["notes"], ensure_ascii=False), ts))
    return dict(res, id=gid, cached=False, saved=False), 200


def _md_entry(r):
    date = r["ts"][:10]
    lines = [f"", f"## {r['term'].replace('#', '').strip()}",
             f"> [!warning] Sugerencia de IA — sin revisar · {date} · id `{r['id']}`"]
    if r["sentence"]:
        lines += [f'> **Oración de contexto:** "{r["sentence"]}"', ">"]
    lines += ["> " + ln if ln.strip() else ">" for ln in r["body"].splitlines()]
    notes = json.loads(r["notes"] or "[]")
    if notes:
        lines += [">", "> **Mis notas relacionadas:** " + " · ".join(f"[[{n}]]" for n in notes)]
    return "\n".join(lines) + "\n"


def api_ai_save(body):
    again = bool(body.get("again"))
    with _lock, db() as con:
        r = con.execute("SELECT * FROM glossary WHERE id=?", (str(body.get("id", "")),)).fetchone()
        if not r:
            return {"error": "No encontré esa consulta. Volvé a consultarla."}, 404
        if r["saved"] and not again:
            return {"already": True, "message": "Ya está guardada en tu glosario."}, 200
        path, fallback = GLOSSARY_MD, False
        if not path.parent.exists():          # p. ej. en el celular, donde no está el vault de Obsidian
            path, fallback = GLOSSARY_FALLBACK, True
        try:
            new = not path.exists()
            with open(path, "a", encoding="utf-8", newline="\n") as f:
                if new:
                    f.write(GLOSSARY_HEADER)
                f.write(_md_entry(r))
        except OSError as e:
            return {"error": f"No pude escribir el glosario: {e}"}, 500
        con.execute("UPDATE glossary SET saved=1, saved_ts=? WHERE id=?", (time.strftime("%Y-%m-%dT%H:%M:%S"), r["id"]))
    return {"saved": True, "path": str(path), "fallback": fallback}, 200


def api_glossary():
    with db() as con:
        rows = con.execute("SELECT id, term, sentence, saved_ts FROM glossary WHERE saved=1 ORDER BY saved_ts DESC").fetchall()
    return {"entries": [dict(r) for r in rows], "path": str(GLOSSARY_MD if GLOSSARY_MD.parent.exists() else GLOSSARY_FALLBACK)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/exercises":
            return self._json(api_exercises())
        if u.path == "/api/queue":
            return self._json(api_queue(parse_qs(u.query)))
        if u.path == "/api/stats":
            return self._json(api_stats())
        if u.path == "/api/export":
            data = json.dumps(api_export(), ensure_ascii=False, indent=1).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="ipp-progreso-%s.json"' % time.strftime("%Y%m%d-%H%M"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if u.path == "/api/glossary":
            return self._json(api_glossary())
        if u.path == "/api/sync/status":
            return self._json(api_sync_status())
        if u.path == "/api/resume":
            return self._json(api_resume_get())
        if u.path == "/api/sim/history":
            return self._json(api_sim_history())
        if u.path == "/api/rules":
            return self._json(RULES)
        rel = "index.html" if u.path in ("/", "") else u.path.lstrip("/")
        f = (STATIC / rel).resolve()
        if STATIC.resolve() not in f.parents or not f.is_file():
            self.send_error(404)
            return
        ctype = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}.get(f.suffix, "application/octet-stream")
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "JSON inválido"}, 400)
        path = urlparse(self.path).path
        if path == "/api/check":
            obj, code = api_check(body)
            return self._json(obj, code)
        if path == "/api/import":
            obj, code = api_import(body)
            return self._json(obj, code)
        if path == "/api/resume":
            obj, code = api_resume_save(body)
            return self._json(obj, code)
        if path == "/api/sync/config":
            obj, code = api_sync_config(body)
            return self._json(obj, code)
        if path == "/api/sync/now":
            sync_now()
            return self._json(api_sync_status())
        if path == "/api/ai/lookup":
            obj, code = api_ai_lookup(body)
            return self._json(obj, code)
        if path == "/api/ai/save":
            obj, code = api_ai_save(body)
            return self._json(obj, code)
        if path == "/api/sim/start":
            obj, code = api_sim_start(body)
            return self._json(obj, code)
        if path == "/api/sim/finish":
            obj, code = api_sim_finish(body)
            return self._json(obj, code)
        self.send_error(404)


def main():
    init_db()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=_sync_loop, daemon=True).start()
    url = f"http://127.0.0.1:{PORT}"
    print(f"Práctica IPP — {len(EXERCISES)} ejercicios cargados. Abriendo {url}  (Ctrl+C para salir)")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
