"""Consultor de inglés con IA (Hugging Face) apoyado en TUS apuntes de Obsidian.

Le das una palabra, frase o estructura (y opcionalmente la oración donde la viste) y devuelve una explicación en
español: significado en ese contexto, cómo se usa, ejemplos, diferencia con parecidos y error típico. Antes de
preguntarle al modelo busca en obsidian-notes/ lo que tengas escrito sobre el tema y se lo pasa como referencia.

Requiere internet y un token de Hugging Face (gratis), leído de la variable de entorno HF_TOKEN o del archivo
data/hf_token.txt (una línea; está en .gitignore y no viaja en el zip del celular).

Probar sin servidor:   python app/ai.py "be able to" "I wasn't able to fix the bug"
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTES_DIR = ROOT / "obsidian-notes"
ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"
TOKEN_FILE = ROOT / "data" / "hf_token.txt"
# Si HF_MODEL está definido se usa solo ese. Si no, se prueban en orden: Cerebras/Groq/Together dieron 403 de Cloudflare.
_ENV_MODEL = os.environ.get("HF_MODEL", "").strip()
DEFAULT_MODELS = [_ENV_MODEL] if _ENV_MODEL else [
    "openai/gpt-oss-120b:fireworks-ai",
    "openai/gpt-oss-120b:novita",
    "openai/gpt-oss-120b:cheapest",
]
MAX_TERM, MAX_SENTENCE = 80, 400
TIMEOUT_S = 40

PROMPT = """Sos un tutor de inglés para un hispanohablante rioplatense (usá voseo) que es programador y prepara el examen Linguaskill Reading (B1/B2). Explicá SIEMPRE en español.
Recibís un TÉRMINO (palabra, frase o estructura), a veces una ORACIÓN donde apareció, y a veces APUNTES del propio alumno.

