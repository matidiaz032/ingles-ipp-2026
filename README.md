# Práctica IPP English (Unidades 1 a 5)

Herramienta **local y gratuita** para practicar inglés de nivel intermedio (contenido del curso IPP de Silicon Misiones) con los formatos del examen **Cambridge Linguaskill Reading**. Registra en qué reglas gramaticales fallás y te hace practicar más esas. Funciona en la PC y en el celular (Android), sin internet y sin instalar librerías.

- 138 ejercicios / 837 ítems de las Unidades 1 a 5 (tiempos verbales, used to, futuros, condicionales, wish, modales, passive, vocabulario IT).
- Formatos: open cloze, multiple choice cloze, gapped text, cross-text, comprehension, identificar tiempos y más.
- Explicación de **por qué falla cada opción** (Unit 1 completa; las otras unidades usan un mensaje genérico por ahora).
- Seguimiento de errores por regla, práctica dirigida y **simulacro cronometrado**.
- Opcional: consultor de vocabulario con IA (Hugging Face) y sincronización PC ↔ celular con Syncthing.

> Proyecto personal hecho por un estudiante. Las explicaciones las escribió una IA y pueden tener errores: si ves uno, abrí un *issue*.

## Inicio rápido

Requisito: **Python 3.10 o superior** ([python.org](https://www.python.org/downloads/)). No hay nada más que instalar.

```bash
git clone https://github.com/matidiaz032/ingles-ipp-2026.git
cd ingles-ipp-2026
python app/server.py
```

Abrí <http://127.0.0.1:8765>. En Windows también podés hacer doble clic en `practicar.bat`. Tu progreso se guarda en `data/progress.sqlite` (se crea solo; borrarlo lo reinicia).

**Celular:** `python tools/make_mobile_zip.py` genera un zip para instalar con Termux (ver la sección *En el celular*).

## Qué usa el autor y no viene en el repo

La herramienta corre sola, pero hay partes pensadas para el uso personal del autor. Si la usás tal cual la bajás, esto es lo que cambia:

| Qué | Cómo lo usa el autor | Qué pasa si no lo tenés |
|---|---|---|
| **Booklet y tests originales del curso** (PDF) | Base para armar los ejercicios y las reglas. Son material del instituto, no se publican. | Nada: los ejercicios ya están en `data/`. |
| **Apuntes en Obsidian** | La carpeta `obsidian-notes/` apunta (con enlaces simbólicos) a su vault, organizado por unidad. Las reglas de `data/rules.json` citan esos apuntes, y el consultor con IA los lee. | Las reglas se ven igual, pero sin el apunte asociado, y el consultor responde sin tu terminología. Podés crear `obsidian-notes/` con tus propios `.md`. |
| **Historial de errores propios** (`data/history-seed.json`) | Sus errores reales en 5 tests, cargados como punto de partida para saber qué reglas reforzar. Es personal, no se publica. | Empezás con el historial vacío: la app detecta tus puntos débiles a medida que practicás. Para partir de tus errores reales, copiá `data/history-seed.example.json` a `data/history-seed.json` y reemplazá las entradas (una por pregunta fallada: `source`, `question`, `rule` de `data/rules.json`, `given`). Se carga una sola vez por `source`. |
| **Hugging Face** (IA) | Pantalla *Consultar* y glosario. Usa su token gratuito. | Todo lo demás funciona sin internet. Para *Consultar* necesitás tu propio token (ver la sección de IA más abajo). El cupo gratuito es limitado. |
| **Glosario en Obsidian** | *Guardar en mi glosario* agrega entradas a un `.md` de su vault. | Sin vault, guarda en `data/glosario-pendiente.md`. |
| **Syncthing + Termux** | Sincroniza PC y celular Android. | Opcional: sin eso, usá solo la PC o el exportar/importar manual. |

Además, el contenido de las unidades 2 a 5 todavía no tiene explicación por opción (las 5 unidades completas). Las explicaciones las redactó una IA y pueden tener errores.

## Correr

```
python app/server.py        # o doble click en practicar.bat
```
Abre http://127.0.0.1:8765 (elegí la unidad arriba). Para probar sin tocar tu historial: variable de entorno `IPP_DB` con otra ruta. Tu historial queda en `data/progress.sqlite` (se crea solo, con los 4 errores de tu Test 1 como punto de partida; borrarlo lo reinicia).

## Qué hay
- `data/rules.json` — catálogo de reglas (cada error se etiqueta con una; cada una apunta a tu apunte de Obsidian).
- `data/unit1..5/*.json` — 138 ejercicios / 837 ítems: Unit 1 (36 / 196), Unit 2 (29 / 183: pasados, used to, relative clauses), Unit 3 (23 / 134: futuros, time clauses, about to/due to/likely to), Unit 4 (24 / 155: conditionals, unless/in case, wish, conectores), Unit 5 (26 / 170: modales presente y pasado, would, semi-modales, passive voice). Formatos: gap-fill con verbo, open cloze, multiple choice cloze, discrete cloze, identificar tiempo/categoría, elegir la oración correcta, gapped text (oraciones y párrafos), cross-text matching, reading discrete, comprehension (5 y 2 ítems), vocabulario IT. Los `linguaskill-*.json` siguen las pautas oficiales de Cambridge (open cloze = solo palabras gramaticales).
- `data/history-seed.json` — errores de tus tests (Test 1: 4, Test 2: 15, Test 3: 6, Test 4: 5, Test 5: 4). Se cargan una sola vez por test (por `source`), sin pisar tu historial.
- `app/` — servidor + interfaz.

## Retomar donde lo dejaste
Cada vez que corregís un ejercicio se guarda tu posición en la cola. En el inicio aparece **▶ Continuar donde lo dejaste** (ejercicio X de N); *Descartar* la borra. La posición **se sincroniza entre PC y celular** junto con tu progreso (misma carpeta de sync; gana la más reciente): si avanzás en la PC, el celular te lo muestra al abrir el inicio. Las respuestas ya corregidas se registran siempre, aunque no toques *Terminar*. Para que llegue rápido, antes de cambiar de dispositivo apretá *Sincronizar ahora* en *Progreso* en los dos. Hace falta tener la sincronización automática configurada (si no, queda solo en ese dispositivo).

## Feedback por opción (por qué falla CADA distractor)
Al corregir, cada ítem muestra: la **oración completa correcta** (con la respuesta en negrita), los **participios irregulares** (know → knew → **known**, y avisa de formas inventadas como *knowed*) y, si el ítem lo tiene, **por qué falla justo la opción que elegiste**, con etiquetas: *Forma*, *Tiempo*, *Válida, pero…* (gramaticalmente posible pero no es lo que pide el ejercicio), *Significado*. Una opción con dos errores los muestra por separado. Sin explicación propia, cae al mensaje genérico de siempre.

Formato en los JSON (todo opcional, por ítem): `"fb": {"opción": [["forma","texto"],["tiempo","texto"]]}` para opción múltiple; en respuesta libre, un 3.er elemento en `pat`: `["regex","regla",[["forma","texto"]]]`; `"alt": [respuestas]` + `"altnote": "aviso"` para respuestas válidas en inglés real pero no esperadas: cuentan como **correctas con aviso de contexto** (no castigan tus reglas). **Las 5 unidades están completas: todos los distractores (1.403) y patrones (454) tienen explicación propia** (el validador muestra la cobertura exacta por unidad). `python tools/validate.py` revisa el formato y muestra la **cobertura** por unidad (distractores y patrones con explicación propia). La regla *Present Perfect vs Past Simple* ahora dice **momento CERRADO** (yesterday, last week, ago) vs **período ABIERTO hasta ahora** (for, since, so far).

## Cómo se detectan tus patrones de error
Cada respuesta se guarda con la regla asociada. Si es incorrecta, la regla sale de (1) el distractor elegido en opción múltiple, (2) un patrón sobre lo que escribiste en respuesta libre (ej. `doesn't works` → *do/does + verbo base*), o (3) la regla base del ítem. El score por regla pondera más los intentos recientes (0,85 por posición) con suavizado; ≥0,30 con 3+ intentos = "a reforzar". La práctica dirigida prioriza ejercicios de esas reglas.

## Validar el contenido
`python tools/validate.py` corrige cada respuesta esperada contra el motor y avisa si una regla, opción o hueco está mal armado. Usa una base temporal: no toca tu historial.

## Agregar ejercicios
Copiá la estructura de cualquier ejercicio en `data/unit1/`. Al arrancar el servidor valida que las reglas existan. Respuestas libres: `a` = aceptadas, `alt` = válida pero no la esperada, `pat` = [regex, regla] para clasificar errores típicos.

## En el celular (Android) y sincronización
`python tools/make_mobile_zip.py` genera `mobile/ipp-mobile.zip` (app + una copia de tu progreso actual). Se instala con **Termux** siguiendo `LEEME-CELULAR.txt` (viene dentro del zip): instalar Termux, pasar el zip a Descargas, `pkg install python`, descomprimir y `bash ~/ipp/start.sh`. Después se practica desde Chrome en `http://localhost:8765`, sin internet. La pantalla se adapta al ancho del celular.

Para mantener PC y celular iguales: *Progreso → Exportar progreso* en uno, *Importar progreso* en el otro. Cada respuesta tiene un ID estable, así que la fusión no duplica ni borra nada y se puede repetir. La primera vez que arranca una versión con sync sobre una base anterior, el servidor guarda una copia (`data/progress.pre-sync-backup.sqlite`) antes de migrarla.

## Simulacro Linguaskill
Desde el inicio → *Configurar simulacro*. Arma ~15 tareas mezcladas solo con formatos de Linguaskill (open cloze, multiple choice cloze, discrete cloze, reading discrete, gapped text, cross-text, comprehension 5 y 2 ítems), una por pantalla, sin volver atrás ni corrección hasta el final, con cuenta regresiva de 59 / 45 / 30 min. Al terminar (o al acabarse el tiempo) muestra puntaje, resultado por formato, reglas donde más fallaste y la revisión de cada error. Lo que dejás sin responder cuenta como incorrecto pero no castiga tus reglas débiles. No es adaptativo: sirve para comparar simulacros entre sí, no para estimar tu nivel. Se guarda el historial en *Progreso*.

## Sincronización automática PC ↔ celular (carpeta compartida)
En *Progreso → Sincronización automática* elegís un **nombre de dispositivo** (`pc`, `celu`) y una **carpeta**. Cada ~45 s la app escribe *su propio* archivo `ipp-sync-<nombre>.json` en esa carpeta e importa los de los demás dispositivos. Como cada respuesta tiene un ID estable, importar es idempotente: repetir, archivos viejos o copias de conflicto no duplican ni borran nada, y si un archivo llega a medias se reintenta solo. La carpeta la comparte una herramienta externa: **Syncthing** (gratis, sin nube; en Android, Syncthing-Fork desde F-Droid). La app no sube nada a ningún servidor.

Pasos: (1) instalar Syncthing en PC y celular y compartir una carpeta `IPP-sync`; (2) en la app de cada dispositivo poner nombre distinto y la ruta de esa carpeta (en Termux: `~/storage/shared/IPP-sync`, tras `termux-setup-storage`); (3) *Guardar y sincronizar*. También se puede fijar con las variables `IPP_SYNC_DIR` / `IPP_DEVICE`. El exportar/importar manual sigue disponible. La configuración queda en `data/sync.json` (fuera del repo y fuera del zip del celular).

Para actualizar el código del celular sin perder su progreso: `python tools/make_mobile_zip.py --sin-progreso` genera `mobile/ipp-mobile-update.zip` (sin base de datos, token ni configuración).

## Consultar con IA + glosario (Hugging Face)
Pantalla *Inicio → 📖 Consultar* (`app/static/consultar.html`, lógica en `app/ai.py`, rutas `/api/ai/lookup`, `/api/ai/save`, `/api/glossary`). Escribís una palabra, frase o estructura (ej. `be able to`) y, opcionalmente, la oración donde la viste. Antes de preguntarle al modelo, la app busca en tus apuntes de `obsidian-notes/` las secciones relacionadas y se las pasa como referencia (así usa tu terminología). Devuelve, en español: significado en ese contexto, cómo se usa, ejemplos, diferencia con parecidos y error típico. Si el término depende del contexto y no diste oración, **te la pide**. Es independiente del motor de ejercicios: no toca tu progreso.

**Glosario:** el botón *Guardar en mi glosario* agrega la entrada al final de `obsidian-notes/Referencia-General/99 Glosario y dudas.md` (tu vault real) como callout `[!warning] Sugerencia de IA — sin revisar`, con enlaces `[[...]]` a tus apuntes relacionados. Cuando la investigues y la corrijas en Obsidian, cambiá `[!warning]` por `[!tip]`. La app **solo agrega al final; nunca edita ni reescribe** lo que ya está. Las consultas repetidas sin oración salen de la base local sin gastar cupo. Si no existe el vault en el dispositivo (ej. Termux), guarda en `data/glosario-pendiente.md`.

**Necesita internet** y un token de Hugging Face (gratis: huggingface.co/settings/tokens, tipo *fine-grained* con permiso "Make calls to Inference Providers"), en la variable `HF_TOKEN` o en `data/hf_token.txt` (una línea; fuera del repo y del zip del celular). Modelo por defecto `openai/gpt-oss-120b` (probando Fireworks, Novita y `cheapest`; configurable con `HF_MODEL`).

**Ojo con el cupo:** el nivel gratuito de Hugging Face incluye créditos mensuales limitados y **se pueden agotar** (la app avisa con un mensaje claro cuando pasa: error 402). Se renuevan cada mes; para más hay que comprar créditos o suscribirse a PRO.

Probar sin navegador: `python app/ai.py "be able to" "I wasn't able to fix the bug"`. El texto de la IA es una **sugerencia**: puede equivocarse; tus apuntes mandan.

## Pendiente
La regla `adv-freq-position` y el uso de *look/seem* como state verbs no están en tus apuntes de Unit 1 (agregalos a Obsidian si querés que la herramienta cite el apunte).

