const $app = document.getElementById('app');
const FORMATS = {
  verb_gap: 'Gap-fill (verbo dado)', open_cloze: 'Open cloze', mc_cloze: 'Multiple choice cloze',
  discrete_cloze: 'Discrete cloze', tense_id: 'Identificar el tiempo', sentence_choice: 'Elegir la oración correcta',
  gapped_sentences: 'Gapped text (oraciones)', gapped_paragraphs: 'Gapped text (párrafos)', cross_text: 'Cross-text matching', reading_discrete: 'Reading discrete', comprehension: 'Comprehension',
  vocab_def: 'Vocabulario IT'
};
const STATUS = { weak: 'a reforzar', watch: 'a vigilar', ok: 'bien', new: 'sin datos' };
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const md = s => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
const api = (u, opt) => fetch(u, opt).then(r => r.json());
let session = null;
let sim = null;
// --- retomar donde lo dejaste: lo guarda el servidor de cada dispositivo y se sincroniza entre PC y celular
// (gana el más reciente); localStorage queda de respaldo por si el servidor no responde ---
const RESUME_KEY = 'resume';
const qLabel = q => [q.get('unit') ? 'Unit ' + q.get('unit') : 'Todas las unidades', q.get('format') ? FORMATS[q.get('format')] : '',
  q.get('rule') ? 'una regla' : '', q.get('mode') === 'weak' ? 'práctica dirigida' : '', q.get('mode') === 'repaso' ? 'repaso final' : ''].filter(Boolean).join(' · ');
const validResume = r => r && r.ids && r.ids.length && r.i < r.ids.length ? r : null;
const localResume = () => { try { return validResume(JSON.parse(localStorage.getItem(RESUME_KEY) || 'null')); } catch { return null; } };
const loadResume = async () => {
  try { const r = await api('/api/resume'); return validResume(r); } catch { return localResume(); }
};
const postResume = r => fetch('/api/resume', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(r) }).catch(() => {});
const clearResume = () => { try { localStorage.removeItem(RESUME_KEY); } catch {} return postResume({ ids: [], i: 0, qs: '', ts: Date.now() }); };
const saveResume = nextI => { try {
  if (!session || session.sim) return;
  if (nextI >= session.ids.length) return clearResume();
  const r = { ids: session.ids, i: nextI, qs: session.q.toString(), ts: Date.now() };
  try { localStorage.setItem(RESUME_KEY, JSON.stringify(r)); } catch {}
  postResume(r);
} catch {} };
const UNITS = { '': 'Todas las unidades', '1': 'Unit 1 — Present tenses, comparatives, too/enough', '2': 'Unit 2 — Past tenses, used to, relative clauses', '3': 'Unit 3 — Future forms, future time clauses', '4': 'Unit 4 — Conditionals, wish / if only, connectors', '5': 'Unit 5 — Modal verbs, passive voice, semi-modals' };
const getUnit = () => { try { return localStorage.getItem('unit') || ''; } catch { return ''; } };
const setUnit = u => { try { localStorage.setItem('unit', u); } catch {} };

async function route() {
  const [path, query] = (location.hash.slice(1) || '/').split('?');
  if (path !== '/sim/run' && sim && sim.timer) { clearInterval(sim.timer); sim.timer = null; }
  if (path === '/resume') return resumeSession();
  if (path === '/repaso') return startRepaso();
  if (path === '/repaso/report') return repasoReport();
  if (path === '/sim') return simSetup();
  if (path === '/sim/run') return sim ? simShow() : (location.hash = '#/sim');
  if (path === '/progress') return progress();
  if (path === '/run') return startSession(new URLSearchParams(query));
  return home();
}
window.addEventListener('hashchange', route);
route();

