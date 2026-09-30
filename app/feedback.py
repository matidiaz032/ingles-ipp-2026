"""Feedback por opción: oración completa, participios irregulares y explicación de POR QUÉ falla cada distractor.

Datos opcionales en cada ítem (todo lo que falte cae al feedback genérico de siempre):
  "fb":      {opción: explicación}        ítems de opción múltiple. Explicación = "texto" o [["tipo", "texto"], ...]
  "pat":     [[regex, regla, explicación]] respuestas libres: el 3.er elemento es opcional
  "alt":     [respuestas]                  válidas en inglés real pero no las esperadas → CORRECTAS con aviso
  "altnote": "texto"                       el aviso de contexto de esas alternativas
Tipos de explicación: forma (error de forma/ortografía), tiempo (tiempo o marcador equivocado),
valida (gramaticalmente válida, pero no es lo que pide el ejercicio), significado, aviso.
"""
import re

KINDS = {"forma", "tiempo", "valida", "significado", "aviso"}

# base: (pasado, participio) — verbos irregulares de tu booklet (Unit2/03) y otros frecuentes. Sin be/have (ruido).
IRREG = {
    "go": ("went", "gone"), "buy": ("bought", "bought"), "eat": ("ate", "eaten"), "see": ("saw", "seen"),
    "make": ("made", "made"), "take": ("took", "taken"), "give": ("gave", "given"), "find": ("found", "found"),
    "think": ("thought", "thought"), "teach": ("taught", "taught"), "grow": ("grew", "grown"), "get": ("got", "got/gotten"),
    "do": ("did", "done"), "know": ("knew", "known"), "write": ("wrote", "written"), "forget": ("forgot", "forgotten"),
    "fly": ("flew", "flown"), "speak": ("spoke", "spoken"), "break": ("broke", "broken"), "choose": ("chose", "chosen"),
    "drive": ("drove", "driven"), "begin": ("began", "begun"), "send": ("sent", "sent"), "build": ("built", "built"),
    "lose": ("lost", "lost"), "tell": ("told", "told"), "leave": ("left", "left"), "keep": ("kept", "kept"),
    "understand": ("understood", "understood"), "sit": ("sat", "sat"), "stand": ("stood", "stood"), "win": ("won", "won"),
    "wear": ("wore", "worn"), "steal": ("stole", "stolen"), "swim": ("swam", "swum"), "sing": ("sang", "sung"),
    "drink": ("drank", "drunk"), "ride": ("rode", "ridden"), "rise": ("rose", "risen"), "throw": ("threw", "thrown"),
    "show": ("showed", "shown"), "hide": ("hid", "hidden"), "bite": ("bit", "bitten"), "fall": ("fell", "fallen"),
    "feel": ("felt", "felt"), "hear": ("heard", "heard"), "hold": ("held", "held"), "pay": ("paid", "paid"),
    "say": ("said", "said"), "sell": ("sold", "sold"), "meet": ("met", "met"), "mean": ("meant", "meant"),
}
_AUX = {"have", "has", "had", "haven't", "hasn't", "hadn't", "been", "'ve"}


def _words(text):
    return re.findall(r"[a-z']+", (text or "").lower())


def irregular_notes(answer, given=""):
    """Avisos sobre participios irregulares: formas inventadas ('knowed') y el participio correcto de la respuesta."""
    notes, seen = [], set()
    gw, aw = set(_words(given)), _words(answer)
    for base, (past, pp) in IRREG.items():
        for bad in (base + "ed", base + "d"):
            if bad in gw and bad not in seen:
                seen.add(bad)
                notes.append(f"**{bad}** no existe: {base} es irregular → {past} → **{pp}**.")
    if _AUX & set(aw):
        for base, (past, pp) in IRREG.items():
            if pp.split("/")[0] in aw and base not in seen:
                seen.add(base)
                notes.append(f"Participio irregular: {base} → {past} → **{pp}**.")
    return notes


def _segment(ex, n):
    """La oración (o línea numerada) del texto que contiene el hueco [n]."""
    marker = f"[{n}]"
    for line in ex["text"].split("\n"):
        if marker not in line:
            continue
        line = re.sub(r"^\s*\d+\.\s*", "", line)
        for sent in re.split(r"(?<=[.!?])\s+", line):
            if marker in sent:
                return sent
        return line
    return None


def full_sentence(ex, it, first_answers):
    """La oración completa con la respuesta correcta (en **negrita**), o None si no aplica."""
    if ex.get("bank"):
        return None
    a0 = first_answers[it["n"]]
    q = it.get("q")
    if q and "___" in q:
        return q.replace("___", f"**{a0}**", 1)
    if ex.get("text") and f"[{it['n']}]" in ex["text"]:
        seg = _segment(ex, it["n"])
        if not seg:
            return None
        seg = re.sub(r"(\[\d+\])\s*\([^)]*\)", r"\1", seg)          # saca la pista "(work)"
        def fill(m):
            k = int(m.group(1))
            ans = first_answers.get(k, "…")
            return f"**{ans}**" if k == it["n"] else ans
        return re.sub(r"\[(\d+)\]", fill, seg).strip()
    return None


def _norm_parts(v):
    if not v:
        return []
    if isinstance(v, str):
        return [{"kind": "", "msg": v}]
    return [{"kind": k, "msg": m} for k, m in v]


def explain(ex, it, given, correct, note, gnorm, first_answers, is_choice):
    """→ {"sentence", "parts", "alt", "irr"} para mostrar junto al resultado."""
    a = it["a"] if isinstance(it["a"], list) else [it["a"]]
    out = {"sentence": full_sentence(ex, it, first_answers), "parts": [], "alt": False, "irr": []}
    if correct and note:
        out["alt"] = True
        out["parts"] = [{"kind": "aviso", "msg": note}]
    elif not correct and given:
        if is_choice:
            out["parts"] = _norm_parts((it.get("fb") or {}).get(given))
        else:
            for pr in it.get("pat", []):
                if len(pr) > 2 and re.search(pr[0], gnorm):
                    out["parts"] = _norm_parts(pr[2])
                    break
    if not (is_choice and ex["format"] in ("tense_id", "vocab_def", "reading_discrete", "comprehension", "cross_text")):
        out["irr"] = irregular_notes(a[0], given if not correct else "")
        if any(p["kind"] == "forma" for p in out["parts"]):        # ya hay una explicación de forma escrita a mano: no repetir
            out["irr"] = [t for t in out["irr"] if not t.startswith("**")]
    return out
