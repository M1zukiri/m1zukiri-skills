/* 创建时间: 2026-10-22 15:10:00
 * 课件批注工作台前端（通用版，由 courseware-annotator skill 分发）
 *
 * 结构：
 *   1. 基础工具            2. 全局状态            3. 启动与章节目录
 *   4. 页面渲染与滚动       5. 批注状态同步         6. 批注交互（选中/框选/浮层）
 *   7. 右侧批注面板         8. 搜索                9. 复制提问 / 导出笔记
 *  10. 快捷键
 *
 * 项目名、副标题从 /data/manifest.json 的 project 字段读取。
 */
'use strict';

(() => {
  /* ================= 1. 基础工具 ================= */
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  };
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const debounce = (fn, ms) => {
    let timer = 0;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
  };
  const uid = () => 'a-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 7);
  const TAGS = ['不懂', '前置', '推导', '符号', '补充'];

  async function fetchJSON(url, opts) {
    const res = await fetch(url, opts);
    if (!res.ok) throw new Error(`${res.status} ${url}`);
    return res.json();
  }
  const postJSON = (url, body) => fetchJSON(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  function fmtTime(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    const p = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  let toastTimer = 0;
  function toast(msg, ms = 2400) {
    const node = $('#toast');
    if (!node) return;
    node.textContent = msg;
    node.classList.remove('hidden');
    requestAnimationFrame(() => node.classList.add('show'));
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      node.classList.remove('show');
      setTimeout(() => node.classList.add('hidden'), 250);
    }, ms);
  }

  /* ================= 2. 全局状态 ================= */
  const S = {
    manifest: null,
    chapters: new Map(),
    current: null,
    annotations: [],
    answers: {},
    lastAnnRev: -1,
    lastAnsKey: '',
    annotMode: false,
    filter: localStorage.getItem('study.filter') || 'all',
    scopeCurrent: localStorage.getItem('study.scope') === '1',
    selectedId: null,
    currentPage: 1,
    pending: null,
    region: null,
    regionJustFinished: false,
    zoomPct: Number(localStorage.getItem('study.zoom')) || 90,
    drafts: new Map(),
    pollTimer: 0,
    root: '',
  };

  /* ================= 3. 启动与章节 ================= */
  async function boot() {
    try {
      S.manifest = await fetchJSON('/data/manifest.json');
      applyProjectMeta();
      renderChapterTabs();
      bindTopbar();
      bindReader();
      bindKeyboard();
      const params = new URLSearchParams(location.search);
      const start = params.get('ch') || localStorage.getItem('study.chapter') || S.manifest.chapters[0].id;
      const chapterId = S.manifest.chapters.some((c) => c.id === start) ? start : S.manifest.chapters[0].id;
      await switchChapter(chapterId, { page: Number(params.get('page')) || 0 });
      applyZoom();
      new ResizeObserver(() => setPw()).observe($('#reader-inner'));
      setPw();
      await pollState();
      $('#loading')?.remove();
      S.pollTimer = setInterval(pollState, 1500);
      document.addEventListener('visibilitychange', () => { if (!document.hidden) pollState(); });
      if (params.get('annot') === '1') toggleAnnotMode(true);
    } catch (err) {
      console.error(err);
      const loading = $('#loading');
      if (loading) loading.textContent = '加载失败：' + err.message;
    }
  }

  function applyProjectMeta() {
    const project = (S.manifest && S.manifest.project) || {};
    const title = project.title || '课件批注工作台';
    const subtitle = project.subtitle || '';
    S.projectTitle = title;
    document.title = subtitle ? `${title} · ${subtitle}` : title;
    const nameEl = $('.brand-name');
    if (nameEl) nameEl.textContent = title;
    const subEl = $('.brand-sub');
    if (subEl) {
      subEl.textContent = subtitle;
      subEl.classList.toggle('hidden', !subtitle);
    }
  }

  function renderChapterTabs() {
    const nav = $('#chapter-tabs');
    nav.innerHTML = '';
    S.manifest.chapters.forEach((ch) => {
      const btn = el('button', 'chapter-tab');
      btn.type = 'button';
      btn.dataset.ch = ch.id;
      btn.append(el('span', 'ch-id', ch.id), document.createTextNode(' ' + ch.title));
      btn.addEventListener('click', () => { if (ch.id !== S.current) switchChapter(ch.id); });
      nav.appendChild(btn);
    });
  }

  function updateTabs() {
    $$('.chapter-tab').forEach((btn) => btn.classList.toggle('on', btn.dataset.ch === S.current));
  }

  async function loadChapter(id) {
    if (S.chapters.has(id)) return S.chapters.get(id);
    const meta = S.manifest.chapters.find((c) => c.id === id);
    const doc = await fetchJSON('/' + meta.data);
    S.chapters.set(id, doc);
    return doc;
  }

  function preloadChapters() {
    S.manifest.chapters.forEach((c) => { if (!S.chapters.has(c.id)) loadChapter(c.id).catch(() => {}); });
  }

  async function switchChapter(id, opts = {}) {
    const meta = S.manifest.chapters.find((c) => c.id === id);
    if (!meta) return;
    closePopover(true);
    const doc = await loadChapter(id);
    S.current = id;
    localStorage.setItem('study.chapter', id);
    updateTabs();
    $('#toc-meta').textContent = `${meta.pages} 页`;
    renderPages(doc, meta);
    renderToc(doc);
    renderAnnotations();
    renderNotes();
    $('#reader').scrollTop = 0;
    S.currentPage = opts.page || 1;
    updatePagePill();
    if (opts.page) requestAnimationFrame(() => gotoPage(opts.page, false));
    preloadChapters();
  }

  /* ================= 4. 页面渲染与滚动 ================= */
  function renderPages(doc, meta) {
    const inner = $('#reader-inner');
    inner.innerHTML = '';
    const frag = document.createDocumentFragment();
    for (const pg of doc.pages) {
      const fig = el('figure', 'page');
      fig.dataset.page = String(pg.n);
      fig.style.aspectRatio = `${doc.pageW} / ${doc.pageH}`;

      const img = el('img', 'page-img');
      img.loading = 'lazy';
      img.decoding = 'async';
      img.alt = `第 ${pg.n} 页${pg.title ? ' · ' + pg.title : ''}`;
      img.src = `/${meta.img}/${String(pg.n).padStart(3, '0')}.webp`;

      const layer = el('div', 'text-layer');
      pg.lines.forEach((line, i) => {
        const node = el('div', 'line');
        node.textContent = line.t;
        node.dataset.i = String(i);
        node.dataset.b = String(line.b);
        node.style.left = (line.x * 100).toFixed(3) + '%';
        node.style.top = (line.y * 100).toFixed(3) + '%';
        node.style.width = (Math.min(1 - line.x, line.w + 0.004) * 100).toFixed(3) + '%';
        node.style.height = (line.h * 100).toFixed(3) + '%';
        node.style.fontSize = `calc(var(--pw) * ${line.f})`;
        layer.appendChild(node);
      });

      fig.append(img, layer, el('div', 'annot-layer'), el('div', 'page-cap', String(pg.n)));
      frag.appendChild(fig);
    }
    inner.appendChild(frag);
    requestAnimationFrame(setPw);
  }

  function setPw() {
    const inner = $('#reader-inner');
    if (!inner) return;
    const width = inner.getBoundingClientRect().width;
    if (width > 0) inner.style.setProperty('--pw', width.toFixed(1) + 'px');
  }

  function renderToc(doc) {
    const list = $('#toc-list');
    list.innerHTML = '';
    const frag = document.createDocumentFragment();
    doc.pages.forEach((pg) => {
      const li = el('li', 'toc-item');
      li.dataset.page = String(pg.n);
      if (pg.n === S.currentPage) li.classList.add('active');
      li.append(el('span', 'toc-num', String(pg.n)), el('span', 'toc-title', pg.title || `第 ${pg.n} 页`));
      if (pg.title) li.title = pg.title;
      li.addEventListener('click', () => gotoPage(pg.n));
      frag.appendChild(li);
    });
    list.appendChild(frag);
  }

  function updateTocActive() {
    let active = null;
    $$('#toc-list .toc-item').forEach((li) => {
      const on = Number(li.dataset.page) === S.currentPage;
      li.classList.toggle('active', on);
      if (on) active = li;
    });
    if (!active) return;
    const list = $('#toc-list');
    const r = active.getBoundingClientRect();
    const lr = list.getBoundingClientRect();
    if (r.top < lr.top || r.bottom > lr.bottom) active.scrollIntoView({ block: 'nearest' });
  }

  function pageData(n) {
    const doc = S.chapters.get(S.current);
    return doc ? doc.pages[n - 1] : null;
  }
  function pageCount() {
    const doc = S.chapters.get(S.current);
    return doc ? doc.pages.length : 0;
  }
  function updatePagePill() {
    const node = $('#page-pill');
    if (node) node.textContent = `${S.currentPage} / ${pageCount()}`;
  }

  function gotoPage(n, smooth = true) {
    const target = $(`.page[data-page="${n}"]`);
    if (!target) return;
    const reader = $('#reader');
    const top = target.getBoundingClientRect().top - reader.getBoundingClientRect().top + reader.scrollTop - 24;
    const distance = Math.abs(top - reader.scrollTop);
    if (smooth && distance < 2400) {
      reader.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
    } else {
      // 跨章或远距离跳转直接定位，避免长距离平滑滚动
      const previous = reader.style.scrollBehavior;
      reader.style.scrollBehavior = 'auto';
      reader.scrollTo({ top: Math.max(0, top), behavior: 'auto' });
      reader.style.scrollBehavior = previous;
    }
    S.currentPage = n;
    updatePagePill();
    updateTocActive();
  }

  function flashPage(n) {
    const page = $(`.page[data-page="${n}"]`);
    if (!page) return;
    page.classList.remove('flash');
    void page.offsetWidth;
    page.classList.add('flash');
  }

  let scrollRaf = 0;
  function bindReaderScroll() {
    $('#reader').addEventListener('scroll', () => {
      if (scrollRaf) return;
      scrollRaf = requestAnimationFrame(() => { scrollRaf = 0; onScroll(); });
    });
  }
  function onScroll() {
    const reader = $('#reader');
    const readerTop = reader.getBoundingClientRect().top;
    let current = 1;
    for (const page of $$('.page', reader)) {
      if (page.getBoundingClientRect().top - readerTop <= 140) current = Number(page.dataset.page);
      else break;
    }
    if (current !== S.currentPage) {
      S.currentPage = current;
      updatePagePill();
      updateTocActive();
    }
  }

  /* ================= 5. 批注状态同步 ================= */
  function statusOf(a) {
    return a.resolved ? 'resolved' : (S.answers[a.id] ? 'answered' : 'open');
  }
  function openAnnotations() {
    return S.annotations.filter((a) => !a.resolved && !S.answers[a.id]);
  }

  async function pollState() {
    try {
      const state = await fetchJSON('/api/state');
      if (state.workbench && state.workbench.root) S.root = state.workbench.root;
      const answersKey = JSON.stringify(state.answers || {});
      const annChanged = state.annotationsRev !== S.lastAnnRev;
      const ansChanged = answersKey !== S.lastAnsKey;
      if (annChanged) {
        S.annotations = state.annotations || [];
        S.lastAnnRev = state.annotationsRev;
      }
      S.answers = state.answers || {};
      S.lastAnsKey = answersKey;
      if (annChanged || ansChanged) {
        renderAnnotations();
        renderNotes();
        updatePendingBadge();
      }
    } catch (err) {
      /* 服务重启或短暂不可用时静默重试 */
    }
  }

  function updatePendingBadge() {
    const count = openAnnotations().length;
    const badge = $('#pending-count');
    if (badge) {
      badge.textContent = String(count);
      badge.classList.toggle('hidden', count === 0);
    }
    const ask = $('#ask-copy');
    if (ask) ask.title = count ? `${count} 条批注待回答，点击复制提问` : '暂无待回答批注';
  }

  function renderAnnotations() {
    $$('.annot-layer').forEach((layer) => { layer.innerHTML = ''; });
    const list = S.annotations
      .filter((a) => a.ch === S.current)
      .sort((a, b) => a.page - b.page || String(a.created).localeCompare(String(b.created)));
    const counters = new Map();
    for (const ann of list) {
      const pageEl = $(`.page[data-page="${ann.page}"]`);
      if (!pageEl) continue;
      const layer = $('.annot-layer', pageEl);
      if (!layer) continue;
      const status = statusOf(ann);
      const rects = (ann.rects || []).slice(0, 30);
      for (const r of rects) {
        const hl = el('div', 'hl ' + status);
        hl.dataset.id = ann.id;
        hl.style.left = (r.x * 100) + '%';
        hl.style.top = (r.y * 100) + '%';
        hl.style.width = (r.w * 100) + '%';
        hl.style.height = (r.h * 100) + '%';
        layer.appendChild(hl);
      }
      const index = (counters.get(ann.page) || 0) + 1;
      counters.set(ann.page, index);
      const r0 = rects[0] || { x: 0.5, y: 0.02, w: 0, h: 0 };
      const pin = el('button', 'pin ' + status, String(index));
      pin.type = 'button';
      pin.dataset.id = ann.id;
      pin.style.left = (clamp(r0.x + r0.w + 0.006, 0.01, 0.985) * 100) + '%';
      pin.style.top = (clamp(r0.y + Math.min(r0.h * 0.5, 0.015), 0.01, 0.99) * 100) + '%';
      pin.title = `${ann.tag ? '[' + ann.tag + '] ' : ''}${ann.q || ''}`.slice(0, 160);
      attachPinDrag(pin, ann, pageEl);
      pin.addEventListener('click', (ev) => {
        ev.stopPropagation();
        if (pin.dataset.dragged === '1') { delete pin.dataset.dragged; return; }
        selectAnnotation(ann.id);
      });
      layer.appendChild(pin);
      if (S.selectedId === ann.id) $$('.hl', layer).forEach((hl) => hl.classList.add('active'));
    }
    updatePendingBadge();
  }

  /* ---- 图钉拖动：把批注挪到另一行，或平移框选区域 ---- */
  function attachPinDrag(pin, ann, pageEl) {
    pin.addEventListener('pointerdown', (ev) => {
      if (ev.button !== 0) return;
      ev.preventDefault();
      ev.stopPropagation();
      const pr = pageEl.getBoundingClientRect();
      const pinStart = {
        x: parseFloat(pin.style.left) / 100,
        y: parseFloat(pin.style.top) / 100,
      };
      const start = { x: ev.clientX, y: ev.clientY };
      const pos = { x: pinStart.x, y: pinStart.y };
      const ghost = el('div', 'drag-ghost', pin.textContent);
      ghost.style.left = pin.style.left;
      ghost.style.top = pin.style.top;
      $('.annot-layer', pageEl).appendChild(ghost);
      pin.classList.add('dragging');
      try { pin.setPointerCapture(ev.pointerId); } catch (err) { /* 合成事件没有真实指针 */ }
      let moved = false;
      const move = (e) => {
        if (!moved && Math.abs(e.clientX - start.x) + Math.abs(e.clientY - start.y) < 4) return;
        moved = true;
        pos.x = clamp((e.clientX - pr.left) / pr.width, 0, 1);
        pos.y = clamp((e.clientY - pr.top) / pr.height, 0, 1);
        ghost.style.left = (pos.x * 100) + '%';
        ghost.style.top = (pos.y * 100) + '%';
      };
      const finish = () => {
        pin.removeEventListener('pointermove', move);
        pin.removeEventListener('pointerup', finish);
        pin.removeEventListener('pointercancel', finish);
        pin.classList.remove('dragging');
        ghost.remove();
        if (!moved) return;
        pin.dataset.dragged = '1';
        movePinAnnotation(ann, pos, pinStart);
      };
      pin.addEventListener('pointermove', move);
      pin.addEventListener('pointerup', finish);
      pin.addEventListener('pointercancel', finish);
    });
  }

  async function movePinAnnotation(ann, pos, pinStart) {
    const pg = pageData(ann.page);
    if (!pg) return;
    const doc = S.chapters.get(ann.ch);
    const aspect = doc && doc.pageH ? doc.pageW / doc.pageH : 1.78;
    let best = null;
    let bestDistance = Infinity;
    for (const line of pg.lines) {
      const cx = line.x + line.w / 2;
      const cy = line.y + line.h / 2;
      const inside = pos.x >= line.x - 0.012 && pos.x <= line.x + line.w + 0.012 &&
        pos.y >= line.y - 0.012 && pos.y <= line.y + line.h + 0.012;
      const distance = inside ? 0 : Math.hypot(pos.x - cx, (pos.y - cy) * aspect);
      if (distance < bestDistance) { bestDistance = distance; best = line; }
    }
    const item = { ...ann };
    if (ann.kind === 'region') {
      const dx = pos.x - pinStart.x;
      const dy = pos.y - pinStart.y;
      item.rects = (ann.rects || []).map((r) => ({
        x: clamp(r.x + dx, 0, 1), y: clamp(r.y + dy, 0, 1), w: r.w, h: r.h,
      }));
    } else if (best && bestDistance <= 0.04) {
      item.rects = [{ x: best.x, y: best.y, w: best.w, h: best.h }];
      item.quote = best.t;
      item.kind = 'line';
    } else {
      toast('没有落到文字上，位置未改动');
      return;
    }
    try {
      const res = await postJSON('/api/annotations', { action: 'save', item });
      S.annotations = S.annotations.filter((a) => a.id !== res.item.id).concat(res.item);
      S.lastAnnRev = res.rev;
      renderAnnotations();
      renderNotes();
      selectAnnotation(res.item.id);
      toast('已移动');
    } catch (err) {
      toast('移动失败：' + err.message);
    }
  }

  /* ---- 公式快捷输入与实时预览 ---- */
  const LATEX_SNIPPETS = [
    '\\alpha', '\\beta', '\\lambda', '\\mu', '\\varepsilon',
    '\\in', '\\subset', '\\oplus', '\\dim', '\\operatorname{rank}',
    '\\Rightarrow', '\\neq', '\\leq', '\\to', '\\mathbb{R}^n',
    '\\frac{a}{b}', '\\sqrt{\\ }', '\\sum_{i=1}^{n}', '\\int_a^b',
    '\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}',
  ];

  function insertAtCursor(textarea, text) {
    const start = textarea.selectionStart ?? textarea.value.length;
    const end = textarea.selectionEnd ?? textarea.value.length;
    textarea.value = textarea.value.slice(0, start) + text + textarea.value.slice(end);
    const caret = start + text.length;
    textarea.selectionStart = caret;
    textarea.selectionEnd = caret;
    textarea.focus({ preventScroll: true });
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function buildLatexToolbar(textarea) {
    const bar = el('div', 'latex-bar');
    bar.setAttribute('role', 'toolbar');
    bar.setAttribute('aria-label', '插入公式');
    LATEX_SNIPPETS.forEach((tex) => {
      const btn = el('button', 'latex-btn');
      btn.type = 'button';
      btn.dataset.tex = tex;
      btn.title = tex;
      try {
        btn.innerHTML = window.katex
          ? window.katex.renderToString(tex, { throwOnError: false })
          : escapeHtml(tex);
      } catch (err) {
        btn.textContent = tex;
      }
      btn.addEventListener('mousedown', (ev) => ev.preventDefault());
      btn.addEventListener('click', () => {
        const display = /\\begin\{|\\sum|\\int/.test(tex);
        insertAtCursor(textarea, (display ? '$$' : '$') + tex + (display ? '$$' : '$'));
      });
      bar.appendChild(btn);
    });
    return bar;
  }

  function buildQuestionPreview(textarea) {
    const box = el('div', 'pop-preview hidden');
    const update = () => {
      const text = textarea.value.trim();
      if (!text) {
        box.classList.add('hidden');
        box.textContent = '';
        return;
      }
      box.textContent = '';
      box.appendChild(renderMarkdown(text));
      box.classList.remove('hidden');
    };
    textarea.addEventListener('input', debounce(update, 120));
    return { box, update };
  }

  function makePopoverDraggable(pop, handle) {
    let drag = null;
    handle.addEventListener('pointerdown', (ev) => {
      if (ev.button !== 0 || ev.target.closest('button')) return;
      const rect = pop.getBoundingClientRect();
      drag = { dx: ev.clientX - rect.left, dy: ev.clientY - rect.top };
      pop.classList.add('dragging');
      try { handle.setPointerCapture(ev.pointerId); } catch (err) { /* 合成事件 */ }
      ev.preventDefault();
    });
    handle.addEventListener('pointermove', (ev) => {
      if (!drag) return;
      pop.style.left = clamp(ev.clientX - drag.dx, 8, window.innerWidth - pop.offsetWidth - 8) + 'px';
      pop.style.top = clamp(ev.clientY - drag.dy, 8, window.innerHeight - pop.offsetHeight - 8) + 'px';
      pop.dataset.pinned = '1';
    });
    const end = () => { drag = null; pop.classList.remove('dragging'); };
    handle.addEventListener('pointerup', end);
    handle.addEventListener('pointercancel', end);
  }

  function selectAnnotation(id) {
    S.selectedId = id;
    $$('.hl').forEach((hl) => hl.classList.toggle('active', hl.dataset.id === id));
    $$('.note').forEach((note) => note.classList.toggle('active', note.dataset.id === id));
    const card = $(`.note[data-id="${CSS.escape(id)}"]`);
    if (card) card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function gotoAnnotation(ann) {
    const jump = () => { gotoPage(ann.page); flashPage(ann.page); selectAnnotation(ann.id); };
    if (ann.ch !== S.current) switchChapter(ann.ch, { page: ann.page }).then(jump);
    else jump();
  }

  /* ================= 6. 批注交互 ================= */
  function toggleAnnotMode(force) {
    S.annotMode = typeof force === 'boolean' ? force : !S.annotMode;
    document.body.classList.toggle('annot-on', S.annotMode);
    $('#annot-toggle').classList.toggle('on', S.annotMode);
    if (S.annotMode) toast('批注模式 · Esc 退出', 1800);
    else closePopover(true);
  }

  function bindReader() {
    bindReaderScroll();
    const reader = $('#reader');
    reader.addEventListener('mousedown', onReaderDown);
    reader.addEventListener('click', onReaderClick);
    document.addEventListener('mousemove', onDocMove);
    document.addEventListener('mouseup', onDocUp);
    document.addEventListener('mousedown', onDocDown);
  }

  function onDocDown(ev) {
    const pop = $('#annot-popover');
    if (!pop || pop.classList.contains('hidden')) return;
    if (S.region) return;
    if (ev.target.closest('#annot-popover')) return;
    closePopover();
  }

  function onReaderDown(ev) {
    if (!S.annotMode || ev.button !== 0 || !ev.shiftKey) return;
    const pageEl = ev.target.closest('.page');
    if (!pageEl) return;
    ev.preventDefault();
    const pr = pageEl.getBoundingClientRect();
    const box = el('div', 'region-box');
    box.style.left = (ev.clientX - pr.left) + 'px';
    box.style.top = (ev.clientY - pr.top) + 'px';
    $('.annot-layer', pageEl).appendChild(box);
    S.region = { pageEl, box, x0: ev.clientX, y0: ev.clientY, moved: false, last: null };
  }

  function onDocMove(ev) {
    const region = S.region;
    if (!region) return;
    const pr = region.pageEl.getBoundingClientRect();
    const x0 = clamp(region.x0 - pr.left, 0, pr.width);
    const y0 = clamp(region.y0 - pr.top, 0, pr.height);
    const x1 = clamp(ev.clientX - pr.left, 0, pr.width);
    const y1 = clamp(ev.clientY - pr.top, 0, pr.height);
    const left = Math.min(x0, x1);
    const top = Math.min(y0, y1);
    const w = Math.abs(x1 - x0);
    const h = Math.abs(y1 - y0);
    region.box.style.left = left + 'px';
    region.box.style.top = top + 'px';
    region.box.style.width = w + 'px';
    region.box.style.height = h + 'px';
    region.last = { left, top, w, h };
    region.moved = region.moved || w > 6 || h > 6;
  }

  function onDocUp() {
    const region = S.region;
    if (region) {
      S.region = null;
      const rect = region.last;
      region.box.remove();
      if (region.moved && rect && rect.w > 6 && rect.h > 6) {
        S.regionJustFinished = true;
        const pr = region.pageEl.getBoundingClientRect();
        const norm = { x: rect.left / pr.width, y: rect.top / pr.height, w: rect.w / pr.width, h: rect.h / pr.height };
        openPopover(targetFromRegion(Number(region.pageEl.dataset.page), norm, region.pageEl));
      }
      return;
    }
    if (!S.annotMode) return;
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed && String(sel).trim()) {
      setTimeout(() => {
        const target = targetFromSelection(sel);
        if (target) openPopover(target);
      }, 0);
    }
  }

  function onReaderClick(ev) {
    if (!S.annotMode) return;
    if (S.regionJustFinished) { S.regionJustFinished = false; return; }
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed) return;
    const line = ev.target.closest('.line');
    if (line) openPopover(targetFromLine(line));
  }

  function blockText(pg, blockIndex) {
    return pg.lines.filter((l) => l.b === blockIndex).map((l) => l.t).join(' ').slice(0, 900);
  }
  function pageQuote(pg) {
    return (pg.title || `第 ${pg.n} 页`) + (pg.text ? '｜' + pg.text.slice(0, 80).replace(/\s+/g, ' ') : '');
  }

  function targetFromLine(lineEl) {
    const pageEl = lineEl.closest('.page');
    const n = Number(pageEl.dataset.page);
    const pg = pageData(n);
    const lineIndex = Number(lineEl.dataset.i);
    const line = pg.lines[lineIndex];
    const block = pg.blocks[line.b] || { x: line.x, y: line.y, w: line.w, h: line.h };
    const cands = [
      { key: 'line', label: '这一行', rects: [{ x: line.x, y: line.y, w: line.w, h: line.h }], quote: line.t },
      { key: 'block', label: '整段', rects: [block], quote: blockText(pg, line.b) },
    ];
    let candIdx = 0;
    const formula = formulaBlock(pg, lineIndex);
    if (formula) {
      cands.splice(1, 0, { key: 'formula', label: '公式块', rects: [formula.rect], quote: formula.quote });
      candIdx = 1;
    }
    cands.push({ key: 'page', label: '整页', rects: [{ x: 0.01, y: 0.01, w: 0.98, h: 0.98 }], quote: pageQuote(pg) });
    return { ch: S.current, page: n, kind: 'line', pageEl, cands, candIdx };
  }

  // 单行点击常常只框到公式的一角（分数线、矩阵拆成多行），
  // 这里把相邻、水平重叠的公式行合成一个「公式块」候选。
  function formulaBlock(pg, index) {
    const base = pg.lines[index];
    if (!base || base.t.length < 3) return null;
    const cjk = (base.t.match(/[\u4e00-\u9fff]/g) || []).length;
    const mathy = cjk === 0 || (cjk <= 1 && /[=⇒→<>α-ωΑ-Ω∑∫√±]/.test(base.t));
    if (!mathy) return null;
    const group = [base];
    for (const dir of [-1, 1]) {
      let cur = base;
      let i = index + dir;
      while (i >= 0 && i < pg.lines.length && group.length < 6) {
        const cand = pg.lines[i];
        const gap = dir < 0 ? cur.y - (cand.y + cand.h) : cand.y - (cur.y + cur.h);
        if (gap > 0.95 * Math.max(base.h, 0.012)) break;
        if (!(cand.x < cur.x + cur.w && cand.x + cand.w > cur.x)) break;
        group.push(cand);
        cur = cand;
        i += dir;
      }
    }
    if (group.length < 2) return null;
    const rect = {
      x: Math.min(...group.map((l) => l.x)),
      y: Math.min(...group.map((l) => l.y)),
    };
    rect.w = Math.max(...group.map((l) => l.x + l.w)) - rect.x;
    rect.h = Math.max(...group.map((l) => l.y + l.h)) - rect.y;
    const quote = group.map((l) => l.t).join(' ').slice(0, 900);
    return { rect, quote };
  }

  function targetFromRegion(n, rect, pageEl) {
    const pg = pageData(n);
    const hits = pg.lines.filter((l) => !(l.x > rect.x + rect.w || l.x + l.w < rect.x ||
      l.y > rect.y + rect.h || l.y + l.h < rect.y));
    return {
      ch: S.current, page: n, kind: 'region', pageEl, candIdx: 0,
      cands: [
        { key: 'region', label: '框选区域', rects: [rect], quote: hits.map((l) => l.t).join(' ').slice(0, 900) },
        { key: 'page', label: '整页', rects: [{ x: 0.01, y: 0.01, w: 0.98, h: 0.98 }], quote: pageQuote(pg) },
      ],
    };
  }

  function targetFromSelection(sel) {
    const range = sel.getRangeAt(0);
    const start = range.startContainer.nodeType === 1
      ? range.startContainer : range.startContainer.parentElement;
    const pageEl = start && start.closest ? start.closest('.page') : null;
    if (!pageEl) return null;
    const n = Number(pageEl.dataset.page);
    const pg = pageData(n);
    const pr = pageEl.getBoundingClientRect();
    const rects = Array.from(range.getClientRects())
      .filter((r) => r.width > 2 && r.height > 2)
      .map((r) => ({
        x: clamp((r.left - pr.left) / pr.width, 0, 1),
        y: clamp((r.top - pr.top) / pr.height, 0, 1),
        w: clamp(r.width / pr.width, 0, 1),
        h: clamp(r.height / pr.height, 0, 1),
      }))
      .slice(0, 16);
    if (!rects.length) return null;
    const quote = String(sel).replace(/\s+/g, ' ').trim().slice(0, 900);
    const box = rects.reduce((acc, r) => ({
      x: Math.min(acc.x, r.x), y: Math.min(acc.y, r.y),
      x2: Math.max(acc.x2, r.x + r.w), y2: Math.max(acc.y2, r.y + r.h),
    }), { x: 1, y: 1, x2: 0, y2: 0 });
    const boxRect = { x: box.x, y: box.y, w: box.x2 - box.x, h: box.y2 - box.y };
    const blocks = new Set();
    pg.lines.forEach((l) => {
      if (!(l.x > boxRect.x + boxRect.w || l.x + l.w < boxRect.x ||
        l.y > boxRect.y + boxRect.h || l.y + l.h < boxRect.y)) blocks.add(l.b);
    });
    const cands = [{ key: 'sel', label: '所选文字', rects, quote }];
    if (blocks.size === 1) {
      const bi = [...blocks][0];
      cands.push({ key: 'block', label: '整段', rects: [pg.blocks[bi] || boxRect], quote: blockText(pg, bi) });
    }
    cands.push({ key: 'page', label: '整页', rects: [{ x: 0.01, y: 0.01, w: 0.98, h: 0.98 }], quote: pageQuote(pg) });
    return { ch: S.current, page: n, kind: 'selection', pageEl, cands, candIdx: 0 };
  }

  function openPopover(target) {
    closePopover(true);
    S.pending = target;
    const pop = $('#annot-popover');
    pop.innerHTML = '';
    pop.classList.remove('hidden');
    drawPendingBoxes(target);
    const head = el('div', 'pop-head draggable');
    head.append(el('span', 'pop-drag', '⠿'), el('span', 'pop-title', '新建批注'),
      el('span', 'pop-sub', `${target.ch} · p${target.page}`));
    const close = el('button', 'icon-btn pop-close', '×');
    close.type = 'button';
    close.title = '取消（Esc）';
    close.addEventListener('click', () => closePopover());
    head.append(close);
    makePopoverDraggable(pop, head);

    const candRow = el('div', 'pop-cands');
    const quoteBox = el('div', 'pop-quote');
    const setCand = (index) => {
      target.candIdx = index;
      $$('.pop-cand', candRow).forEach((btn, i) => btn.classList.toggle('on', i === index));
      const text = target.cands[index].quote || '（无可提取文字，按位置说明）';
      quoteBox.textContent = text;
      quoteBox.title = text;
      pop.dataset.cand = target.cands[index].key;
      drawPendingBoxes(target);
      if (!pop.dataset.pinned) positionPopover(pop, target);
    };
    target.cands.forEach((cand, i) => {
      const btn = el('button', 'pop-cand' + (i === target.candIdx ? ' on' : ''), cand.label);
      btn.type = 'button';
      btn.dataset.key = cand.key;
      btn.addEventListener('click', () => setCand(i));
      candRow.appendChild(btn);
    });

    const tagRow = el('div', 'pop-tags');
    let tag = '不懂';
    TAGS.forEach((name) => {
      const btn = el('button', 'pop-tag' + (name === tag ? ' on' : ''), name);
      btn.type = 'button';
      btn.dataset.tag = name;
      btn.addEventListener('click', () => {
        tag = name;
        $$('.pop-tag', tagRow).forEach((x) => x.classList.toggle('on', x.dataset.tag === name));
      });
      tagRow.appendChild(btn);
    });

    const textarea = el('textarea', 'pop-text');
    textarea.rows = 3;
    textarea.placeholder = '写下问题…';
    textarea.id = 'annot-text';
    const preview = buildQuestionPreview(textarea);

    const foot = el('div', 'pop-foot');
    foot.append(el('span', 'pop-hint', 'Enter 保存 · Esc 取消'));
    const save = el('button', 'pop-save', '保存批注');
    save.type = 'button';
    save.id = 'annot-save';
    save.addEventListener('click', () => saveAnnotation(target, tag, textarea, save));
    foot.append(save);

    pop.append(head, candRow, quoteBox, tagRow, buildLatexToolbar(textarea), textarea, preview.box, foot);
    setCand(target.candIdx);
    if (!pop.dataset.pinned) positionPopover(pop, target);

    textarea.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' && !ev.shiftKey) {
        ev.preventDefault();
        saveAnnotation(target, tag, textarea, save);
      }
      if (ev.key === 'Escape') { ev.preventDefault(); closePopover(); }
    });
    setTimeout(() => textarea.focus({ preventScroll: true }), 30);
  }

  function positionPopover(pop, target) {
    const pageEl = target.pageEl || $(`.page[data-page="${target.page}"]`);
    const rect = target.cands[target.candIdx]?.rects[0];
    let left = window.innerWidth / 2;
    let top = 140;
    if (pageEl && rect) {
      const pr = pageEl.getBoundingClientRect();
      left = pr.left + (rect.x + rect.w) * pr.width + 14;
      top = pr.top + rect.y * pr.height;
    }
    const width = pop.offsetWidth || 390;
    const height = pop.offsetHeight || 270;
    left = clamp(left, 12, window.innerWidth - width - 12);
    if (top + height + 14 > window.innerHeight) top = Math.max(12, top - height - 14);
    pop.style.left = left + 'px';
    pop.style.top = top + 'px';
  }

  function closePopover(silent) {
    const pop = $('#annot-popover');
    if (!pop) return;
    pop.classList.add('hidden');
    pop.innerHTML = '';
    delete pop.dataset.pinned;
    S.pending = null;
    clearPendingBoxes();
    if (!silent) {
      const sel = window.getSelection();
      if (sel) sel.removeAllRanges();
    }
  }

  let pendingBoxes = [];
  function clearPendingBoxes() {
    pendingBoxes.forEach((box) => box.remove());
    pendingBoxes = [];
  }
  function drawPendingBoxes(target) {
    clearPendingBoxes();
    const pageEl = target.pageEl || $(`.page[data-page="${target.page}"]`);
    if (!pageEl) return;
    const layer = $('.annot-layer', pageEl);
    if (!layer) return;
    const cand = target.cands[target.candIdx];
    cand.rects.forEach((r) => {
      const box = el('div', 'pending-box');
      box.style.left = (r.x * 100) + '%';
      box.style.top = (r.y * 100) + '%';
      box.style.width = (r.w * 100) + '%';
      box.style.height = (r.h * 100) + '%';
      layer.appendChild(box);
      pendingBoxes.push(box);
    });
  }

  async function saveAnnotation(target, tag, textarea, saveBtn) {
    const q = textarea.value.trim();
    if (!q) { textarea.focus(); toast('先写下问题再保存'); return; }
    const cand = target.cands[target.candIdx];
    const item = {
      id: uid(),
      ch: target.ch,
      page: target.page,
      kind: target.kind === 'region' ? 'region' : (cand.key === 'page' ? 'page' : target.kind),
      rects: cand.rects,
      quote: cand.quote || '',
      tag,
      q,
      created: new Date().toISOString(),
      resolved: false,
    };
    saveBtn.disabled = true;
    try {
      const res = await postJSON('/api/annotations', { action: 'save', item });
      const saved = res.item || item;
      S.annotations = S.annotations.filter((a) => a.id !== saved.id).concat(saved);
      S.lastAnnRev = res.rev;
      closePopover(true);
      renderAnnotations();
      renderNotes();
      selectAnnotation(saved.id);
      toast('已保存，点「复制提问」提问');
    } catch (err) {
      console.error(err);
      toast('保存失败：' + err.message);
    } finally {
      saveBtn.disabled = false;
    }
  }

  /* ================= 7. 右侧批注面板 ================= */
  function renderNotes() {
    const list = $('#notes-list');
    if (!list) return;
    if (document.activeElement && document.activeElement.closest && document.activeElement.closest('.follow-form')) return;
    const scrollTop = list.scrollTop;
    const counts = { all: S.annotations.length, open: 0, answered: 0, resolved: 0 };
    S.annotations.forEach((a) => { counts[statusOf(a)] += 1; });
    const labels = { all: '全部', open: '待回答', answered: '已回答', resolved: '已解决' };
    $$('#notes-filters .chip').forEach((chip) => {
      const f = chip.dataset.filter;
      chip.textContent = `${labels[f]}${counts[f] ? ' ' + counts[f] : ''}`;
      chip.classList.toggle('on', f === S.filter);
    });
    $('#scope-current').checked = S.scopeCurrent;

    let items = S.annotations.slice();
    if (S.scopeCurrent) items = items.filter((a) => a.ch === S.current);
    if (S.filter !== 'all') items = items.filter((a) => statusOf(a) === S.filter);
    const order = new Map(S.manifest.chapters.map((c, i) => [c.id, i]));
    items.sort((a, b) => (order.get(a.ch) - order.get(b.ch)) || (a.page - b.page) ||
      String(a.created).localeCompare(String(b.created)));

    list.innerHTML = '';
    if (!items.length) {
      const empty = el('div', 'notes-empty');
      if (S.annotations.length) empty.textContent = '当前筛选下没有批注。';
      else empty.textContent = '点「批注」，选中一行或框选区域，写下问题。';
      list.appendChild(empty);
    } else {
      const frag = document.createDocumentFragment();
      items.forEach((a) => frag.appendChild(renderNoteCard(a)));
      list.appendChild(frag);
    }
    list.scrollTop = scrollTop;
  }

  function renderNoteCard(ann) {
    const card = el('article', 'note');
    card.dataset.id = ann.id;
    if (S.selectedId === ann.id) card.classList.add('active');
    const status = statusOf(ann);

    const head = el('div', 'note-head');
    const loc = el('button', 'note-loc', `${ann.ch} · p${ann.page}`);
    loc.type = 'button';
    loc.title = '跳转到该页';
    loc.addEventListener('click', () => gotoAnnotation(ann));
    head.append(loc);
    if (ann.tag) head.append(el('span', 'note-tag', ann.tag));
    head.append(el('span', 'note-status ' + status,
      status === 'open' ? '待回答' : status === 'answered' ? '已回答' : '已解决'));
    const actions = el('div', 'note-actions');
    const resolve = el('button', '', status === 'resolved' ? '↺' : '✓');
    resolve.title = status === 'resolved' ? '标为未解决' : '标为已解决';
    resolve.addEventListener('click', () => {
      const current = S.annotations.find((x) => x.id === ann.id) || ann;
      toggleResolve(current, !current.resolved);
    });
    const remove = el('button', 'danger', '✕');
    remove.title = '删除批注';
    remove.addEventListener('click', () => deleteAnnotation(ann));
    actions.append(resolve, remove);
    head.append(actions);

    const quote = el('div', 'quote', ann.quote || '（按位置批注）');
    quote.title = ann.quote || '';
    quote.addEventListener('click', () => gotoAnnotation(ann));

    const question = el('div', 'question');
    const renderedQuestion = renderMarkdown(ann.q || '（未填写问题）');
    while (renderedQuestion.firstChild) question.appendChild(renderedQuestion.firstChild);
    card.append(head, quote, question);

    if (ann.parent) {
      const parent = S.annotations.find((x) => x.id === ann.parent);
      if (parent) {
        const link = el('button', 'link-btn', `↳ 追问自 p${parent.page}「${(parent.q || '').slice(0, 16)}…」`);
        link.type = 'button';
        link.addEventListener('click', () => { gotoAnnotation(parent); selectAnnotation(parent.id); });
        card.append(link);
      }
    }

    const answer = S.answers[ann.id];
    if (answer && answer.md) {
      const box = el('div', 'answer');
      box.appendChild(renderMarkdown(answer.md));
      card.append(box);
    } else if (!ann.resolved) {
      card.append(el('div', 'waiting', '等待回答'));
    }

    const foot = el('div', 'note-foot');
    const follow = el('button', 'link-btn', '＋ 追问');
    follow.type = 'button';
    foot.append(follow, el('span', 'note-time', fmtTime(ann.created)));
    card.append(foot);

    let form = null;
    follow.addEventListener('click', () => {
      if (form) { form.remove(); form = null; return; }
      form = buildFollowForm(ann, () => { form = null; });
      card.appendChild(form);
      const textarea = $('textarea', form);
      textarea.value = S.drafts.get(ann.id) || '';
      form._updatePreview();
      textarea.focus();
    });
    return card;
  }

  function buildFollowForm(parent, onDone) {
    const form = el('div', 'follow-form');
    const textarea = el('textarea');
    textarea.placeholder = '继续追问…';
    const preview = buildQuestionPreview(textarea);
    form._updatePreview = preview.update;
    const row = el('div', 'row');
    const cancel = el('button', 'mini', '取消');
    cancel.type = 'button';
    const ok = el('button', 'mini primary', '提交追问');
    ok.type = 'button';
    row.append(cancel, ok);
    form.append(buildLatexToolbar(textarea), textarea, preview.box, row);
    textarea.addEventListener('input', () => S.drafts.set(parent.id, textarea.value));
    textarea.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' && !ev.shiftKey) {
        ev.preventDefault();
        submitFollow(parent, textarea, ok, onDone);
      }
    });
    cancel.addEventListener('click', () => { form.remove(); onDone(); });
    ok.addEventListener('click', () => submitFollow(parent, textarea, ok, onDone));
    return form;
  }

  async function submitFollow(parent, textarea, btn, onDone) {
    const q = textarea.value.trim();
    if (!q) return;
    btn.disabled = true;
    const item = {
      id: uid(), ch: parent.ch, page: parent.page, kind: 'follow',
      rects: parent.rects, quote: parent.quote, tag: parent.tag || '不懂',
      q, created: new Date().toISOString(), resolved: false, parent: parent.id,
    };
    try {
      const res = await postJSON('/api/annotations', { action: 'save', item });
      S.annotations = S.annotations.filter((a) => a.id !== res.item.id).concat(res.item);
      S.lastAnnRev = res.rev;
      S.drafts.delete(parent.id);
      renderAnnotations();
      renderNotes();
      toast('追问已保存');
      if (onDone) onDone();
    } catch (err) {
      toast('提交失败：' + err.message);
      btn.disabled = false;
    }
  }

  async function toggleResolve(ann, resolved) {
    try {
      const res = await postJSON('/api/annotations', { action: 'resolve', id: ann.id, resolved });
      const target = S.annotations.find((x) => x.id === ann.id);
      if (target) target.resolved = resolved;
      ann.resolved = resolved;
      S.lastAnnRev = res.rev;
      renderAnnotations();
      renderNotes();
    } catch (err) {
      toast('操作失败：' + err.message);
    }
  }

  async function deleteAnnotation(ann) {
    if (!confirm('删除这条批注？')) return;
    try {
      const res = await postJSON('/api/annotations', { action: 'delete', id: ann.id });
      S.annotations = S.annotations.filter((a) => a.id !== ann.id);
      S.lastAnnRev = res.rev;
      if (S.selectedId === ann.id) S.selectedId = null;
      renderAnnotations();
      renderNotes();
    } catch (err) {
      toast('删除失败：' + err.message);
    }
  }

  function renderMarkdown(md) {
    const div = el('div');
    const raw = String(md || '');
    // 先把 $...$ / $$...$$ 抽成占位符：否则 marked 会把公式里的 \\ 和反斜杠命令吃掉。
    const formulas = [];
    const protectedText = raw.replace(/\$\$[\s\S]+?\$\$|\$[^$\n]+?\$/g, (match) => {
      formulas.push(match);
      return `@@MATH${formulas.length - 1}@@`;
    });
    try {
      div.innerHTML = window.marked
        ? window.marked.parse(protectedText, { gfm: true, breaks: true })
        : escapeHtml(protectedText).replace(/\n/g, '<br>');
    } catch (err) {
      div.textContent = raw;
      return div;
    }
    if (formulas.length) {
      const walker = document.createTreeWalker(div, NodeFilter.SHOW_TEXT);
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      for (const node of nodes) {
        if (!node.nodeValue.includes('@@MATH')) continue;
        const frag = document.createDocumentFragment();
        for (const part of node.nodeValue.split(/(@@MATH\d+@@)/)) {
          const hit = part.match(/^@@MATH(\d+)@@$/);
          if (hit) frag.appendChild(document.createTextNode(formulas[Number(hit[1])] || ''));
          else if (part) frag.appendChild(document.createTextNode(part));
        }
        node.parentNode.replaceChild(frag, node);
      }
    }
    if (window.renderMathInElement) {
      try {
        window.renderMathInElement(div, {
          delimiters: [
            { left: '$$', right: '$$', display: true },
            { left: '\\[', right: '\\]', display: true },
            { left: '$', right: '$', display: false },
            { left: '\\(', right: '\\)', display: false },
          ],
          throwOnError: false,
        });
      } catch (err) { /* 公式渲染失败时保留原文 */ }
    }
    return div;
  }

  /* ================= 8. 搜索 ================= */
  function bindSearch() {
    const input = $('#search-input');
    input.addEventListener('input', debounce(runSearch, 180));
    input.addEventListener('focus', () => { if (input.value.trim()) runSearch(); });
    input.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape') { input.value = ''; hideSearch(); input.blur(); }
      if (ev.key === 'Enter') {
        const first = $('.search-hit');
        if (first) first.click();
      }
    });
    document.addEventListener('mousedown', (ev) => {
      if (!ev.target.closest('.search-box')) hideSearch();
    });
  }

  function hideSearch() {
    const box = $('#search-results');
    box.classList.add('hidden');
    box.innerHTML = '';
  }

  async function runSearch() {
    const query = $('#search-input').value.trim().toLowerCase();
    if (!query) { hideSearch(); return; }
    try {
      await Promise.all(S.manifest.chapters.map((c) => loadChapter(c.id)));
    } catch (err) { return; }
    const hits = [];
    for (const meta of S.manifest.chapters) {
      const doc = S.chapters.get(meta.id);
      if (!doc) continue;
      for (const pg of doc.pages) {
        const idx = pg.text.toLowerCase().indexOf(query);
        if (idx >= 0) hits.push({ ch: meta.id, page: pg.n, title: pg.title, text: pg.text, idx, len: query.length });
        if (hits.length >= 60) break;
      }
      if (hits.length >= 60) break;
    }
    const box = $('#search-results');
    box.innerHTML = '';
    if (!hits.length) {
      box.innerHTML = `<div class="search-empty">没有找到「${escapeHtml(query)}」</div>`;
      box.classList.remove('hidden');
      return;
    }
    hits.slice(0, 40).forEach((hit) => {
      const btn = el('button', 'search-hit');
      btn.type = 'button';
      btn.append(el('div', 'hit-loc', `${hit.ch} · p${hit.page}${hit.title ? ' · ' + hit.title : ''}`));
      const text = el('div', 'hit-text');
      const start = Math.max(0, hit.idx - 26);
      const end = Math.min(hit.text.length, hit.idx + hit.len + 46);
      const before = hit.text.slice(start, hit.idx).replace(/\s+/g, ' ');
      const match = hit.text.slice(hit.idx, hit.idx + hit.len).replace(/\s+/g, ' ');
      const after = hit.text.slice(hit.idx + hit.len, end).replace(/\s+/g, ' ');
      text.innerHTML = (start > 0 ? '…' : '') + escapeHtml(before) +
        '<mark>' + escapeHtml(match) + '</mark>' + escapeHtml(after) + (end < hit.text.length ? '…' : '');
      btn.append(text);
      btn.addEventListener('click', () => {
        hideSearch();
        if (hit.ch !== S.current) switchChapter(hit.ch, { page: hit.page }).then(() => flashPage(hit.page));
        else { gotoPage(hit.page); flashPage(hit.page); }
      });
      box.appendChild(btn);
    });
    box.classList.remove('hidden');
  }

  /* ================= 9. 复制提问 / 导出笔记 ================= */
  function buildAskText() {
    const open = openAnnotations();
    if (!open.length) return null;
    const root = S.root || '';
    const filePath = (name) => (root ? `${root}/data/${name}` : `data/${name}`);
    const imgDir = root ? `${root}/img` : 'img';
    const reviewCmd = root
      ? `python "${root}/scripts/review_workbench.py" --root "${root}"`
      : 'python scripts/review_workbench.py';
    const lines = open.slice(0, 12).map((a) => {
      const quote = (a.quote || '').replace(/\s+/g, ' ').slice(0, 32);
      const question = (a.q || '').replace(/\s+/g, ' ').slice(0, 70);
      return `- ${a.id} · ${a.ch} p${a.page}${quote ? '「' + quote + '」' : ''}：${question}`;
    });
    return [
      `工作台里有 ${open.length} 条待回答批注。请读取 ${filePath('annotations.json')} 中未回答的条目，`,
      `对照 ${imgDir}/<章>/<页>.webp 的页面图确认批注所指内容后作答（可先运行 ${reviewCmd} --crops 生成裁剪图），`,
      `把答案写入 ${filePath('answers.json')}（key 为批注 id，字段 md，支持 $LaTeX$），页面会自动刷新。`,
      '',
      ...lines,
    ].join('\n');
  }

  async function copyAskPrompt() {
    const text = buildAskText();
    if (!text) { toast('没有待回答的批注，先标几条吧'); return; }
    try {
      await navigator.clipboard.writeText(text);
      toast('已复制，粘贴到对话发送');
    } catch (err) {
      const helper = document.createElement('textarea');
      helper.value = text;
      document.body.appendChild(helper);
      helper.select();
      document.execCommand('copy');
      helper.remove();
      toast('已复制');
    }
  }

  function buildExportMarkdown() {
    const order = new Map(S.manifest.chapters.map((c, i) => [c.id, i]));
    const items = S.annotations.slice().sort((a, b) =>
      (order.get(a.ch) - order.get(b.ch)) || (a.page - b.page) || String(a.created).localeCompare(String(b.created)));
    const out = [
      `# ${S.projectTitle || '课件批注工作台'} · 批注笔记`, '',
      `导出时间：${fmtTime(new Date().toISOString())}`,
      `批注 ${items.length} 条，已解答 ${items.filter((a) => S.answers[a.id]).length} 条。`, '',
    ];
    let chapter = null;
    let page = null;
    for (const ann of items) {
      if (ann.ch !== chapter) {
        chapter = ann.ch;
        page = null;
        const meta = S.manifest.chapters.find((c) => c.id === ann.ch);
        out.push('', `## ${ann.ch} ${meta ? meta.title : ''}`, '');
      }
      if (ann.page !== page) {
        page = ann.page;
        const title = S.chapters.get(ann.ch)?.pages[ann.page - 1]?.title;
        out.push('', `### p${ann.page}${title ? ' · ' + title : ''}`, '');
      }
      out.push(`> ${(ann.quote || '').replace(/\n/g, ' ')}`, '');
      out.push(`**问题**（${ann.tag || '不懂'}${ann.resolved ? ' · 已解决' : ''}）：${ann.q}`, '');
      const answer = S.answers[ann.id];
      out.push(answer && answer.md ? `**解答**：\n\n${answer.md}` : '**解答**：待回答', '');
    }
    return out.join('\n');
  }

  function exportNotes() {
    if (!S.annotations.length) { toast('还没有批注可导出'); return; }
    const blob = new Blob([buildExportMarkdown()], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    const d = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    link.href = url;
    const safeTitle = String(S.projectTitle || '课件批注').replace(/[\\/:*?"<>|]/g, '_');
    link.download = `${safeTitle}_批注笔记_${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}.md`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    toast('笔记已导出');
  }

  /* ================= 10. 顶栏 / 缩放 / 快捷键 ================= */
  function bindTopbar() {
    $('#annot-toggle').addEventListener('click', () => toggleAnnotMode());
    $('#ask-copy').addEventListener('click', copyAskPrompt);
    $('#export-notes').addEventListener('click', exportNotes);
    $('#toc-toggle').addEventListener('click', () => {
      document.body.classList.toggle('toc-collapsed');
      requestAnimationFrame(setPw);
    });
    $('#notes-toggle')?.addEventListener('click', () => $('#notes').classList.toggle('open'));
    $('#notes-close')?.addEventListener('click', () => $('#notes').classList.remove('open'));
    $('#notes-filters').addEventListener('click', (ev) => {
      const chip = ev.target.closest('.chip');
      if (!chip) return;
      S.filter = chip.dataset.filter;
      localStorage.setItem('study.filter', S.filter);
      renderNotes();
    });
    $('#scope-current').addEventListener('change', (ev) => {
      S.scopeCurrent = ev.target.checked;
      localStorage.setItem('study.scope', S.scopeCurrent ? '1' : '0');
      renderNotes();
    });
    $('#zoom-in').addEventListener('click', () => setZoom(S.zoomPct + 10));
    $('#zoom-out').addEventListener('click', () => setZoom(S.zoomPct - 10));
    $('#zoom-val').addEventListener('click', () => setZoom(90));
    bindSearch();
  }

  function setZoom(pct) {
    S.zoomPct = clamp(Math.round(pct / 10) * 10, 60, 100);
    localStorage.setItem('study.zoom', String(S.zoomPct));
    applyZoom();
  }
  function applyZoom() {
    const inner = $('#reader-inner');
    if (!inner) return;
    inner.style.width = S.zoomPct + '%';
    const label = $('#zoom-val');
    if (label) label.textContent = S.zoomPct + '%';
    requestAnimationFrame(setPw);
  }

  function bindKeyboard() {
    document.addEventListener('keydown', (ev) => {
      const active = document.activeElement;
      const typing = active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' ||
        active.tagName === 'SELECT' || active.isContentEditable);
      if (ev.altKey && (ev.key === 'a' || ev.key === 'A')) {
        ev.preventDefault();
        toggleAnnotMode();
        return;
      }
      if (ev.key === 'Escape') {
        const pop = $('#annot-popover');
        if (pop && !pop.classList.contains('hidden')) { closePopover(); ev.preventDefault(); return; }
        const results = $('#search-results');
        if (results && !results.classList.contains('hidden')) { hideSearch(); ev.preventDefault(); return; }
        if (S.annotMode) { toggleAnnotMode(false); ev.preventDefault(); return; }
        return;
      }
      if (typing) return;
      if (ev.key === '/') {
        ev.preventDefault();
        const input = $('#search-input');
        input.focus();
        input.select();
        return;
      }
      if (ev.key === 'ArrowLeft') { ev.preventDefault(); gotoPage(Math.max(1, S.currentPage - 1)); }
      if (ev.key === 'ArrowRight') { ev.preventDefault(); gotoPage(Math.min(pageCount(), S.currentPage + 1)); }
    });
  }

  /* 测试与调试入口 */
  window.__STUDY__ = {
    S, gotoPage, switchChapter, pollState, renderNotes, renderAnnotations,
    pageCount, statusOf, openPopover, toggleAnnotMode,
    buildAskText, buildExportMarkdown,
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