async function home() {
  const [stats, exs, resume] = await Promise.all([api('/api/stats'), api('/api/exercises'), loadResume()]);
  const unit = getUnit();
  const weak = stats.rules.filter(r => (r.status === 'weak' || r.status === 'watch') && (!unit || String(r.unit) === unit)).slice(0, 4);
  const inUnit = exs.filter(e => !unit || String(e.unit) === unit);
  const done = inUnit.filter(e => e.seen).length;
  $app.innerHTML = `
    <div class="card"><h1>Práctica IPP</h1>
      <select class="filter" id="unitsel">${Object.entries(UNITS).map(([k, v]) => `<option value="${k}" ${k === unit ? 'selected' : ''}>${v}</option>`).join('')}</select>
      <div class="mute" style="margin-top:8px">${inUnit.length} ejercicios · ${done} ya intentados · ${stats.total} respuestas registradas</div>
      <div class="row">
        <a class="btn" href="#/run?mode=weak&unit=${unit}">Práctica dirigida (mis reglas débiles)</a>
        <a class="btn secondary" href="#/run?mode=all&unit=${unit}">Todo lo de esta selección</a>
      </div></div>
    <div class="card" style="border-color:var(--warn)"><h2>⏱ Repaso final (todas las unidades)</h2>
      <div class="mute">Unos 20 ejercicios cortos en los formatos de tus tests, mezclando las 5 unidades y poniendo primero lo que menos practicaste y lo que más fallaste. Al final (o cuando quieras) ves en qué estás más flojo.</div>
      <div class="row"><a class="btn" href="#/repaso">Empezar repaso</a><a class="btn secondary" href="#/repaso/report">Ver diagnóstico</a></div></div>
    ${(() => { const r = resume; return r ? `<div class="card"><h2>▶ Continuar donde lo dejaste</h2>
      <div class="mute">Ejercicio ${r.i + 1} de ${r.ids.length} · ${esc(qLabel(new URLSearchParams(r.qs)))}</div>
      <div class="row"><a class="btn" href="#/resume">Continuar</a><a class="btn secondary" href="#/" id="dropresume">Descartar</a></div></div>` : ''; })()}
    <div class="card"><h2>Simulacro Linguaskill Reading</h2>
      <div class="mute">Tareas mezcladas en formato del examen, una por pantalla, sin volver atrás ni corrección hasta el final, con cuenta regresiva.</div>
      <div class="row"><a class="btn" href="#/sim">Configurar simulacro →</a></div></div>
    <div class="card"><h2>📖 Consultar una palabra o estructura (IA)</h2>
      <div class="mute">Preguntá qué significa algo (ej. <i>be able to</i>), pasá la oración donde lo viste y guardalo en tu glosario de Obsidian. Necesita internet.</div>
      <div class="row"><a class="btn secondary" href="consultar.html">Consultar →</a></div></div>
    <div class="card"><h2>Reglas que más estás fallando</h2>
      ${weak.length ? weak.map(r => `<div class="row" style="margin:6px 0"><span class="st ${r.status}">${STATUS[r.status]}</span>
        <span style="flex:1">${esc(r.name)}</span><a href="#/run?rule=${r.id}">practicar →</a></div>`).join('') : '<div class="mute">Todavía no hay datos suficientes.</div>'}
      <div class="mute" style="margin-top:8px">Incluye los 4 errores de tu Test 1 como punto de partida.</div></div>
    <div class="card"><h2>Por formato (Linguaskill / tu test)</h2>
      <div class="row">${Object.entries(FORMATS).map(([k, v]) => `<a class="btn secondary" href="#/run?format=${k}&unit=${unit}">${v}</a>`).join('')}</div></div>
    <div class="card"><h2>Por regla</h2>
      <select class="filter" id="rulesel"><option value="">Elegí una regla…</option>
      ${stats.rules.slice().sort((a, b) => a.group.localeCompare(b.group)).map(r => `<option value="${r.id}">${esc(r.group)} — ${esc(r.name)}</option>`).join('')}</select></div>`;
  const dr = document.getElementById('dropresume'); if (dr) dr.onclick = async () => { await clearResume(); home(); };
  document.getElementById('unitsel').onchange = e => { setUnit(e.target.value); home(); };
  document.getElementById('rulesel').onchange = e => e.target.value && (location.hash = '#/run?rule=' + e.target.value);
}

