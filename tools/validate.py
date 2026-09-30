"""Autocontrol del contenido: python tools/validate.py
Verifica que cada respuesta correcta se corrija bien, que ningún patrón de error capture una
respuesta válida, y que opciones / huecos / reglas sean coherentes. No toca tu base de datos."""
import os, re, sys, tempfile, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
os.environ["IPP_DB"] = os.path.join(tempfile.gettempdir(), "ipp_validate.sqlite")
for _f in (os.environ["IPP_DB"], os.environ["IPP_DB"].replace(".sqlite", ".pre-sync-backup.sqlite")):
    if os.path.exists(_f):
        os.remove(_f)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import server as s

bad = 0
ids = [e["id"] for e in s.EXERCISES]
assert len(ids) == len(set(ids)), "ids duplicados"
for e in s.EXERCISES:
    ns = [it["n"] for it in e["items"]]
    assert ns == list(range(1, len(ns) + 1)), (e["id"], ns)
    for it in e["items"]:
        a = it["a"] if isinstance(it["a"], list) else [it["a"]]
        for x in a + it.get("alt", []):
            ok, _, _ = s.grade(e, it, x)
            if not ok:
                print("FAIL", e["id"], it["n"], x); bad += 1
            for pr in it.get("pat", []):
                pat = pr[0]
                if re.search(pat, s.norm(x)):
                    print("PAT MATCHES CORRECT", e["id"], it["n"], pat, x); bad += 1
        opts = it.get("o") or e.get("options")
        if opts:
            if a[0] not in opts: print("ANSWER NOT IN OPTIONS", e["id"], it["n"]); bad += 1
            if len(set(opts)) != len(opts): print("OPT DUP", e["id"], it["n"]); bad += 1
        if "bank" in e and a[0] not in e["bank"]: print("ANSWER NOT IN BANK", e["id"], it["n"]); bad += 1
        for w in it.get("wr", {}):
            if w not in (opts or []): print("WR NOT IN OPTIONS", e["id"], it["n"], w); bad += 1
        if "text" in e and re.search(r"\[\d+\]", e["text"]) and f"[{it['n']}]" not in e["text"]:
            print("GAP MARKER MISSING", e["id"], it["n"]); bad += 1
# simulacro: armarlo por alcance y corregirlo con las respuestas correctas → puntaje perfecto
s.init_db()
for unit in ["", "1", "2", "3", "4", "5"]:
    for minutes in (59, 30):
        r, code = s.api_sim_start({"unit": unit, "minutes": minutes})
        if code != 200 or not r["tasks"]:
            print("SIM SIN TAREAS", unit, minutes); bad += 1; continue
        payload = []
        for tk in r["tasks"]:
            ex = s.BY_ID[tk["id"]]
            ans = {str(it["n"]): (it["a"][0] if isinstance(it["a"], list) else it["a"]) for it in ex["items"]}
            payload.append({"exercise_id": ex["id"], "ns": tk["ns"], "answers": ans})
        res, _ = s.api_sim_finish({"unit": unit, "minutes": minutes, "elapsed": 1, "tasks": payload})
        if res["score"] != res["total"] or res["total"] != r["total_items"]:
            print("SIM PUNTAJE", unit, minutes, res["score"], res["total"], r["total_items"]); bad += 1
# ---- feedback por opción: coherencia + oración completa + cobertura ----
import feedback as fbk
cov = collections.defaultdict(lambda: [0, 0, 0, 0])      # unidad → [distractores, con fb, patrones, con mensaje]
def _parts_ok(v, where):
    global bad
    for p_ in ([["", v]] if isinstance(v, str) else v):
        if isinstance(v, str): continue
        if len(p_) != 2 or p_[0] not in fbk.KINDS:
            print("FB TIPO INVALIDO", where, p_); bad += 1
for e in s.EXERCISES:
    first = s._first_answers(e)
    for it in e["items"]:
        opts = it.get("o") or e.get("options") or []
        a0 = first[it["n"]]
        for o, v in (it.get("fb") or {}).items():
            if o not in opts or o == a0:
                print("FB OPCION INVALIDA", e["id"], it["n"], o); bad += 1
            _parts_ok(v, (e["id"], it["n"]))
        for o in it.get("alt", []) if opts else []:
            if o not in opts: print("ALT NO ESTA EN OPCIONES", e["id"], it["n"], o); bad += 1
        for pr in it.get("pat", []):
            if len(pr) > 2: _parts_ok(pr[2], (e["id"], it["n"]))
        sent = fbk.full_sentence(e, it, first)
        if sent is not None and (re.search(r"\[\d+\]|___|\(\w[^)]*\)\s", sent) or f"**{a0}**" not in sent):
            print("ORACION COMPLETA MAL ARMADA", e["id"], it["n"], sent[:90]); bad += 1
        if opts and "bank" not in e:
            d = [o for o in opts if o != a0 and o not in it.get("alt", [])]
            cov[e["unit"]][0] += len(d); cov[e["unit"]][1] += sum(1 for o in d if o in (it.get("fb") or {}))
        cov[e["unit"]][2] += len(it.get("pat", [])); cov[e["unit"]][3] += sum(1 for pr in it.get("pat", []) if len(pr) > 2)
print("explicación propia por unidad (distractores | patrones de texto libre):")
for u in sorted(cov):
    d, f_, pt, pm = cov[u]
    print(f"  Unit {u}: {f_}/{d} distractores, {pm}/{pt} patrones")
print(len(s.EXERCISES), "ejercicios,", sum(len(e["items"]) for e in s.EXERCISES), "items", dict(sorted(collections.Counter(e["unit"] for e in s.EXERCISES).items())))
print("problemas:", bad)
sys.exit(1 if bad else 0)