Reglas:
- Si el significado del término depende del contexto, no hay ORACIÓN y no podés explicarlo bien sin ella, respondé SOLO una línea: NEEDS_CONTEXT: <pedido breve, en español, para que pase la oración completa donde lo vio>.
- Si no, respondé en Markdown con exactamente estas secciones, en este orden y con estos títulos en negrita:
**Significado** (si hay ORACIÓN, qué significa ahí; si no, los sentidos principales)
**Cómo se usa** (estructura y cuándo sí / cuándo no)
**Ejemplos** (3 oraciones en inglés con su traducción, contexto de trabajo o IT)
**Diferencia con parecidos** (con qué se confunde y en qué se distingue; si no aplica, escribí "—")
**Error típico** (el error más común de hispanohablantes)
- Usá los APUNTES solo si son relevantes, sin contradecirlos ni copiarlos enteros. Si no cubren el tema, no lo menciones.
- No inventes reglas: si no estás seguro de algo, decilo. Máximo 250 palabras."""

STOP = {"the", "and", "for", "you", "are", "was", "were", "has", "have", "had", "not", "can", "to", "of", "in",
        "on", "it", "is", "be", "a", "an", "i", "at", "as", "or", "so", "do", "does", "did"}


class HFError(Exception):
    """Problema al hablar con Hugging Face (token, red, formato de la respuesta)."""
    retryable = False    # True: conviene probar con otro proveedor (403/429/5xx/red)


def get_token():
    tok = os.environ.get("HF_TOKEN", "").strip()
    if tok:
        return tok
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8-sig").strip()
    return ""


def _post(messages, model):
    token = get_token()
    if not token:
        raise HFError(
            "Falta el token de Hugging Face. Definí la variable de entorno HF_TOKEN (o creá data/hf_token.txt con "
            "el token en una sola línea) y reiniciá el servidor. Se consigue gratis en https://huggingface.co/settings/tokens "
            "(token 'fine-grained' con el permiso 'Make calls to Inference Providers').")
    body = json.dumps({"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 1500}).encode("utf-8")
    req = urllib.request.Request(ROUTER_URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        hint = " (¿el token es válido y tiene permiso de Inference Providers?)" if e.code in (401, 403) else ""
        if "<html" in detail.lower():
            detail = "el proveedor rechazó la petición (bloqueo de su firewall)"
        if e.code == 402:
            raise HFError("Se agotó el cupo gratuito mensual de Hugging Face. Se renueva con el mes nuevo (o podés comprar créditos / "
                          "suscribirte a PRO en huggingface.co/settings/billing). Tu glosario guardado sigue disponible para leer.") from e
        err = HFError(f"Hugging Face devolvió {e.code}{hint}: {detail}")
        err.retryable = e.code in (403, 408, 429) or e.code >= 500
        raise err from e
    except urllib.error.URLError as e:
        err = HFError(f"No se pudo conectar con Hugging Face ({e.reason}). ¿Hay internet?")
        err.retryable = True
        raise err from e
    except TimeoutError as e:
        err = HFError("Hugging Face tardó demasiado en responder (timeout).")
        err.retryable = True
        raise err from e
    try:
        content = (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        raise HFError(f"Respuesta inesperada de Hugging Face: {json.dumps(data)[:300]}")
    if not content:
        err = HFError("El modelo devolvió una respuesta vacía.")
        err.retryable = True
        raise err
    return content


# ---------- búsqueda en tus apuntes ----------
def _note_chunks():
    """(archivo, título de sección, texto) de cada sección de tus notas. Sigue los symlinks del vault."""
    out = []
    if not NOTES_DIR.exists():
        return out
    for dirpath, _dirs, files in os.walk(NOTES_DIR, followlinks=True):
        for fn in files:
            if not fn.endswith(".md") or fn.startswith("99 Glosario"):      # el glosario de la IA no es un apunte
                continue
            try:
                text = (Path(dirpath) / fn).read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError):
                continue
            title, buf = fn[:-3], []
            for line in text.splitlines():
                if line.startswith("#") and buf:
                    out.append((fn[:-3], title, "\n".join(buf)))
                    buf = []
                if line.startswith("#"):
                    title = line.lstrip("# ").strip()
                buf.append(line)
            if buf:
                out.append((fn[:-3], title, "\n".join(buf)))
    return out


def find_notes(term, sentence="", limit=3, budget=3500):
    """Las secciones de tus apuntes más relacionadas con el término. → [(archivo, sección, texto)]"""
    phrase = re.sub(r"\s+", " ", term.lower()).strip()
    toks = [t for t in re.findall(r"[a-záéíóúñ']+", phrase) if t not in STOP and len(t) > 1]
    scored = []
    for fn, title, text in _note_chunks():
        low = text.lower()
        score = 6 * low.count(phrase) if len(phrase) > 2 else 0
        hits = [t for t in toks if t in low]
        if toks and len(hits) * 2 < len(toks) and not score:
            continue
        score += sum(min(low.count(t), 3) for t in hits) + (4 if any(t in title.lower() for t in toks) else 0)
        if score >= 3:
            scored.append((score, fn, title, text))
    scored.sort(key=lambda x: -x[0])
    picked, used = [], 0
    for _s, fn, title, text in scored[:limit]:
        text = text[:1200]
        if used + len(text) > budget:
            break
        picked.append((fn, title, text))
        used += len(text)
    return picked


# ---------- consulta ----------
def lookup(term, sentence=""):
    term = re.sub(r"\s+", " ", (term or "")).strip()
    sentence = re.sub(r"\s+", " ", (sentence or "")).strip()
    if not term:
        raise HFError("Escribí la palabra, frase o estructura que querés consultar.")
    if len(term) > MAX_TERM:
        raise HFError(f"El término es demasiado largo (máx. {MAX_TERM} caracteres). Para una oración completa usá el campo de la oración.")
    if len(sentence) > MAX_SENTENCE:
        raise HFError(f"La oración es demasiado larga (máx. {MAX_SENTENCE} caracteres).")
    notes = find_notes(term, sentence)
    user = f"TÉRMINO: {term}\nORACIÓN: {sentence or '(no la dio)'}"
    if notes:
        user += "\n\nAPUNTES DEL ALUMNO:\n" + "\n\n".join(f"[{fn} › {title}]\n{text}" for fn, title, text in notes)
    messages = [{"role": "system", "content": PROMPT}, {"role": "user", "content": user}]
    content, used, last = None, None, None
    for m in DEFAULT_MODELS:
        try:
            content, used = _post(messages, m), m
            break
        except HFError as e:
            last = e
            if not e.retryable:
                raise
    if content is None:
        raise last
    notes_used = sorted({fn for fn, _t, _x in notes})
    if content.upper().startswith("NEEDS_CONTEXT:") and not sentence:
        return {"needs_context": True, "question": content.split(":", 1)[1].strip(), "term": term,
                "notes": notes_used, "model": used}
    if content.upper().startswith("NEEDS_CONTEXT:"):       # pidió contexto pese a tenerlo: mostrar igual lo que haya
        content = content.split(":", 1)[1].strip()
    return {"needs_context": False, "term": term, "sentence": sentence, "body": content, "notes": notes_used, "model": used}


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")     # la consola de Windows (cp1252) no soporta → etc.
    args = sys.argv[1:]
    if not args:
        print('Uso: python app/ai.py "be able to" ["oración donde lo viste"]')
        sys.exit(1)
    try:
        r = lookup(args[0], args[1] if len(args) > 1 else "")
    except HFError as e:
        print("Error:", e)
        sys.exit(1)
    if r["needs_context"]:
        print("La IA pide más contexto:", r["question"])
    else:
        print(r["body"])
    print("\n[apuntes usados:", ", ".join(r["notes"]) or "ninguno", "| modelo:", r["model"] + "]")