async function startSession(q) {
  const qs = new URLSearchParams({ mode: q.get('mode') || 'all', format: q.get('format') || '', rule: q.get('rule') || '', unit: q.get('unit') || '' });
  const [ids, exs] = await Promise.all([api('/api/queue?' + qs), api('/api/exercises')]);
  if (!ids.length) { $app.innerHTML = '<div class="card">No hay ejercicios para ese filtro todavía. <a href="#/">Volver</a></div>'; return; }
  session = { ids, exs: Object.fromEntries(exs.map(e => [e.id, e])), i: 0, ok: 0, total: 0, q };
  showExercise();
}

async function startRepaso() {
  const [rp, exs] = await Promise.all([api('/api/repaso/start'), api('/api/exercises')]);
  session = { ids: rp.ids, exs: Object.fromEntries(exs.map(e => [e.id, e])), i: 0, ok: 0, total: 0, q: new URLSearchParams('mode=repaso') };
  $app.innerHTML = `<div class="card"><h1>Repaso final</h1>
    <p>${rp.ids.length} ejercicios · ${rp.items} respuestas · unos <b>${rp.minutes} minutos</b>.</p>
    <p class="mute">Ejercicios por unidad: ${Object.entries(rp.per_unit).sort().map(([u, n]) => `Unit ${u}: ${n}`).join(' · ')}. Van intercalados, así que aunque no llegues al final vas a haber pasado por todas.</p>
    <p class="mute">No te quedes trabado: si no sabés una, respondé lo que te parezca y leé la explicación. En cualquier momento podés abrir <b>Diagnóstico</b>.</p>
    <div class="row"><button id="go">Empezar →</button><a class="btn secondary" href="#/">Volver</a></div></div>`;
  document.getElementById('go').onclick = () => { showExercise(); window.scrollTo(0, 0); };
}

async function repasoReport() {
  const r = await api('/api/repaso/report');
  const pct = (ok, t) => t ? Math.round(100 * ok / t) : 0;
  const col = p => p >= 80 ? 'var(--ok)' : p >= 60 ? 'var(--warn)' : 'var(--bad)';
  const units = r.units.slice().sort((a, b) => (a.total ? pct(a.ok, a.total) : 101) - (b.total ? pct(b.ok, b.total) : 101));
  $app.innerHTML = `<div class="card"><h1>Diagnóstico del repaso</h1>
    <div class="mute">Respuestas desde ${esc(r.since.replace('T', ' '))}: <b>${r.ok}/${r.total}</b>${r.total ? ' (' + pct(r.ok, r.total) + '%)' : ''}</div></div>
    <div class="card"><h2>Por unidad (de más floja a más firme)</h2>
      ${r.total ? `<table>${units.map(u => { const p = pct(u.ok, u.total); return `<tr><td>${esc(UNITS[String(u.unit)] || 'Unit ' + u.unit)}</td>
        <td>${u.total ? `${u.ok}/${u.total} · <b>${p}%</b>` : '<span class="mute">sin responder todavía</span>'}</td>
        <td><div class="bar"><i style="width:${p}%;background:${col(p)}"></i></div></td></tr>`; }).join('')}</table>` : '<div class="mute">Todavía no respondiste nada en este repaso.</div>'}</div>
    <div class="card"><h2>Reglas que fallaste (repasá estas primero)</h2>
      ${r.rules.length ? r.rules.map(d => `<div class="row" style="margin:8px 0;align-items:flex-start">
        <span class="st ${d.bad >= 2 ? 'weak' : 'watch'}">${d.bad} de ${d.total}</span>
        <span style="flex:1">${esc(d.name)}<div class="mute">${esc(d.group)}${d.given.length ? ' · pusiste: ' + d.given.map(esc).join(' / ') : ''}</div></span>
        <a href="#/run?rule=${d.id}">practicar →</a></div>`).join('') : '<div class="mute">Ninguna por ahora.</div>'}</div>
    <div class="row">${session && session.q.get('mode') === 'repaso' && session.i < session.ids.length - 1 ? '<button id="back">Seguir con el repaso →</button>' : '<a class="btn" href="#/repaso">Nuevo repaso</a>'}<a class="btn secondary" href="#/">Inicio</a></div>`;
  const bk = document.getElementById('back');
  if (bk) bk.onclick = () => { session.i++; history.replaceState(null, '', '#/run-repaso'); showExercise(); window.scrollTo(0, 0); };
}

