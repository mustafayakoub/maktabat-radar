/* رادار المكتبات — منطقُ الصفحة.
   مبدأٌ حاكم: لا يُعرَضُ رقمٌ بلا مصدرِه. فصفوفُ البحثِ موسومةٌ «من فهرس Everything»،
   وصفوفُ «وصل إلينا» موسومةٌ بشهادةِ سجلِّ الرادار، ولا يُخلَطُ المقياسان في عمودٍ واحد. */
(() => {
  'use strict';

  const $ = (s) => document.querySelector(s);
  const el = (tag, cls, txt) => { const n = document.createElement(tag); if (cls) n.className = cls; if (txt != null) n.textContent = txt; return n; };

  // ── أرقامٌ هنديّةٌ ومقادير ───────────────────────────────────────────────
  const AR = ['٠','١','٢','٣','٤','٥','٦','٧','٨','٩'];
  const arDigits = (s) => String(s).replace(/[0-9]/g, (d) => AR[+d]);
  const num = (n, dec = 0) => (n == null ? '—' : arDigits(Number(n).toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec })).replace(/,/g, '٬').replace(/\./g, '٫'));
  const size = (b) => {
    if (b == null) return '—';
    const u = [[1e12, 'ت.ب'], [1e9, 'ج.ب'], [1e6, 'م.ب'], [1e3, 'ك.ب']];
    for (const [s, label] of u) if (b >= s) return num(b / s, b < s * 100 ? 1 : 0) + ' ' + label;
    return num(b) + ' بايت';
  };
  const ago = (ts) => {
    if (!ts) return '—';
    const s = Math.max(0, Date.now() / 1000 - ts);
    if (s < 60) return 'الآن';
    const steps = [[60, 'دقيقة', 'دقيقتين', 'دقائق'], [3600, 'ساعة', 'ساعتين', 'ساعات'], [86400, 'يوم', 'يومين', 'أيّام'], [86400 * 30, 'شهر', 'شهرين', 'أشهر'], [86400 * 365, 'سنة', 'سنتين', 'سنوات']];
    let pick = steps[0];
    for (const st of steps) if (s >= st[0]) pick = st;
    const n = Math.floor(s / pick[0]);
    if (n === 1) return 'قبل ' + pick[1];
    if (n === 2) return 'قبل ' + pick[2];
    return 'قبل ' + num(n) + ' ' + (n <= 10 ? pick[3] : pick[1]);
  };
  const stampNode = (ts, tag = 'span') => {
    const n = document.createElement(tag);
    n.className = 'mr-stamp';
    n.setAttribute('dir', 'ltr');
    n.textContent = stamp(ts);
    return n;
  };
  const stamp = (ts) => {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    const p = (x) => String(x).padStart(2, '0');
    return arDigits(`${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`);
  };

  // ── الحالة ──────────────────────────────────────────────────────────────
  const S = {
    mode: 'new',           // 'new' أو 'search'
    measure: 'arrival',    // 'arrival' شهادةُ الرادار · 'mtime' ختمُ المِلفّ
    window: 'day',
    list: 'arrivals',
    q: '', tolerant: true,
    store: '', root: '', shelf: '', kind: '', ext: '', sort: 'modified',
    offset: 0, rows: [], total: 0,
    state: null,
  };
  const WINDOW_KEYS = [['hour', 'ساعة'], ['day', '٢٤ ساعة'], ['3days', '٣ أيّام'], ['week', 'أسبوع'], ['month', 'شهر'], ['quarter', '٣ أشهر'], ['year', 'سنة'], ['all', 'الكلّ']];

  const remember = () => { try { localStorage.setItem('mr', JSON.stringify({ list: S.list, measure: S.measure, window: S.window, store: S.store, root: S.root, kind: S.kind, ext: S.ext, sort: S.sort, tolerant: S.tolerant })); } catch (e) { /* لا يُعتمَدُ على مخزنِ المتصفّح */ } };
  const recall = () => { try { Object.assign(S, JSON.parse(localStorage.getItem('mr') || '{}')); } catch (e) { /* يُقرأُ فارغًا في نافذةٍ خاصّة */ } };

  const api = async (path, opts) => {
    const res = await fetch(path, opts);
    const body = await res.json().catch(() => ({ error: 'ردٌّ غيرُ مفهوم' }));
    if (!res.ok) throw new Error(body.error || ('خطأ ' + res.status));
    return body;
  };

  // ── الرأسُ والحالة ──────────────────────────────────────────────────────
  function paintChips(st) {
    const c = $('#chips');
    c.textContent = '';
    const add = (html, cls) => { const n = el('span', 'mr-chip' + (cls ? ' ' + cls : '')); n.innerHTML = html; c.appendChild(n); };
    add(st.alive ? 'Everything <b>حيّ</b>' : 'Everything <b>متوقّف</b>', st.alive ? 'good' : 'bad');
    if (st.live && st.live.scope != null) add(`في النطاق <b>${num(st.live.scope)}</b> مِلفًّا`);
    if (st.totals) add(`المسجَّل <b>${num(st.totals.files)}</b> — ${size(st.totals.bytes)}`);
    if (st.scan) add(`آخرُ مسحٍ <b>${ago(st.scan.finished)}</b>`);
    if (st.db) add(`السجلّ <b>${size(st.db.bytes)}</b>`);
  }

  function paintWindows(st) {
    const box = $('#windows');
    box.textContent = '';
    const counts = {};
    (st.buckets || []).forEach((b) => { counts[b.secs] = b; });
    const secsOf = { hour: 3600, day: 86400, '3days': 259200, week: 604800, month: 2592000, quarter: 7776000, year: 31536000 };
    WINDOW_KEYS.forEach(([key, label]) => {
      const btn = el('button', 'mr-win' + (S.window === key && S.mode === 'new' ? ' on' : ''));
      btn.type = 'button';
      const b = counts[secsOf[key]];
      btn.appendChild(el('b', null, S.measure === 'arrival' && b ? num(b.count) : (key === 'all' ? '∞' : '—')));
      btn.appendChild(el('span', null, label));
      btn.addEventListener('click', () => { S.window = key; S.mode = 'new'; S.offset = 0; remember(); paintWindows(S.state); load(); });
      box.appendChild(btn);
    });
    // ختمُ المِلفِّ لا يعرفُ المفقودَ ولا الواصل — فلا تُعرَضُ قوائمُه مع هذا المقياس
    $('#lists').hidden = S.measure !== 'arrival';
    $('#measure-note').textContent = S.measure === 'arrival'
      ? 'بشهادةِ الرادار: ما لم يكن في المسحِ السابقِ وصارَ في هذا — فهو الواصلُ حقًّا وإنْ كان ختمُه قديمًا.'
      : 'ختمُ المِلفِّ نفسِه من فهرس Everything — كتابٌ نسختَه اليومَ يحملُ تاريخَ منبعه فلا يظهرُ هنا.';
    const since = st.watching_since;
    const foot = $('#foot-since');
    foot.textContent = '';
    if (since) {
      foot.appendChild(document.createTextNode(' والرصدُ قائمٌ منذ '));
      foot.appendChild(stampNode(since));
      foot.appendChild(document.createTextNode(` (${ago(since)}).`));
    }
  }

  function fillSelect(sel, items, value) {
    const first = sel.options[0];
    sel.textContent = '';
    sel.appendChild(first);
    items.forEach(({ v, t }) => {
      const o = el('option', null, t);
      o.value = v;
      sel.appendChild(o);
    });
    sel.value = value || '';
  }

  function paintFilters(st) {
    const stores = (st.totals && st.totals.stores) || [];
    fillSelect($('#f-store'), stores.map((s) => ({ v: s.store, t: (s.store === 'nas' ? 'السيرفر' : 'الهارد') + ' — ' + num(s.n) })), S.store);
    fillSelect($('#f-root'), (st.roots || []).map((r) => ({ v: r.id, t: r.label })), S.root);
    fillSelect($('#f-kind'), ((st.totals && st.totals.kinds) || []).map((k) => ({ v: k.kind, t: k.kind + ' — ' + num(k.n) })), S.kind);
    fillSelect($('#f-ext'), (st.exts || []).map((e) => ({ v: e, t: e })), S.ext);
    $('#f-sort').value = S.sort;
    $('#tolerant').checked = !!S.tolerant;
  }

  function paintPanels(st) {
    const t = st.totals;
    const bars = (host, items, max) => {
      host.textContent = '';
      if (!items.length) { host.appendChild(el('p', 'mr-note', 'لا سجلَّ بعد — امسحْ أوّلًا.')); return; }
      items.forEach((it) => {
        const row = el('div', 'mr-bar' + (it.onClick ? ' clickable' : ''));
        row.appendChild(el('div', 'mr-lbl', it.label));
        row.appendChild(el('div', 'mr-val', it.value));
        const track = el('div', 'mr-track');
        const fill = el('div', 'mr-fill');
        fill.style.width = Math.max(1, Math.round((it.weight / max) * 100)) + '%';
        track.appendChild(fill);
        row.appendChild(track);
        if (it.onClick) row.addEventListener('click', it.onClick);
        host.appendChild(row);
      });
    };
    if (!t) { bars($('#p-stores'), [], 1); bars($('#p-kinds'), [], 1); bars($('#p-shelves'), [], 1); return; }
    const maxS = Math.max(1, ...t.stores.map((s) => s.n));
    bars($('#p-stores'), t.stores.map((s) => ({
      label: s.store === 'nas' ? 'السيرفر' : 'الهارد المحلّيّ',
      value: num(s.n) + ' — ' + size(s.bytes), weight: s.n,
      onClick: () => { S.store = s.store; $('#f-store').value = s.store; S.offset = 0; load(); },
    })), maxS);
    const maxK = Math.max(1, ...t.kinds.map((k) => k.n));
    bars($('#p-kinds'), t.kinds.map((k) => ({
      label: k.kind, value: num(k.n) + ' — ' + size(k.bytes), weight: k.n,
      onClick: () => { S.kind = k.kind; $('#f-kind').value = k.kind; S.offset = 0; load(); },
    })), maxK);
  }

  async function paintShelves() {
    try {
      const d = await api('/api/shelves?limit=24');
      const rows = d.rows || [];
      const max = Math.max(1, ...rows.map((r) => r.n));
      const host = $('#p-shelves');
      host.textContent = '';
      if (!rows.length) { host.appendChild(el('p', 'mr-note', 'لا سجلَّ بعد.')); return; }
      rows.forEach((r) => {
        const row = el('div', 'mr-bar clickable');
        row.appendChild(el('div', 'mr-lbl', r.shelf + (r.store === 'nas' ? ' — السيرفر' : ' — الهارد')));
        row.appendChild(el('div', 'mr-val', num(r.n) + ' — ' + size(r.bytes) + (r.arrived ? ' — جديدٌ ' + num(r.arrived) : '')));
        const track = el('div', 'mr-track'); const fill = el('div', 'mr-fill');
        fill.style.width = Math.max(1, Math.round((r.n / max) * 100)) + '%';
        track.appendChild(fill); row.appendChild(track);
        row.addEventListener('click', () => { S.shelf = r.shelf; S.offset = 0; syncShelf(); load(); });
        host.appendChild(row);
      });
    } catch (e) { /* الرفوفُ زينةٌ لا شرطٌ للعمل */ }
  }

  function syncShelf() {
    const sel = $('#f-shelf');
    if (S.shelf && ![...sel.options].some((o) => o.value === S.shelf)) {
      const o = el('option', null, S.shelf); o.value = S.shelf; sel.appendChild(o);
    }
    sel.value = S.shelf || '';
  }

  // ── الصفوف ──────────────────────────────────────────────────────────────
  function rowNode(r) {
    const gone = !!r.gone_at;
    const fresh = !gone && r.first_seen && !r.is_baseline;
    const node = el('div', 'mr-row' + (fresh ? ' fresh' : '') + (gone ? ' gone' : ''));
    const name = el('div', 'mr-name');
    name.appendChild(el('b', null, r.name || r.path));
    const meta = el('div', 'mr-meta');
    if (r.kind) meta.appendChild(el('i', null, r.kind));
    if (r.ext) meta.appendChild(el('i', null, r.ext));
    if (r.shelf) meta.appendChild(el('span', null, r.shelf));
    meta.appendChild(el('span', null, r.store === 'nas' ? 'السيرفر' : 'الهارد'));
    meta.appendChild(el('span', 'mr-path', r.dir || (r.path || '').replace(/\\[^\\]*$/, '')));
    name.appendChild(meta);
    node.appendChild(name);

    node.appendChild(el('div', 'mr-num', size(r.size)));

    const when = el('div', 'mr-when');
    if (gone) {
      when.appendChild(el('b', null, 'اختفى ' + ago(r.gone_at)));
      const line = el('div', null, 'كان تعديلُه ');
      line.appendChild(stampNode(r.mtime));
      when.appendChild(line);
    } else if (fresh) {
      // كلُّ تاريخٍ يُعلنُ مصدرَه: فرقُ لقطتين أم تاريخُ إنشاءِ المِلفِّ على القرص
      const byDisk = r.first_seen_src === 'ctime';
      const b = el('b', null, (byDisk ? 'أُنشئ على القرص ' : 'وصل ') + ago(r.first_seen));
      if (byDisk) b.title = 'تاريخُ إنشاءِ المِلفِّ على القرص — وهو تاريخُ وصولِه إليك';
      when.appendChild(b);
      const line = el('div', null, 'تعديلُه ');
      line.appendChild(stampNode(r.mtime));
      when.appendChild(line);
    } else {
      when.appendChild(stampNode(r.mtime, 'b'));
      when.appendChild(el('div', null, r.is_baseline ? 'في المكتبةِ قبلَ الرصد' : 'لا سجلَّ وصولٍ له'));
    }
    node.appendChild(when);

    const acts = el('div', 'mr-acts');
    const mk = (label, title, mode) => {
      const b = el('button', null, label);
      b.type = 'button'; b.title = title;
      b.addEventListener('click', async () => {
        b.disabled = true;
        try {
          const out = await api('/api/open', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: r.path, mode }) });
          if (!out.ok) alert(out.error || 'تعذّر الفتح');
        } catch (e) { alert(e.message); } finally { b.disabled = false; }
      });
      return b;
    };
    if (!gone) {
      acts.appendChild(mk('📂', 'فتحُ المجلّد وتحديدُ المِلفّ', 'folder'));
      acts.appendChild(mk('📄', 'فتحُ المِلفّ', 'file'));
    }
    const copy = el('button', null, '⧉');
    copy.type = 'button'; copy.title = 'نسخُ المسار';
    copy.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(r.path); copy.textContent = '✓'; setTimeout(() => { copy.textContent = '⧉'; }, 1200); } catch (e) { alert('تعذّر النسخ'); }
    });
    acts.appendChild(copy);
    node.appendChild(acts);
    return node;
  }

  function paintRows(append) {
    const host = $('#rows');
    if (!append) host.textContent = '';
    if (!S.rows.length && !append) {
      const box = el('div', 'mr-empty');
      box.appendChild(el('p', null, S.emptyMsg || 'لا نتيجة.'));
      if (S.mode === 'new' && S.measure === 'arrival' && S.list === 'arrivals') {
        const b = el('button', 'mr-ghost', 'اعرضْ بتاريخِ التعديلِ بدلًا منه');
        b.type = 'button';
        b.addEventListener('click', () => {
          document.querySelectorAll('.mr-measure button').forEach((x) => x.classList.toggle('on', x.dataset.measure === 'mtime'));
          S.measure = 'mtime'; remember(); paintWindows(S.state || {}); load();
        });
        box.appendChild(b);
      }
      host.appendChild(box);
    }
    S.rows.slice(append ? S.painted : 0).forEach((r) => host.appendChild(rowNode(r)));
    S.painted = S.rows.length;
    $('#more').hidden = S.rows.length >= S.total || S.rows.length === 0;
  }

  // ── التحميل ─────────────────────────────────────────────────────────────
  let seq = 0;
  async function load(append = false) {
    const mine = ++seq;
    const res = $('#results');
    res.setAttribute('aria-busy', 'true');
    if (!append) { S.offset = 0; S.painted = 0; }
    const qs = new URLSearchParams();
    const put = (k, v) => { if (v) qs.set(k, v); };
    put('q', S.q); put('store', S.store); put('root', S.root); put('shelf', S.shelf);
    put('kind', S.kind); put('ext', S.ext); put('sort', S.sort);
    qs.set('limit', '120'); qs.set('offset', String(S.offset));

    let path;
    const ledger = S.mode === 'new' && S.measure === 'arrival';
    if (ledger) {
      qs.set('window', S.window); qs.set('list', S.list);
      path = '/api/recent?' + qs;
    } else {
      qs.set('tolerant', S.tolerant ? '1' : '0');
      if (S.mode === 'new') { qs.set('window', S.window); qs.set('measure', 'mtime'); }
      path = '/api/search?' + qs;
    }
    try {
      const d = await api(path);
      if (mine !== seq) return;
      S.total = d.total || 0;
      S.rows = append ? S.rows.concat(d.rows || []) : (d.rows || []);
      const blanks = {
        arrivals: 'لم يصلْ شيءٌ في هذه المدّة بشهادةِ الرادار. وربّما وصلَ قبلَ أوّلِ مسحٍ فهو في الخطِّ الأساس.',
        changed: 'لم يتغيّرْ حجمُ ملفٍّ ولا تاريخُه في هذه المدّة.',
        gone: 'لم يختفِ شيءٌ في هذه المدّة — وهذا خبرٌ طيّب.',
      };
      S.emptyMsg = d.empty || (ledger ? blanks[S.list] : 'لا نتيجةَ في فهرس Everything بهذه القيود.');
      paintRows(append);
      const titles = { arrivals: 'ما وصلَ إلينا', changed: 'ما تغيّرَ عندنا', gone: 'ما اختفى من المكتبة' };
      $('#results-title').textContent = S.mode === 'search' ? 'نتائجُ البحث'
        : (S.measure === 'arrival' ? titles[S.list] : 'ما عُدِّلَ حديثًا');
      const src = ledger ? 'سجلِّ الرادار' : 'فهرس Everything';
      $('#results-count').textContent = `${num(S.total)} نتيجة — من ${src}` + (d.took ? ` في ${num(d.took, 2)} ثانية` : '');
      if (!ledger && d.took != null) $('#seek-stat').textContent = S.q ? `${num(S.total)} نتيجة في ${num(d.took, 2)} ثانية` : '';
      const ex = new URLSearchParams(qs); ex.set('src', ledger ? 'ledger' : 'live');
      $('#csv').href = '/api/export.csv?' + ex;
    } catch (e) {
      if (mine !== seq) return;
      $('#rows').textContent = '';
      $('#rows').appendChild(el('div', 'mr-empty', '⛔ ' + e.message));
      $('#results-count').textContent = '';
    } finally {
      res.setAttribute('aria-busy', 'false');
    }
  }

  async function refreshState() {
    try {
      S.state = await api('/api/state');
      paintChips(S.state); paintWindows(S.state); paintFilters(S.state); paintPanels(S.state);
      syncShelf();
      paintShelves();
    } catch (e) {
      $('#chips').textContent = '';
      const bad = el('span', 'mr-chip bad'); bad.textContent = 'تعذّر الاتّصالُ بالخادم';
      $('#chips').appendChild(bad);
    }
  }

  // ── الأحداث ─────────────────────────────────────────────────────────────
  let timer = null;
  $('#q').addEventListener('input', (e) => {
    S.q = e.target.value.trim();
    clearTimeout(timer);
    // بوّابةُ الحرفين: حرفٌ واحدٌ يجلبُ مئاتَ الآلافِ بلا فائدة
    if (S.q.length === 1) return;
    timer = setTimeout(() => {
      S.mode = S.q ? 'search' : 'new';
      paintWindows(S.state || {});
      load();
    }, 280);
  });
  $('#clear').addEventListener('click', () => { $('#q').value = ''; S.q = ''; S.mode = 'new'; paintWindows(S.state || {}); load(); $('#q').focus(); });
  $('#tolerant').addEventListener('change', (e) => { S.tolerant = e.target.checked; remember(); if (S.q) load(); });
  document.querySelectorAll('.mr-lists button').forEach((b) => b.addEventListener('click', () => {
    document.querySelectorAll('.mr-lists button').forEach((x) => x.classList.toggle('on', x === b));
    S.list = b.dataset.list; S.mode = 'new'; S.offset = 0; remember(); load();
  }));
  document.querySelectorAll('.mr-measure button').forEach((b) => b.addEventListener('click', () => {
    document.querySelectorAll('.mr-measure button').forEach((x) => x.classList.toggle('on', x === b));
    S.measure = b.dataset.measure; S.mode = 'new'; remember(); paintWindows(S.state || {}); load();
  }));
  [['#f-store', 'store'], ['#f-root', 'root'], ['#f-shelf', 'shelf'], ['#f-kind', 'kind'], ['#f-ext', 'ext'], ['#f-sort', 'sort']]
    .forEach(([sel, key]) => $(sel).addEventListener('change', (e) => { S[key] = e.target.value; remember(); load(); }));
  $('#reset').addEventListener('click', () => {
    Object.assign(S, { store: '', root: '', shelf: '', kind: '', ext: '', sort: 'modified' });
    remember(); paintFilters(S.state || {}); syncShelf(); load();
  });
  $('#more').addEventListener('click', () => { S.offset = S.rows.length; load(true); });
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && document.activeElement !== $('#q')) { e.preventDefault(); $('#q').focus(); }
    if (e.key === 'Escape' && document.activeElement === $('#q')) { $('#clear').click(); }
  });

  // المسح
  $('#scan').addEventListener('click', async () => {
    const btn = $('#scan');
    btn.disabled = true;
    $('#scan-log').hidden = false;
    try {
      const out = await api('/api/scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      if (!out.ok) { $('#scan-note').textContent = out.error; btn.disabled = false; return; }
      pollScan();
    } catch (e) { $('#scan-note').textContent = e.message; btn.disabled = false; }
  });

  async function pollScan() {
    try {
      const st = await api('/api/scan/status');
      $('#scan-log').textContent = (st.lines || []).join('\n');
      $('#scan-log').scrollTop = $('#scan-log').scrollHeight;
      if (st.running) { setTimeout(pollScan, 900); return; }
      $('#scan').disabled = false;
      const r = st.result || {};
      $('#scan-note').textContent = r.error ? '⛔ ' + r.error
        : `انتهى في ${num(r.secs, 1)} ثانية — رُئي ${num(r.seen)}، واصلٌ جديد ${num(r.added)}، متغيّر ${num(r.changed)}، مفقود ${num(r.gone)}` + (r.skipped && r.skipped.length ? ` — لم يُمسَح (غيرُ موصول): ${r.skipped.join('، ')}` : '');
      await refreshState();
      load();
    } catch (e) { $('#scan').disabled = false; $('#scan-note').textContent = e.message; }
  }

  // ── الجدولة ─────────────────────────────────────────────────────────────
  /** «كلَّ ساعة» لا «كلَّ ١ ساعة»، و«كلَّ ساعتين» لا «كلَّ ٢ ساعة». */
  function arabicEvery(minutes) {
    const pick = (n, one, two, many) => (n === 1 ? one : n === 2 ? two : num(n) + ' ' + (n <= 10 ? many : one));
    if (minutes % 1440 === 0) return pick(minutes / 1440, 'يوم', 'يومين', 'أيّام');
    if (minutes % 60 === 0) return pick(minutes / 60, 'ساعة', 'ساعتين', 'ساعات');
    return pick(minutes, 'دقيقة', 'دقيقتين', 'دقائق');
  }

  function schedText(st) {
    if (st.error) return '⛔ تعذّر قراءةُ حالةِ المهمّة — ' + st.error;
    if (!st.exists) return 'لا مسحَ آليًّا الآن. والنوافذُ الزمنيّةُ لا تمتلئُ إلّا بمسحٍ دوريّ — فعّلْه.';
    const bits = [];
    if (st.minutes) bits.push('كلَّ ' + arabicEvery(st.minutes));
    if (st.last) bits.push('آخرُ تشغيلٍ ' + ago(new Date(st.last).getTime() / 1000));
    if (st.next) bits.push('التالي ' + stamp(new Date(st.next).getTime() / 1000));
    if (st.result !== 0 && st.result != null) bits.push('آخرُ نتيجةٍ ' + num(st.result));
    return '⏱ مفعَّلٌ — ' + bits.join(' — ');
  }

  async function refreshSchedule() {
    try {
      const st = await api('/api/schedule');
      $('#sched-note').textContent = schedText(st);
      if (st.exists && st.minutes) {
        const unit = st.minutes % 1440 === 0 ? 1440 : (st.minutes % 60 === 0 ? 60 : 1);
        $('#unit').value = String(unit);
        $('#every').value = String(st.minutes / unit);
      }
    } catch (e) { $('#sched-note').textContent = e.message; }
  }

  $('#sched-on').addEventListener('click', async () => {
    const minutes = Math.round(Number($('#every').value || 60) * Number($('#unit').value || 60));
    $('#sched-note').textContent = 'جارٍ التثبيت…';
    try {
      const out = await api('/api/schedule', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ minutes }) });
      $('#sched-note').textContent = out.ok ? '✓ ' + (out.message || 'سُجّلت المهمّة') : '⛔ ' + (out.message || 'تعذّر التثبيت');
      setTimeout(refreshSchedule, 1200);
    } catch (e) { $('#sched-note').textContent = '⛔ ' + e.message; }
  });

  $('#sched-off').addEventListener('click', async () => {
    $('#sched-note').textContent = 'جارٍ الإلغاء…';
    try {
      const out = await api('/api/schedule', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ remove: true }) });
      $('#sched-note').textContent = out.ok ? '✓ ' + (out.message || 'أُلغيت') : '⛔ ' + (out.message || 'تعذّر الإلغاء');
      setTimeout(refreshSchedule, 1000);
    } catch (e) { $('#sched-note').textContent = '⛔ ' + e.message; }
  });

  // ── مفتاحُ الصفحةِ الخاصّةِ ورفعُ اللقطة ─────────────────────────────────
  async function refreshKey() {
    try {
      const st = await api('/api/key');
      $('#key-note').textContent = st.exists
        ? '✓ المفتاحُ محفوظٌ على جهازك — والمسحُ الدوريُّ يرفعُ اللقطةَ وحدَه.'
        : (st.can_publish
          ? 'لم يُكتَبِ المفتاحُ بعد. اكتبْه هنا مرّةً واحدةً — يُحفَظُ على جهازك ويُضبَطُ على الموقعِ معًا.'
          : 'لم يُكتَبِ المفتاحُ بعد. اكتبْه هنا، واضبطِ المثلَ على الموقعِ بنفسك.');
    } catch (e) { $('#key-note').textContent = e.message; }
  }

  $('#key-save').addEventListener('click', async () => {
    const box = $('#skey');
    const key = box.value;
    box.value = '';            // لا يبقى المفتاحُ في الحقلِ بعد الحفظ
    $('#key-note').textContent = 'جارٍ الحفظ…';
    try {
      const out = await api('/api/key', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key }) });
      if (!out.ok) {
        $('#key-note').textContent = '⛔ ' + (out.error || 'تعذّر الحفظ');
      } else if (out.cleared) {
        $('#key-note').textContent = '✓ مُحي المفتاحُ من جهازك (ويبقى على الموقعِ حتّى تحذفَه هناك).';
      } else {
        const r = out.remote;
        $('#key-note').textContent = '✓ حُفِظ على جهازك' + (r ? (r.ok ? ' وضُبط على الموقع — صفحةُ /maktabat صارت تعمل.' : ' — لكنْ تعذّر ضبطُه على الموقع: ' + (r.error || r.message)) : '.');
      }
      setTimeout(refreshKey, 900);
    } catch (e) { $('#key-note').textContent = '⛔ ' + e.message; }
  });

  $('#snap-now').addEventListener('click', async () => {
    const btn = $('#snap-now');
    btn.disabled = true;
    $('#key-note').textContent = 'جارٍ بناءُ اللقطةِ ورفعُها…';
    try {
      const out = await api('/api/snapshot', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      $('#key-note').textContent = out.ok
        ? `✓ رُفعت — ${num(out.arrivals)} واصلًا و${num(out.gone)} مفقودًا (${num((out.sent && out.sent.bytes) || 0)} بايت). افتحْ radar.basaere.com/maktabat`
        : '⛔ ' + out.error;
    } catch (e) { $('#key-note').textContent = '⛔ ' + e.message; } finally { btn.disabled = false; }
  });

  // ── الإقلاع ─────────────────────────────────────────────────────────────
  recall();
  document.querySelectorAll('.mr-measure button').forEach((b) => b.classList.toggle('on', b.dataset.measure === S.measure));
  document.querySelectorAll('.mr-lists button').forEach((b) => b.classList.toggle('on', b.dataset.list === S.list));
  refreshSchedule();
  refreshKey();
  refreshState().then(() => {
    load();
    api('/api/scan/status').then((st) => { if (st.running) { $('#scan').disabled = true; $('#scan-log').hidden = false; pollScan(); } });
  });
  setInterval(() => { if (!document.hidden) refreshState(); }, 60000);
})();