async function resumeSession() {
  const r = await loadResume();
  if (!r) { location.hash = '#/'; return; }
  const exs = await api('/api/exercises');
  const byId = Object.fromEntries(exs.map(e => [e.id, e]));
  const ids = r.ids.filter(id => byId[id]);            // por si cambió el contenido
  if (!ids.length) { clearResume(); location.hash = '#/'; return; }
  session = { ids, exs: byId, i: Math.min(r.i, ids.length - 1), ok: 0, total: 0, q: new URLSearchParams(r.qs) };
  showExercise();
}

function gapHtml(ex, it) {
  const n = it.n;
  if (ex.bank) {
    const L = 'ABCDEFGH';
    return `<select class="gap" data-n="${n}"><option value="">—</option>${ex.bank.map((b, i) => `<option value="${esc(b)}">${L[i]}</option>`).join('')}</select>`;
  }
  if (it.o) return `<select class="gap" data-n="${n}"><option value="">—</option>${it.o.map(o => `<option value="${esc(o)}">${esc(o)}</option>`).join('')}</select>`;
  return `<input class="gap ${ex.format === 'verb_gap' ? 'wide' : ''}" data-n="${n}" autocomplete="off" spellcheck="false">`;
}

function exerciseBody(ex) {
  const hasInline = it => ex.text && ex.text.includes(`[${it.n}]`);
  let body = '';
  const passageClass = ex.format === 'reading_discrete' ? 'passage msg' : 'passage';
  if (ex.text) {
    let t = esc(ex.text).replace(/\[(\d+)\]/g, (_, n) => {
      const it = ex.items.find(i => i.n === +n);
      return it ? `<span class="slot" data-slot="${n}"><sup>${n}</sup>${gapHtml(ex, it)}</span>` : _;
    }).replace(/\n/g, '<br>');
    body += `<div class="${passageClass}">${t}</div>`;
  }
  if (ex.bank) body += `<ul class="bank">${ex.bank.map((b, i) => `<li><b>${'ABCDEFGH'[i]}</b>${esc(b)}</li>`).join('')}</ul>`;
  for (const it of ex.items.filter(i => !hasInline(i))) {
    body += `<div class="q" data-qn="${it.n}">${it.disp || it.n}. ${md(it.q || '')}</div><div class="choices" data-choices="${it.n}">` +
      (it.o ? it.o.map(o => `<label class="opt"><input type="radio" name="it${it.n}" data-n="${it.n}" value="${esc(o)}">${esc(o)}</label>`).join('')
            : `<input class="gap wide" data-n="${it.n}" autocomplete="off">`) + `</div><div class="fbslot" data-fb="${it.n}"></div>`;
  }
  return body;
}

function showExercise() {
  const ex = session.exs[session.ids[session.i]];
  const body = exerciseBody(ex);
  $app.innerHTML = `
    <div class="mute">Ejercicio ${session.i + 1} de ${session.ids.length}</div>
    <div class="card"><h1>${esc(ex.title)}</h1>
      <div><span class="tag">Unit ${ex.unit}</span><span class="tag">${esc(FORMATS[ex.format])}</span><span class="tag">${esc(ex.level)}</span><span class="tag">${esc(ex.linguaskill)}</span></div>
      <p class="mute">${esc(ex.instructions)}</p>${body}
      <div id="inlinefb"></div>
      <div class="row"><button id="check">Corregir</button></div></div>`;
  document.getElementById('check').onclick = () => check(ex);
  const first = $app.querySelector('input.gap, select.gap');
  if (first) first.focus();
  $app.querySelectorAll('input.gap').forEach(inp => inp.addEventListener('keydown', e => {
    if (e.key === 'Enter') { const all = [...$app.querySelectorAll('input.gap')], i = all.indexOf(inp); (all[i + 1] || document.getElementById('check')).focus(); if (i === all.length - 1) document.getElementById('check').click(); }
  }));
}

function collect() {
  const a = {};
  $app.querySelectorAll('input.gap, select.gap').forEach(el => a[el.dataset.n] = el.value);
  $app.querySelectorAll('input[type=radio]:checked').forEach(el => a[el.dataset.n] = el.value);
  return a;
}

const KIND = { forma: 'Forma', tiempo: 'Tiempo', valida: 'Válida, pero…', significado: 'Significado', aviso: 'Ojo con el contexto' };
const whyHtml = r => [
  ...(r.parts || []).map(p => `<div class="why"><span class="pk ${p.kind}">${KIND[p.kind] || 'Por qué'}</span> ${md(p.msg)}</div>`),
  ...(r.irr || []).map(t => `<div class="why"><span class="pk forma">Irregular</span> ${md(t)}</div>`),
  r.sentence ? `<div class="why"><span class="pk ok">Oración completa</span> ${md(r.sentence)}</div>` : '',
].join('');
const disp = (ex, v) => ex.bank && ex.bank.includes(v) ? 'ABCDEFGH'[ex.bank.indexOf(v)] : v;

async function check(ex) {
  const btn = document.getElementById('check');
  btn.disabled = true;
  const res = await api('/api/check', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ exercise_id: ex.id, answers: collect() }) });
  session.ok += res.score; session.total += res.total;
  saveResume(session.i + 1);
  const inlineFb = [];
  for (const r of res.results) {
    const fb = `<div class="fb ${r.correct ? 'ok' : 'bad'}">${r.correct ? '✔' : '✘'} <b>${r.n}.</b> ` +
      (r.alt ? `<b>Correcta, con aviso</b> (esperada: <b>${esc(disp(ex, r.answer))}</b>). ` : '') +
      (r.correct ? '' : `Tu respuesta: <b>${esc(disp(ex, r.given) || '(vacío)')}</b> → correcta: <b>${esc(disp(ex, r.answer))}</b>. `) +
      `${esc(r.explanation)}${r.note && !r.alt ? ' <i>' + esc(r.note) + '</i>' : ''}` + whyHtml(r) +
      (r.correct ? '' : `<br><span class="mute">Regla: ${esc(r.rule_name)}</span>`) + `</div>`;
    const el = $app.querySelector(`[data-n="${r.n}"]`);
    const slot = $app.querySelector(`[data-fb="${r.n}"]`);
    if (slot) {
      slot.innerHTML = fb;
      $app.querySelectorAll(`input[data-n="${r.n}"][type=radio]`).forEach(i => {
        const lab = i.closest('label'); i.disabled = true;
        if (i.value === r.answer) lab.classList.add('ok'); else if (i.checked) lab.classList.add('bad');
      });
      const t = $app.querySelector(`input.gap[data-n="${r.n}"]`); if (t) { t.classList.add(r.correct ? 'ok' : 'bad'); t.disabled = true; }
    } else {
      if (el) { el.classList.add(r.correct ? 'ok' : 'bad'); el.disabled = true; }
      inlineFb.push(fb);
    }
  }
  document.getElementById('inlinefb').innerHTML = inlineFb.join('');
  const last = session.i === session.ids.length - 1;
  btn.parentElement.innerHTML = `<span class="score">${res.score}/${res.total}</span>
    ${last ? (session.q.get('mode') === 'repaso' ? '<a class="btn" href="#/repaso/report">Ver diagnóstico</a>' : '<a class="btn" href="#/progress">Ver progreso</a>') : '<button id="next">Siguiente ejercicio →</button>'}
    ${!last && session.q.get('mode') === 'repaso' ? '<a class="btn secondary" href="#/repaso/report">Diagnóstico</a>' : ''}
    <a class="btn secondary" href="#/">Terminar</a>`;
  const next = document.getElementById('next');
  if (next) { next.onclick = () => { session.i++; showExercise(); window.scrollTo(0, 0); }; next.focus(); }
}

async function progress() {
  const [s, simH, sy] = await Promise.all([api('/api/stats'), api('/api/sim/history'), api('/api/sync/status')]);
  const color = { weak: 'var(--bad)', watch: 'var(--warn)', ok: 'var(--ok)', new: 'var(--line)' };
  const pct = s.total ? Math.round(100 * s.ok / s.total) : 0;
  $app.innerHTML = `
    <div class="card"><h1>Progreso</h1>
      <div class="mute">Respuestas en la app: ${s.total} · aciertos ${pct}%. El score de cada regla pondera más lo reciente (0 = sin errores, 1 = todo error).</div></div>
    <div class="card"><h2>Sincronizar con otro dispositivo (PC ↔ celular)</h2>
      <div class="mute">Exportá tu progreso en un dispositivo y importalo en el otro: se fusionan las respuestas sin duplicar ni borrar nada, y podés repetirlo cuantas veces quieras.</div>
      <div class="row"><a class="btn" href="/api/export" download>Exportar progreso</a>
        <label class="btn secondary" style="cursor:pointer">Importar progreso<input type="file" id="impfile" accept=".json,application/json" hidden></label></div>
      <div id="impres" class="mute" style="margin-top:8px"></div></div>
    <div class="card"><h2>Sincronización automática (carpeta compartida)</h2>
      <div class="mute">Cada dispositivo guarda su progreso en una carpeta y lee el de los demás cada ~45 s. Usá la misma carpeta en la PC y en el celular, compartida con Syncthing (ver README) y un nombre distinto para cada dispositivo.</div>
      <div class="row"><label>Nombre de este dispositivo: <input id="sdev" class="gap wide" placeholder="pc o celu" value="${esc(sy.config.device)}"></label></div>
      <div class="row"><label style="width:100%">Carpeta compartida:<br><input id="sdir" class="gap" style="width:100%;text-align:left" placeholder="C:\Users\...\IPP-sync  o  /storage/emulated/0/IPP-sync" value="${esc(sy.config.dir)}"></label></div>
      <div class="row"><button id="ssave">Guardar y sincronizar</button><button class="secondary" id="snow">Sincronizar ahora</button></div>
      <div id="sstat" class="mute" style="margin-top:8px">${sy.ok ? '✔ ' : ''}${esc(sy.msg)}${sy.last ? ' (' + esc(sy.last) + ')' : ''}</div></div>
    <div class="card"><h2>Reglas gramaticales</h2><table>
      <tr><th>Regla</th><th>Estado</th><th>Score</th><th>Errores / intentos</th><th></th></tr>
      ${s.rules.map(r => `<tr><td>${esc(r.name)}<div class="mute">${esc(r.group)} · ${esc(r.note)}</div></td>
        <td><span class="st ${r.status}">${STATUS[r.status]}</span></td>
        <td><div class="bar"><i style="width:${Math.min(100, r.score * 100 / 0.6 * 1)}%;background:${color[r.status]}"></i></div></td>
        <td>${r.wrong} / ${r.attempts}</td><td><a href="#/run?rule=${r.id}">practicar</a></td></tr>`).join('')}</table></div>
    ${simH.length ? `<div class="card"><h2>Simulacros anteriores</h2><table>
      <tr><th>Fecha</th><th>Alcance</th><th>Puntaje</th><th>Tiempo usado</th></tr>
      ${simH.map(h => `<tr><td>${esc(h.ts.slice(0, 16).replace('T', ' '))}</td><td>${h.unit ? 'Unit ' + esc(h.unit) : 'Todas'}</td>
        <td>${h.score}/${h.total} (${h.total ? Math.round(100 * h.score / h.total) : 0}%)</td><td>${Math.floor(h.elapsed_s / 60)} de ${h.minutes_limit} min</td></tr>`).join('')}</table></div>` : ''}
    <div class="card"><h2>Por formato</h2><table>
      ${s.by_format.map(f => `<tr><td>${esc(FORMATS[f.format])}</td><td>${f.ok}/${f.total}</td><td>${Math.round(100 * f.ok / f.total)}%</td></tr>`).join('') || '<tr><td class="mute">Sin datos todavía.</td></tr>'}</table></div>
    <div class="card"><h2>Últimos errores</h2><table>
      ${s.recent_errors.map(e => `<tr><td>${esc(e.ts.slice(0, 10))}</td><td>${esc(e.given || '(vacío)')}</td><td>${esc(e.rule_name)}</td><td class="mute">${e.source !== 'app' ? esc(e.source) : ''}</td></tr>`).join('')}</table></div>`;
  const showSync = r => { document.getElementById('sstat').textContent = r.error ? '✘ ' + r.error : (r.ok ? '✔ ' : '') + r.msg + (r.last ? ' (' + r.last + ')' : ''); };
  document.getElementById('ssave').onclick = async () => showSync(await api('/api/sync/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ device: document.getElementById('sdev').value, dir: document.getElementById('sdir').value }) }));
  document.getElementById('snow').onclick = async () => { showSync(await api('/api/sync/now', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })); };
  document.getElementById('impfile').onchange = async e => {
    const f = e.target.files[0]; if (!f) return;
    const out = document.getElementById('impres');
    try {
      const r = await api('/api/import', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: await f.text() });
      if (r.error) { out.textContent = '✘ ' + r.error; return; }
      out.textContent = `✔ Importado: ${r.attempts_added} respuestas nuevas (${r.attempts_duplicated} ya estaban), ${r.simulacros_added} simulacros nuevos${r.invalid ? `, ${r.invalid} filas descartadas` : ''}.`;
      setTimeout(progress, 1800);
    } catch (err) { out.textContent = '✘ No se pudo leer el archivo: ' + err.message; }
  };
}

// ---------- simulacro ----------
const fmtTime = sec => { sec = Math.max(0, sec); return String(Math.floor(sec / 60)).padStart(2, '0') + ':' + String(sec % 60).padStart(2, '0'); };

function simSetup() {
  const unit = getUnit();
  $app.innerHTML = `
    <div class="card"><h1>Simulacro Linguaskill Reading</h1>
      <p class="mute">Reproduce las condiciones del examen: una tarea por pantalla, no se puede volver a una pantalla anterior, no hay corrección hasta el final y el tiempo corre.
      Incluye solo formatos de Linguaskill (open cloze, multiple choice cloze, discrete cloze, reading discrete, gapped text, cross-text matching y comprehension).
      <b>No es adaptativo</b> como el real, así que el puntaje sirve para comparar tus simulacros entre sí, no para estimar tu nivel.</p>
      <div class="row"><label>Alcance: <select class="filter" id="simunit">${Object.entries(UNITS).map(([k, v]) => `<option value="${k}" ${k === unit ? 'selected' : ''}>${v}</option>`).join('')}</select></label></div>
      <div class="row"><label>Duración: <select class="filter" id="simmin"><option value="59">59 min (completo)</option><option value="45">45 min</option><option value="30">30 min</option></select></label></div>
      <div class="row"><label><input type="checkbox" id="simweak"> Priorizar ejercicios de mis reglas débiles</label></div>
      <div class="row"><button id="simgo">Empezar simulacro</button><a class="btn secondary" href="#/">Volver</a></div>
      <p class="mute">Ojo: si recargás la página durante el simulacro, se pierde.</p></div>`;
  document.getElementById('simgo').onclick = async () => {
    const btn = document.getElementById('simgo'); btn.disabled = true;
    const body = { unit: document.getElementById('simunit').value, minutes: +document.getElementById('simmin').value, weak: document.getElementById('simweak').checked };
    const r = await api('/api/sim/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (r.error) { alert(r.error); btn.disabled = false; return; }
    sim = { ...r, i: 0, answers: [], startedAt: Date.now(), deadline: Date.now() + r.minutes * 60000, timer: null, done: false };
    location.hash = '#/sim/run';
  };
}

function simShow() {
  const t = sim.tasks[sim.i];
  const last = sim.i === sim.tasks.length - 1;
  $app.innerHTML = `
    <div class="card"><h1>${esc(t.title)}</h1>
      <div><span class="tag">${esc(FORMATS[t.format])}</span></div>
      <p class="mute">${esc(t.instructions)}</p>${exerciseBody(t)}
      <div class="row"><button id="simnext">${last ? 'Terminar simulacro' : 'Siguiente →'}</button></div></div>
    <div class="simbar"><span id="simtask">Tarea ${sim.i + 1} de ${sim.tasks.length}</span>
      <div class="bar" style="flex:1"><i style="width:${Math.round(100 * sim.i / sim.tasks.length)}%;background:var(--accent)"></i></div>
      <b id="simclock">--:--</b><button class="secondary" id="simquit">Terminar ahora</button></div>`;
  window.scrollTo(0, 0);
  document.getElementById('simnext').onclick = () => simAdvance();
  document.getElementById('simquit').onclick = () => { if (confirm('¿Terminar el simulacro ahora? Lo que no respondiste cuenta como incorrecto.')) simFinish(); };
  if (!sim.timer) sim.timer = setInterval(simTick, 500);
  simTick();
}

function simTick() {
  if (!sim || sim.done) return;
  const left = Math.round((sim.deadline - Date.now()) / 1000);
  const c = document.getElementById('simclock');
  if (c) { c.textContent = fmtTime(left); c.style.color = left <= 300 ? 'var(--bad)' : 'inherit'; }
  if (left <= 0) simFinish(true);
}

function simSaveCurrent() {
  if (document.getElementById('simnext')) sim.answers[sim.i] = collect();
}

function simAdvance() {
  simSaveCurrent();
  if (sim.i >= sim.tasks.length - 1) return simFinish();
  sim.i++;
  simShow();
}

async function simFinish(timeUp) {
  if (sim.done) return;
  sim.done = true;
  clearInterval(sim.timer); sim.timer = null;
  simSaveCurrent();
  const elapsed = Math.min(sim.minutes * 60, Math.round((Date.now() - sim.startedAt) / 1000));
  const payload = { unit: sim.unit, minutes: sim.minutes, elapsed,
    tasks: sim.tasks.map((t, i) => ({ exercise_id: t.id, ns: t.ns, answers: sim.answers[i] || {} })) };
  $app.innerHTML = '<div class="card">Corrigiendo…</div>';
  const r = await api('/api/sim/finish', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  simResults(r, elapsed, !!timeUp);
  sim = null;
}

function simResults(r, elapsed, timeUp) {
  const pct = r.total ? Math.round(100 * r.score / r.total) : 0;
  const show = (t, v) => t.bank && t.bank.includes(v) ? 'ABCDEFGH'[t.bank.indexOf(v)] : v;
  const wrongs = r.tasks.map(t => ({ t, w: t.results.filter(x => !x.correct) })).filter(x => x.w.length);
  $app.innerHTML = `
    <div class="card"><h1>Resultado del simulacro</h1>
      <div class="score">${r.score}/${r.total} · ${pct}%</div>
      <div class="mute">${timeUp ? 'Se acabó el tiempo. ' : ''}Usaste ${fmtTime(elapsed)}. Las preguntas sin responder cuentan como incorrectas pero no se cargan a tus reglas débiles.
      Como el examen real es adaptativo, comparalo con tus otros simulacros, no lo tomes como nivel Cambridge.</div></div>
    <div class="card"><h2>Por formato</h2><table>
      ${r.by_format.map(f => `<tr><td>${esc(FORMATS[f.format])}</td><td>${f.ok}/${f.total}</td><td>${Math.round(100 * f.ok / f.total)}%</td></tr>`).join('')}</table></div>
    <div class="card"><h2>Reglas donde más fallaste</h2>
      ${r.top_rules.length ? r.top_rules.map(x => `<div class="row" style="margin:6px 0"><span style="flex:1">${esc(x.rule_name)}</span><span class="mute">${x.errors} error${x.errors > 1 ? 'es' : ''}</span><a href="#/run?rule=${x.rule}">practicar →</a></div>`).join('') : '<div class="mute">Sin errores.</div>'}</div>
    <div class="card"><h2>Revisión de errores</h2>
      ${wrongs.length ? wrongs.map(({ t, w }) => `<details style="margin:8px 0"><summary><b>${esc(t.title)}</b> <span class="mute">· ${esc(FORMATS[t.format])} · ${w.length} error${w.length > 1 ? 'es' : ''}</span></summary>
        ${w.map(x => `<div class="fb bad">✘ <b>${x.n}.</b> Tu respuesta: <b>${esc(show(t, x.given) || '(vacío)')}</b> → correcta: <b>${esc(show(t, x.answer))}</b>. ${esc(x.explanation)}${whyHtml(x)}<br><span class="mute">Regla: ${esc(x.rule_name)}</span></div>`).join('')}</details>`).join('') : '<div class="mute">No hay errores para revisar.</div>'}</div>
    <div class="row"><a class="btn" href="#/sim">Otro simulacro</a><a class="btn secondary" href="#/">Inicio</a></div>`;
}
