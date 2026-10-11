/* 创建时间: 2026-10-11 20:15:44
 * visual-page-editor · 批注运行时（阶段 1 原型 v2）
 *
 * v2 相对 v1 的改动（依据实测反馈）：
 *   - 引入「大头钉」作为选择会话的可视锚点与开关：单击/拖拽后在该处立钉并展开列表，
 *     再点钉子即收起列表并结束该次选择。列表因此不再只能靠 Esc 关闭、不会长期遮盖页面。
 *   - 列表首项提供「📍 这个位置」/「▭ 这块区域」，使框选既能表达「对区域本身批注」，
 *     也能表达「选区域内的元素」。
 *   - 左下角待批注面板支持折叠。
 *
 * v1 相对 v0 的改动：
 *   - 「选择」与「写批注」解耦，批注面板常驻左下角，撤销浮动编辑器状态机。
 *   - 分层判据由「有无尺寸」改为「是否携带语义信息」。
 *   - 元素类型中文化；定点批注手势改为 Ctrl+单击。
 *
 * 设计约束：
 *   - 不改动宿主页面 DOM（除自身挂载点），非激活状态零交互监听
 *   - 所有 UI 置于 Shadow DOM，避免与宿主页面样式互相污染
 *   - 进入批注模式时建立 DOM 快照，批注作用于快照，退出即时还原
 *   - canvas 像素不被 cloneNode 复制，需显式移植
 */
(function () {
  'use strict';

  if (window.__VPE_LOADED__) { return; }
  window.__VPE_LOADED__ = true;

  var HOTKEY = { alt: true, key: 'a' };
  var STORAGE_KEY = 'vpe::' + location.pathname;

  // 副本生成器（make_annotator.py）注入的页面指纹：源页面 sha256 + 生成器指纹。
  // 副本是独立文件，浏览器无法回溯原始文件，故由生成副本的一侧提供。
  var PAGE_META = (typeof window.__VPE_PAGE__ === 'object' && window.__VPE_PAGE__)
    ? window.__VPE_PAGE__ : null;

  // 页面没有生成器注入的 data-src 时，副本生成器会离线反查元素来源并按
  // CSS 路径喂进来（键与 elementPath() 逐字一致）。
  var INDEX = (typeof window.__VPE_INDEX__ === 'object' && window.__VPE_INDEX__)
    ? window.__VPE_INDEX__ : null;

  function pageFingerprint() {
    var p = { path: location.pathname, title: document.title };
    if (PAGE_META) {
      p.sha256 = PAGE_META.sha256 || null;
      p.bytes = PAGE_META.bytes || null;
      p.sourcePath = PAGE_META.path || null;
      p.annotatedAt = PAGE_META.annotatedAt || null;
      if (PAGE_META['generator-sha256']) {
        p.generator = {
          file: PAGE_META.generator || null,
          sha256: PAGE_META['generator-sha256'],
          bytes: Number(PAGE_META['generator-bytes']) || null
        };
      }
    }
    return p;
  }
  var MAX_SHOWN = 3;
  var MAX_REGION_ITEMS = 40;

  // ---------------------------------------------------------------- 类型标签

  var TAG_LABEL = {
    div: '容器', span: '文本片段', p: '段落', a: '链接', br: '换行', hr: '分隔线',
    h1: '标题', h2: '标题', h3: '标题', h4: '标题', h5: '标题', h6: '标题',
    ul: '列表', ol: '列表', li: '列表项', dl: '定义列表', dt: '术语', dd: '说明',
    table: '表格', thead: '表头', tbody: '表体', tfoot: '表尾',
    tr: '表格行', td: '单元格', th: '表头格', caption: '表标题',
    section: '章节', article: '文章', nav: '导航', aside: '侧栏',
    header: '页眉', footer: '页脚', main: '主体',
    figure: '图表', figcaption: '图注', img: '图片',
    canvas: '画布', svg: '矢量图', g: '图形组', text: '图内文本',
    rect: '矩形', circle: '圆', path: '路径', line: '线段', tspan: '图内文本',
    details: '折叠区', summary: '折叠标题',
    code: '代码', pre: '代码块', kbd: '按键',
    button: '按钮', input: '输入控件', select: '下拉框', option: '选项', label: '标签',
    textarea: '文本域',
    strong: '强调', em: '强调', b: '强调', i: '斜体', u: '下划线',
    small: '小字', sub: '下标', sup: '上标', mark: '标记',
    blockquote: '引用', time: '时间', abbr: '缩写', cite: '出处'
  };

  var STRUCTURAL = {
    html: 1, body: 1, head: 1, main: 1, section: 1, article: 1,
    nav: 1, header: 1, footer: 1, aside: 1, style: 1, script: 1,
    link: 1, meta: 1, template: 1, noscript: 1, form: 1, fieldset: 1
  };

  function tagLabel(tag) { return TAG_LABEL[tag] || tag; }

  // ---------------------------------------------------------------- 状态

  var state = {
    active: false,
    origBody: null,
    snapBody: null,
    scroll: { x: 0, y: 0 },
    annotations: [],
    selected: [],
    listItems: [],
    listIndex: 0,
    renderList: null,
    pin: null,
    region: null,
    listAnchor: null,
    listDragged: false,
    drag: null,
    panelCollapsed: false,
    ghost: false,
    seq: 1
  };

  // ---------------------------------------------------------------- 工具

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text != null) { n.textContent = text; }
    return n;
  }

  // 浮层拖动。面板会压住待批注的元素，能挪开是基本要求：此前只有候选列表可拖，
  // 工具栏与两个面板钉死在边缘，目标元素一旦落在它们下面就没法指认。
  // 定位一律改为 left/top，避免与原来的 right/bottom/translateX 混用。
  function makeDraggable(node, handle, onStart) {
    if (!node || !handle) { return; }
    handle.style.cursor = 'move';
    if (!handle.title) { handle.title = '按住拖动可移动'; }
    handle.addEventListener('mousedown', function (e) {
      if (e.button !== 0) { return; }
      var t = e.target;
      if (t !== handle && t.closest && t.closest('button,select,textarea,input,.btn,.x')) { return; }
      e.stopPropagation(); e.preventDefault();
      var r = node.getBoundingClientRect();
      var sx = e.clientX, sy = e.clientY;
      node.style.transform = 'none';
      node.style.right = 'auto';
      node.style.bottom = 'auto';
      node.style.left = Math.round(r.left) + 'px';
      node.style.top = Math.round(r.top) + 'px';
      if (onStart) { onStart(); }
      function mv(ev) {
        node.style.left = Math.round(r.left + ev.clientX - sx) + 'px';
        node.style.top = Math.round(r.top + ev.clientY - sy) + 'px';
        ev.preventDefault();
      }
      function up() {
        document.removeEventListener('mousemove', mv, true);
        document.removeEventListener('mouseup', up, true);
      }
      document.addEventListener('mousemove', mv, true);
      document.addEventListener('mouseup', up, true);
    });
  }

  function normText(s) { return String(s || '').replace(/\s+/g, ' ').trim(); }

  function isOurNode(node) {
    var p = node, guard = 0;
    while (p && guard++ < 200) {
      if (p === host) { return true; }
      p = p.parentNode || p.host || null;
    }
    return false;
  }

  function visibleRect(node) {
    if (!node || !node.getBoundingClientRect) { return null; }
    var r = node.getBoundingClientRect();
    return (r.width > 0 && r.height > 0) ? r : null;
  }

  function elementPath(node) {
    var parts = [], cur = node, guard = 0;
    while (cur && cur.nodeType === 1 && guard++ < 64) {
      if (cur.id) { parts.unshift('#' + cur.id); break; }
      var tag = cur.tagName.toLowerCase();
      var parent = cur.parentNode;
      if (parent && parent.nodeType === 1) {
        var same = [];
        for (var i = 0; i < parent.children.length; i++) {
          if (parent.children[i].tagName === cur.tagName) { same.push(parent.children[i]); }
        }
        if (same.length > 1) { tag += ':nth-of-type(' + (same.indexOf(cur) + 1) + ')'; }
      }
      parts.unshift(tag);
      cur = cur.parentNode;
    }
    return parts.join(' > ');
  }

  function sectionOf(node) {
    var cur = node, guard = 0;
    while (cur && cur.nodeType === 1 && guard++ < 128) {
      var prev = cur.previousElementSibling;
      while (prev) {
        if (/^H[1-4]$/.test(prev.tagName)) { return normText(prev.textContent); }
        prev = prev.previousElementSibling;
      }
      cur = cur.parentNode;
    }
    return '';
  }

  function classify(node) {
    var r = visibleRect(node);
    if (!r) { return 'hidden'; }
    var tag = node.tagName.toLowerCase();
    var hasId = !!node.id;
    var hasCls = typeof node.className === 'string' && !!node.className.trim();
    if (!hasId && r.width > window.innerWidth * 0.55 && r.height > window.innerHeight * 0.45) {
      return 'other';
    }
    if (hasId || hasCls) { return 'primary'; }
    if (STRUCTURAL[tag]) { return 'other'; }
    for (var i = 0; i < node.childNodes.length; i++) {
      var c = node.childNodes[i];
      if (c.nodeType === 3 && normText(c.nodeValue)) { return 'primary'; }
    }
    return 'other';
  }

  // 元素 -> 源码坐标：生成器只在关键节点上写 data-src，子元素继承最近祖先的
  // 坐标（hop = 相隔层数，0 表示该元素自身带标注）。
  function sourceOf(node) {
    var cur = node, hop = 0;
    while (cur && cur.nodeType === 1 && hop < 16) {
      var s = cur.getAttribute('data-src');
      if (s) {
        return { coord: s, origin: 'data-src', own: hop === 0,
                 from: cur.tagName.toLowerCase(), hop: hop };
      }
      cur = cur.parentElement;
      hop++;
    }
    // 无生成器注入时，回落查离线反查表（按 CSS 路径精确匹配，不做猜测）
    if (INDEX) {
      var hit = INDEX[elementPath(node)];
      if (hit) {
        return { coord: hit.coord, origin: 'index', own: true, hop: 0,
                 confidence: hit.confidence, why: hit.why, kind: hit.kind,
                 lineText: hit.line_text };
      }
    }
    return null;
  }

  function describe(node) {
    var r = visibleRect(node);
    var tag = node.tagName.toLowerCase();
    return {
      tag: tag,
      label: tagLabel(tag),
      idAttr: node.id || null,
      cls: (typeof node.className === 'string' && node.className)
        ? node.className.trim().split(/\s+/).slice(0, 2).join(' ') : '',
      text: normText(node.textContent).slice(0, 60),
      cssPath: elementPath(node),
      src: sourceOf(node),
      w: r ? Math.round(r.width) : 0,
      h: r ? Math.round(r.height) : 0
    };
  }

  function pseudo(text, label) {
    return { tag: '', label: label, idAttr: null, cls: '', text: text,
             cssPath: null, src: null, w: 0, h: 0 };
  }

  // ---------------------------------------------------------------- Shadow

  var host = document.createElement('div');
  host.id = '__vpe_host';
  host.style.cssText = 'all: initial; position: fixed; inset: 0; z-index: 2147483000; ' +
    'pointer-events: none;';

  var shadow = host.attachShadow({ mode: 'open' });

  var style = document.createElement('style');
  style.textContent = [
    '*{box-sizing:border-box}',
    '.ui{position:fixed;font:13px/1.55 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;',
    '  color:#e8eaed;background:#1f2430;border:1px solid #3a4152;border-radius:10px;',
    '  box-shadow:0 8px 28px rgba(0,0,0,.45);pointer-events:auto}',
    '.btn{display:inline-flex;align-items:center;gap:6px;padding:7px 12px;border:0;',
    '  background:#2b3242;color:#e8eaed;font:inherit;cursor:pointer;border-radius:7px}',
    '.btn:hover{background:#39415a}',
    '.btn.pri{background:#3b6ea5}.btn.pri:hover{background:#4a83c0}',
    '.btn.sm{padding:4px 9px;font-size:12px}',
    '.fab{position:fixed;right:18px;bottom:18px;pointer-events:auto}',
    '.fab .btn{padding:10px 16px;border-radius:22px;box-shadow:0 6px 20px rgba(0,0,0,.4)}',
    '.bar{position:fixed;left:50%;transform:translateX(-50%);bottom:18px;display:flex;',
    '  gap:8px;padding:8px;align-items:center;z-index:6}',
    '.sep{width:1px;height:22px;background:#3a4152}',
    '.badge{background:#3b6ea5;border-radius:10px;padding:1px 7px;font-size:11px}',
    '.hint{color:#8b94a6;font-size:12px}',
    '.list{position:fixed;width:400px;max-height:352px;overflow:auto;z-index:8}',
    '.hd{padding:8px 12px;background:#252b39;border-bottom:1px solid #3a4152;',
    '  font-size:12px;color:#9aa3b5;display:flex;justify-content:space-between;gap:10px}',
    '.row{display:flex;align-items:center;gap:8px;padding:7px 11px;cursor:pointer;',
    '  border-bottom:1px solid #2a3140}',
    '.row:last-child{border-bottom:0}',
    '.row:hover{background:#2f394d}',
    '.row.on{background:#2c4460}',
    '.lb{flex:none;background:#39415a;border-radius:5px;padding:1px 6px;font-size:11px;',
    '  color:#cbd5e5}',
    '.row.on .lb{background:#3b6ea5;color:#fff}',
    '.ck{flex:none;width:14px;text-align:center;color:#6b7484;font-size:12px}',
    '.row.on .ck{color:#7fd6a0}',
    '.tg{color:#6b7484;font-family:Consolas,monospace;font-size:11px;flex:none}',
    '.idc{color:#e0b872;font-family:Consolas,monospace;font-size:12px;flex:none}',
    '.tx{color:#9aa3b5;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}',
    '.sz{color:#6b7484;font-size:11px;flex:none}',
    '.more{padding:7px 11px;cursor:pointer;color:#7fb3e8;background:#232936}',
    '.more:hover{background:#2b3242}',
    '.panel{position:fixed;left:18px;bottom:18px;width:350px;display:flex;',
    '  flex-direction:column;z-index:7;max-height:62vh}',
    '.ph{padding:9px 12px;background:#252b39;border-bottom:1px solid #3a4152;',
    '  display:flex;justify-content:space-between;align-items:center;gap:8px}',
    '.ph .sp{flex:1}',
    '.sel{max-height:150px;overflow:auto;border-bottom:1px solid #3a4152}',
    '.pb{padding:10px}',
    '.srow{display:flex;align-items:center;gap:8px;padding:6px 12px;cursor:pointer;',
    '  border-bottom:1px solid #232936}',
    '.srow:last-child{border-bottom:0}',
    '.srow:hover{background:#2a3140}',
    '.srow .x{color:#e08a8a;flex:none;font-size:12px}',
    '.srow .tx{flex:1}',
    '.none{color:#6b7484;padding:11px 12px;font-size:12px}',
    'textarea{width:100%;height:76px;resize:vertical;background:#1b202b;',
    '  color:#e8eaed;border:1px solid #3a4152;border-radius:7px;padding:8px;font:inherit}',
    '.r2{display:flex;gap:7px;margin-top:7px;align-items:center}',
    '.r2 select{flex:1;background:#1b202b;color:#e8eaed;border:1px solid #3a4152;',
    '  border-radius:7px;padding:6px;font:inherit}',
    '.hl{position:fixed;pointer-events:none;border:2px solid #4da3ff;',
    '  background:rgba(77,163,255,.14);border-radius:3px;z-index:1}',
    '.hl.hov{border-color:#ffc14d;background:rgba(255,193,77,.16)}',
    '.hl.sel{border-color:#4dff9e;background:rgba(77,255,158,.14)}',
    '.pin{position:fixed;pointer-events:auto;cursor:pointer;z-index:9;',
    '  font-size:24px;line-height:1;font-family:"Segoe UI Emoji","Segoe UI",sans-serif;',
    '  transform:translate(-50%,-95%);filter:drop-shadow(0 2px 3px rgba(0,0,0,.55));',
    '  user-select:none;-webkit-user-select:none}',
    '.pin:hover{filter:drop-shadow(0 0 7px rgba(130,195,255,.95))}',
    '.region{position:fixed;pointer-events:none;border:2px dashed #4da3ff;',
    '  background:rgba(77,163,255,.10);border-radius:3px;z-index:1}',
    '.mark{position:fixed;pointer-events:auto;cursor:pointer;background:#ff7a45;color:#fff;',
    '  border-radius:9px;font-size:11px;padding:1px 6px;border:1px solid #fff;z-index:3;',
    '  font-family:Consolas,monospace}',
    '.toast{position:fixed;left:50%;transform:translateX(-50%);top:20px;background:#2b3242;',
    '  border:1px solid #3a4152;border-radius:8px;padding:8px 15px;z-index:20;text-align:center}',
    '.grip{cursor:move;color:#6b7484;padding:0 3px;user-select:none;-webkit-user-select:none}',
    '.ghost-back{position:fixed;right:18px;bottom:18px;z-index:30;pointer-events:auto;',
    '  box-shadow:0 6px 20px rgba(0,0,0,.4)}'
  ].join('\n');
  shadow.appendChild(style);
  document.documentElement.appendChild(host);

  function toast(msg) {
    var t = el('div', 'ui toast', msg);
    shadow.appendChild(t);
    setTimeout(function () { if (t.parentNode) { t.remove(); } }, 2400);
  }

  // ---------------------------------------------------------------- 高亮

  var hlBox = el('div', 'hl');
  hlBox.style.display = 'none';
  shadow.appendChild(hlBox);

  var hlTarget = null;
  var hlCls = '';

  // 按目标元素当前位置重绘高亮框；滚动后必须重调，否则框会停在原处
  function paintHighlight() {
    if (!hlTarget) { hlBox.style.display = 'none'; return; }
    var r = visibleRect(hlTarget);
    if (!r) { hlBox.style.display = 'none'; return; }
    hlBox.className = 'hl' + (hlCls ? ' ' + hlCls : '');
    hlBox.style.cssText = 'display:block;left:' + r.left + 'px;top:' + r.top + 'px;' +
      'width:' + r.width + 'px;height:' + r.height + 'px';
  }

  function highlight(node, cls) {
    hlTarget = node;
    hlCls = cls || '';
    paintHighlight();
  }

  function clearHighlight() {
    hlTarget = null;
    hlCls = '';
    hlBox.style.display = 'none';
  }

  // ---------------------------------------------------------------- 大头钉

  var pinEl = null;

  var PIN_GLYPH = '\uD83D\uDCCD';   // 📍 round pushpin：垂直字形，针尖位于正下方

  function showPin(x, y) {
    removePin();
    state.pin = { dx: Math.round(x + window.scrollX), dy: Math.round(y + window.scrollY) };
    pinEl = el('div', 'pin', PIN_GLYPH);
    pinEl.title = '点击收起此处的选择';
    pinEl.addEventListener('click', function (e) {
      e.stopPropagation();
      removePin();
      removeRegion();
      closeList();
    });
    shadow.appendChild(pinEl);
    placePin();
  }

  // 图钉按文档坐标存放，滚动时重算视口位置，保持贴合原内容
  function placePin() {
    if (!pinEl || !state.pin) { return; }
    pinEl.style.left = Math.round(state.pin.dx - window.scrollX) + 'px';
    pinEl.style.top = Math.round(state.pin.dy - window.scrollY) + 'px';
  }

  function removePin() {
    state.pin = null;
    if (pinEl) { pinEl.remove(); pinEl = null; }
  }

  // 框选范围预览，与图钉同生命周期、同滚动行为
  var regionEl = null;

  function showRegion(l, t, w, h) {
    removeRegion();
    state.region = {
      dx: Math.round(l + window.scrollX), dy: Math.round(t + window.scrollY),
      w: Math.round(w), h: Math.round(h)
    };
    regionEl = el('div', 'region');
    shadow.appendChild(regionEl);
    placeRegion();
  }

  function placeRegion() {
    if (!regionEl || !state.region) { return; }
    regionEl.style.left = Math.round(state.region.dx - window.scrollX) + 'px';
    regionEl.style.top = Math.round(state.region.dy - window.scrollY) + 'px';
    regionEl.style.width = state.region.w + 'px';
    regionEl.style.height = state.region.h + 'px';
  }

  function removeRegion() {
    state.region = null;
    if (regionEl) { regionEl.remove(); regionEl = null; }
  }

  // ---------------------------------------------------------------- 批注标记

  var pinLayer = el('div');
  pinLayer.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2';
  shadow.appendChild(pinLayer);

  function anchorRect(ann) {
    if (ann._node) { return visibleRect(ann._node); }
    var a = ann.anchor;
    if (!a || !a.docPx) { return null; }
    return {
      left: a.docPx.x - window.scrollX,
      top: a.docPx.y - window.scrollY,
      width: (a.rect && a.rect.w) || 0,
      height: (a.rect && a.rect.h) || 0
    };
  }

  function pinAnnotation(ann) {
    if (!ann._rect) { return; }
    var r = ann._rect;
    var m = el('div', 'mark', ann.id);
    m.style.left = Math.round(r.left + Math.max(r.width, 12) - 8) + 'px';
    m.style.top = Math.round(r.top - 10) + 'px';
    m.title = ann.comment;
    m.addEventListener('click', function () { openPanel_(); });
    m.addEventListener('mouseenter', function () { if (ann._node) { highlight(ann._node, 'sel'); } });
    m.addEventListener('mouseleave', clearHighlight);
    pinLayer.appendChild(m);
  }

  function resolveNodes(root) {
    state.annotations.forEach(function (ann) {
      ann._node = null; ann._rect = null;
      var p = ann.targets && ann.targets[0] && ann.targets[0].cssPath;
      if (!p) { return; }
      try {
        var n = root.querySelector(p);
        if (n && !isOurNode(n)) { ann._node = n; }
      } catch (e) { /* 无效选择器 */ }
    });
  }

  function repin() {
    while (pinLayer.firstChild) { pinLayer.removeChild(pinLayer.firstChild); }
    state.annotations.forEach(function (ann) {
      ann._rect = anchorRect(ann);
      if (ann._rect) { pinAnnotation(ann); }
    });
  }

  // 浮动 UI 的滚动同步：事件监听为主，定时轮询兜底。
  // 真实环境里 scroll 事件的送达时机与目标因浏览器而异，轮询保证位置最终一致。
  var lastSx = window.scrollX;
  var lastSy = window.scrollY;

  function syncFloating() {
    if (!state.active) { return; }
    repin();
    placePin();
    placeRegion();
    placeList();
    paintHighlight();
  }

  function pollScroll() {
    if (!state.active) {
      lastSx = window.scrollX;
      lastSy = window.scrollY;
      return;
    }
    if (window.scrollX !== lastSx || window.scrollY !== lastSy) {
      lastSx = window.scrollX;
      lastSy = window.scrollY;
      syncFloating();
    }
  }

  window.addEventListener('scroll', syncFloating, true);
  document.addEventListener('scroll', syncFloating, true);
  setInterval(pollScroll, 50);
  window.addEventListener('resize', function () { if (state.active) { repin(); } });

  // ---------------------------------------------------------------- 让路

  // 面板压住待批注元素时，逐个挪开太慢；让路把全部浮层变淡并放行鼠标事件，
  // 只保留右下角一个恢复入口，点击于是穿透到页面，被盖住的元素也能选中。
  var ghostBtn = el('button', 'btn pri ghost-back', '\u21A9 恢复浮层');
  ghostBtn.title = '恢复浮层（快捷键 `）';

  function ghostTargets() {
    return [bar, panelEl, panel, listBox].filter(Boolean);
  }

  function ghostApply(n) {
    if (!n) { return; }
    n.style.opacity = state.ghost ? '0.1' : '';
    n.style.pointerEvents = state.ghost ? 'none' : '';
  }

  function setGhost(on) {
    state.ghost = !!on;
    ghostTargets().forEach(ghostApply);
    if (state.ghost) {
      if (ghostBtn.parentNode !== ui) { ui.appendChild(ghostBtn); }
    } else if (ghostBtn.parentNode) {
      ghostBtn.remove();
    }
    if (bGhost) { bGhost.textContent = state.ghost ? '恢复浮层' : '让路'; }
  }

  ghostBtn.addEventListener('click', function () { setGhost(false); });

  // ---------------------------------------------------------------- 入口与工具栏

  var fab = el('div', 'fab');
  var fabBtn = el('button', 'btn pri', '✎ 批注');
  fab.appendChild(fabBtn);

  var bar = el('div', 'ui bar');
  var grip = el('span', 'grip', '\u283F');
  var bExpand = el('button', 'btn', '全部展开');
  var bCount = el('span', 'badge', '0');
  var bList = el('button', 'btn', '批注列表');
  var bExport = el('button', 'btn', '导出 JSON');
  var bGhost = el('button', 'btn', '让路');
  var bExit = el('button', 'btn', '退出');

  bGhost.title = '把浮层变淡并放行鼠标：点击会落到页面元素上（快捷键 `）';

  bar.appendChild(grip);
  bar.appendChild(el('span', 'hint', 'v0.1.0-p9'));
  bar.appendChild(el('div', 'sep'));
  bar.appendChild(el('span', 'hint', '单击选元素 · Ctrl+单击定点 · Shift+拖拽框选'));
  bar.appendChild(el('div', 'sep'));
  bar.appendChild(bExpand);
  bar.appendChild(el('div', 'sep'));
  bar.appendChild(bList);
  bar.appendChild(bCount);
  bar.appendChild(bExport);
  bar.appendChild(el('div', 'sep'));
  bar.appendChild(bGhost);
  bar.appendChild(bExit);

  // ---------------------------------------------------------------- 待批注面板

  var panelEl = null;
  var taRef = null;
  var selRef = null;

  function buildPanel() {
    panelEl = el('div', 'ui panel');

    var ph = el('div', 'ph');
    var t = el('span', null, '待批注');
    t.id = 'vpe-panel-title';
    ph.appendChild(t);
    var sp = el('span', 'sp');
    ph.appendChild(sp);

    var bFold = el('button', 'btn sm', '收起');
    bFold.id = 'vpe-fold';
    bFold.addEventListener('click', function () {
      state.panelCollapsed = !state.panelCollapsed;
      applyFold();
    });
    ph.appendChild(bFold);

    var clr = el('button', 'btn sm', '全部清除');
    clr.id = 'vpe-clear';
    clr.addEventListener('click', function () {
      state.selected = [];
      renderPanel_(); refreshCount();
      if (state.renderList) { state.renderList(); }
    });
    ph.appendChild(clr);
    panelEl.appendChild(ph);

    selRef = el('div', 'sel');
    panelEl.appendChild(selRef);

    var pb = el('div', 'pb');
    taRef = document.createElement('textarea');
    taRef.placeholder = '写下你的修改意见…';
    pb.appendChild(taRef);

    var r2 = el('div', 'r2');
    var sel = document.createElement('select');
    [['change-text', '改文字'], ['change-style', '改样式'], ['change-data', '数值/来源不对'],
     ['add', '这里要加东西'], ['remove', '删掉'], ['question', '不确定，想问你']
    ].forEach(function (o) {
      var op = document.createElement('option');
      op.value = o[0]; op.textContent = o[1];
      sel.appendChild(op);
    });
    r2.appendChild(sel);
    var bSub = el('button', 'btn pri', '提交批注');
    r2.appendChild(bSub);
    pb.appendChild(r2);
    panelEl.appendChild(pb);

    bSub.addEventListener('click', function () {
      var text = taRef.value.trim();
      if (!text) { toast('批注内容为空'); taRef.focus(); return; }
      if (!state.selected.length) { toast('还没有选中任何元素'); return; }
      commit(text, sel.value);
      taRef.value = '';
    });

    shadow.appendChild(panelEl);
    makeDraggable(panelEl, ph);
    ghostApply(panelEl);
    applyFold();
    renderPanel_();
  }

  function applyFold() {
    if (!panelEl) { return; }
    var fold = state.panelCollapsed;
    panelEl.querySelector('.sel').style.display = fold ? 'none' : '';
    panelEl.querySelector('.pb').style.display = fold ? 'none' : '';
    // 收起时缩为小胶囊，避免压住底部工具栏左侧的版本号
    panelEl.style.width = fold ? 'auto' : '350px';
    var clr = panelEl.querySelector('#vpe-clear');
    if (clr) { clr.style.display = fold ? 'none' : ''; }
    var b = panelEl.querySelector('#vpe-fold');
    if (b) { b.textContent = fold ? '展开' : '收起'; }
  }

  function clearPanel() { if (panelEl) { panelEl.remove(); panelEl = null; } }

  function selectedKey(item) {
    if (item.kind === 'element') { return 'e:' + elementPath(item.node); }
    var a = item.anchor || {};
    return item.kind + ':' + (a.docPx ? a.docPx.x + ',' + a.docPx.y : '') +
      ':' + (a.rect ? a.rect.w + 'x' + a.rect.h : '');
  }

  function isSelected(item) {
    var k = selectedKey(item);
    for (var i = 0; i < state.selected.length; i++) {
      if (selectedKey(state.selected[i]) === k) { return true; }
    }
    return false;
  }

  function toggleSelected(item) {
    var k = selectedKey(item);
    var idx = -1;
    for (var j = 0; j < state.selected.length; j++) {
      if (selectedKey(state.selected[j]) === k) { idx = j; break; }
    }
    if (idx >= 0) { state.selected.splice(idx, 1); }
    else { state.selected.push(item); }
    renderPanel_();
    refreshCount();
    if (state.renderList) { state.renderList(); }
  }

  function renderPanel_() {
    if (!panelEl) { return; }
    var box = selRef;
    while (box.firstChild) { box.removeChild(box.firstChild); }

    var title = panelEl.querySelector('#vpe-panel-title');
    title.textContent = state.selected.length
      ? '待批注 ' + state.selected.length + ' 项' : '待批注';

    if (!state.selected.length) {
      box.appendChild(el('div', 'none', '单击页面元素加入待批注列表'));
      return;
    }
    state.selected.slice(0, MAX_SHOWN).forEach(function (s) {
      var row = el('div', 'srow');
      row.appendChild(el('span', 'lb', s.d.label));
      if (s.d.tag) { row.appendChild(el('span', 'tg', s.d.tag)); }
      if (s.d.idAttr) { row.appendChild(el('span', 'idc', '#' + s.d.idAttr)); }
      row.appendChild(el('span', 'tx', s.d.text || ''));
      var x = el('span', 'x', '✕');
      x.title = '移出';
      x.addEventListener('click', function (e) {
        e.stopPropagation();
        state.selected = state.selected.filter(function (z) { return z !== s; });
        renderPanel_(); refreshCount();
        if (state.renderList) { state.renderList(); }
      });
      row.appendChild(x);
      row.addEventListener('mouseenter', function () { if (s.node) { highlight(s.node, 'sel'); } });
      row.addEventListener('mouseleave', clearHighlight);
      box.appendChild(row);
    });
    if (state.selected.length > MAX_SHOWN) {
      box.appendChild(el('div', 'none',
        '…及其他 ' + (state.selected.length - MAX_SHOWN) + ' 个元素'));
    }
  }

  function commit(comment, intent) {
    var items = state.selected.slice();
    var first = items[0];
    var kind = 'elements';
    if (items.length === 1 && first.kind !== 'element') { kind = first.kind; }

    var ann = {
      id: 'a' + (state.seq++),
      kind: kind,
      intent: intent,
      comment: comment,
      createdAt: new Date().toISOString(),
      targets: items.map(function (s, i) {
        var rr = s.node ? visibleRect(s.node) : null;
        return {
          role: i === 0 ? 'anchor' : 'member',
          kind: s.kind,
          label: s.d.label,
          tag: s.d.tag,
          idAttr: s.d.idAttr || null,
          cls: s.d.cls || '',
          text: s.d.text || '',
          cssPath: s.d.cssPath || null,
          src: s.d.src || null,
          section: s.node ? (sectionOf(s.node) || null) : null,
          rect: rr ? { w: Math.round(rr.width), h: Math.round(rr.height) } : null
        };
      })
    };
    if (first.anchor) { ann.anchor = first.anchor; }

    state.annotations.push(ann);
    ann._node = first.node || null;
    ann._rect = anchorRect(ann);

    state.selected = [];
    persist();
    renderPanel_();
    refreshCount();
    renderPanel();
    if (state.renderList) { state.renderList(); }
    repin();

    toast('已保存 ' + ann.id + '（共 ' + state.annotations.length + ' 条）');
  }

  function refreshCount() {
    bCount.textContent = String(state.annotations.length + state.selected.length);
    bCount.title = '已保存 ' + state.annotations.length + ' 条 · 待批注 ' + state.selected.length + ' 项';
  }

  // ---------------------------------------------------------------- 选择列表

  var listBox = null;

  function closeList() {
    if (listBox) { listBox.remove(); listBox = null; }
    state.listItems = [];
    state.listIndex = 0;
    state.renderList = null;
    state.listAnchor = null;
    state.listDragged = false;
    clearHighlight();
  }

  // items 按 tier 排列：head（位置/区域伪项）→ primary（元素）→ other（元素）
  function buildList(items, px, py) {
    closeList();
    if (!items.length) { return; }

    state.listItems = items;
    listBox = el('div', 'ui list');

    var nOther = 0;
    for (var q = 0; q < items.length; q++) {
      if (items[q].tier === 'other') { nOther++; }
    }
    var visibleCount = items.length - nOther;
    var collapsed = nOther > 0;

    var hd = el('div', 'hd');
    hd.title = '按住拖动可移动列表';
    hd.appendChild(el('span', null, items.length + ' 个可批注目标'));
    hd.appendChild(el('span', null, '拖动此栏移动 · 点钉子收起'));
    listBox.appendChild(hd);

    // 拖动标题栏移动列表，避开被遮挡的元素；拖过之后不再自动跟随滚动
    makeDraggable(listBox, hd, function () { state.listDragged = true; });

    function renderRows() {
      while (listBox.children.length > 1) { listBox.removeChild(listBox.lastChild); }
      items.forEach(function (it, i) {
        if (it.tier === 'other' && collapsed) { return; }
        var on = isSelected(it);
        var row = el('div', 'row' + (on ? ' on' : ''));
        row.dataset.i = String(i);

        row.appendChild(el('span', 'ck', on ? '✓' : '○'));
        row.appendChild(el('span', 'lb', it.d.label));
        if (it.d.tag) { row.appendChild(el('span', 'tg', it.d.tag)); }
        if (it.d.idAttr) { row.appendChild(el('span', 'idc', '#' + it.d.idAttr)); }
        row.appendChild(el('span', 'tx', it.d.text || ''));
        if (it.d.w || it.d.h) {
          row.appendChild(el('span', 'sz', it.d.w + '×' + it.d.h));
        }

        row.addEventListener('mouseenter', function () {
          state.listIndex = i;
          if (it.node) { highlight(it.node, 'hov'); }
        });
        row.addEventListener('click', function (e) {
          e.stopPropagation();
          toggleSelected(it);
          renderRows();
        });
        listBox.appendChild(row);
      });

      if (collapsed) {
        var more = el('div', 'more', '▸ 其他 (' + nOther + ')');
        more.addEventListener('click', function (e) {
          e.stopPropagation();
          collapsed = false;
          renderRows();
        });
        listBox.appendChild(more);
      }
    }

    state.renderList = renderRows;
    renderRows();
    state.listIndex = 0;
    if (items[0] && items[0].node) { highlight(items[0].node, 'hov'); }

    state.listAnchor = { dx: px + window.scrollX, dy: py + window.scrollY };
    state.listDragged = false;
    shadow.appendChild(listBox);
    ghostApply(listBox);
    placeList();
  }

  // 列表按锚点的文档坐标定位；用户手动拖过之后不再自动跟随滚动。
  // 不做垂直钳制：用视口高度把列表钉在边缘会让它在滚动后偏离锚点（指向错误位置），
  // 与图钉、高亮框的位移对不上。锚点移出视口时列表跟着出去，拖拽仍可把它拉回来。
  function placeList() {
    if (!listBox || !state.listAnchor || state.listDragged) { return; }
    var px = state.listAnchor.dx - window.scrollX;
    var py = state.listAnchor.dy - window.scrollY;
    // 从钉子右侧展开，避免压住钉子本身；右侧放不下时翻到左侧（仍相对锚点）
    var w = listBox.offsetWidth || 410;
    var lx = px + 22;
    if (lx + w > window.innerWidth) { lx = Math.max(8, px - w); }
    listBox.style.left = Math.round(lx) + 'px';
    listBox.style.top = Math.round(py) + 'px';
  }

  function moveList(delta) {
    var n = state.listItems.length;
    if (!n) { return; }
    state.listIndex = (state.listIndex + delta + n) % n;
    var it = state.listItems[state.listIndex];
    if (it.node) { highlight(it.node, 'hov'); }
    var row = listBox && listBox.querySelector('.row[data-i="' + state.listIndex + '"]');
    if (row) { row.scrollIntoView({ block: 'nearest' }); }
  }

  // ---------------------------------------------------------------- 批注列表面板

  var panel = null;

  function openPanel_() {
    if (panel) { closePanel(); return; }
    panel = el('div', 'ui panel');
    panel.style.left = 'auto';
    panel.style.right = '18px';
    panel.style.width = '340px';
    panel.style.maxHeight = '70vh';

    var ph = el('div', 'ph');
    ph.title = '按住拖动可移动';
    ph.appendChild(el('span', null, '批注列表'));
    var sp = el('span', 'sp');
    ph.appendChild(sp);
    var x = el('span', 'x', '✕');
    x.addEventListener('click', closePanel);
    ph.appendChild(x);
    panel.appendChild(ph);

    var bd = el('div', 'sel');
    bd.style.maxHeight = 'none';
    bd.style.flex = '1';
    panel.appendChild(bd);
    shadow.appendChild(panel);
    makeDraggable(panel, ph);
    ghostApply(panel);
    renderPanel();
  }

  function closePanel() { if (panel) { panel.remove(); panel = null; } }

  function renderPanel() {
    if (!panel) { return; }
    var bd = panel.querySelector('.sel');
    while (bd.firstChild) { bd.removeChild(bd.firstChild); }

    if (!state.annotations.length) {
      bd.appendChild(el('div', 'none', '还没有批注'));
      return;
    }
    state.annotations.forEach(function (ann) {
      var it = el('div', 'srow');
      it.style.display = 'block';
      var m = el('div', 'hint');
      m.textContent = ann.id + ' · ' + ann.kind + ' · ' + ann.intent;
      var del = el('span', 'x', '删除');
      del.style.float = 'right';
      del.style.cursor = 'pointer';
      del.addEventListener('click', function () {
        state.annotations = state.annotations.filter(function (a) { return a !== ann; });
        persist(); refreshCount(); renderPanel(); repin();
      });
      m.appendChild(del);
      it.appendChild(m);
      var c = el('div');
      c.style.whiteSpace = 'pre-wrap';
      c.style.marginTop = '4px';
      c.textContent = ann.comment;
      it.appendChild(c);
      ann.targets.forEach(function (t) {
        var line = el('div', 'hint');
        line.style.fontFamily = 'Consolas,monospace';
        line.textContent = t.role + ' · ' + (t.label || t.tag) +
          (t.idAttr ? '#' + t.idAttr : '') + (t.text ? ' 「' + t.text + '」' : '');
        it.appendChild(line);
      });
      bd.appendChild(it);
    });
  }

  // ---------------------------------------------------------------- 持久化

  function plain() {
    return state.annotations.map(function (a) {
      return {
        id: a.id, kind: a.kind, intent: a.intent, comment: a.comment,
        createdAt: a.createdAt, targets: a.targets, anchor: a.anchor
      };
    });
  }

  function persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        schema: 'page-annotations/v1-proto',
        page: pageFingerprint(),
        savedAt: new Date().toISOString(),
        annotations: plain()
      }));
    } catch (e) { /* 静默 */ }
  }

  function restore() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) { return; }
      var d = JSON.parse(raw);
      if (!d || !Array.isArray(d.annotations)) { return; }
      state.annotations = d.annotations;
      state.seq = state.annotations.length + 1;
      resolveNodes(document.body);
    } catch (e) { /* ignore */ }
  }

  function exportJSON() {
    var page = pageFingerprint();
    page.exportedAt = new Date().toISOString();
    var payload = {
      schema: 'page-annotations/v1-proto',
      page: page,
      annotations: plain()
    };
    var text = JSON.stringify(payload, null, 2);
    var ok = false;
    try {
      var blob = new Blob([text], { type: 'application/json' });
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'annotations.json';
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 4000);
      ok = true;
    } catch (e) { ok = false; }
    if (!ok) {
      try { navigator.clipboard.writeText(text); toast('已复制到剪贴板'); return; }
      catch (e2) { /* fallthrough */ }
    }
    toast('已导出 ' + state.annotations.length + ' 条批注');
  }

  // ---------------------------------------------------------------- 快照

  function transplantCanvases(srcRoot, dstRoot) {
    var a = srcRoot.querySelectorAll('canvas');
    var b = dstRoot.querySelectorAll('canvas');
    var n = Math.min(a.length, b.length), done = 0;
    for (var i = 0; i < n; i++) {
      try {
        var ctx = b[i].getContext('2d');
        if (ctx) { ctx.drawImage(a[i], 0, 0); done++; }
      } catch (e) { /* 跳过 */ }
    }
    return { total: n, transplanted: done };
  }

  function enterSnapshot() {
    var orig = document.body;
    var snap = orig.cloneNode(true);
    var stat = transplantCanvases(orig, snap);
    // cloneNode 不复制事件监听：快照内的表单控件一律失效（值还在，拖动无反应），
    // 因此在这里点清数量，进入时如实告知，避免用户以为页面坏了
    stat.controls = snap.querySelectorAll('input, select, textarea, button').length;
    // disabled 控件在浏览器的命中测试阶段就被丢弃，连 mousedown 都不派发，
    // 表现为「点不动」而不是「点到了没反应」——空态页面往往大面积命中。
    // 只在克隆体上解除，原页面不受影响。
    var dis = snap.querySelectorAll(
      'input[disabled], select[disabled], textarea[disabled], button[disabled]');
    stat.disabled = dis.length;
    Array.prototype.forEach.call(dis, function (n) { n.disabled = false; });
    state.scroll = { x: window.scrollX, y: window.scrollY };
    state.origBody = orig;
    state.snapBody = snap;
    orig.parentNode.replaceChild(snap, orig);
    window.scrollTo(state.scroll.x, state.scroll.y);
    resolveNodes(snap);
    return stat;
  }

  function exitSnapshot() {
    if (state.origBody && state.snapBody && state.snapBody.parentNode) {
      state.snapBody.parentNode.replaceChild(state.origBody, state.snapBody);
      window.scrollTo(state.scroll.x, state.scroll.y);
      resolveNodes(state.origBody);
    }
    state.origBody = null;
    state.snapBody = null;
  }

  // ---------------------------------------------------------------- 事件

  function fromHost(e) {
    if (e.composedPath) {
      var p = e.composedPath();
      for (var i = 0; i < p.length; i++) { if (p[i] === host) { return true; } }
      return false;
    }
    return isOurNode(e.target);
  }

  var BLOCKED = ['mousedown', 'mouseup', 'click', 'dblclick', 'contextmenu',
                 'selectstart', 'dragstart', 'submit', 'change', 'input', 'keypress'];

  function blocker(e) {
    if (fromHost(e)) { return; }
    e.stopPropagation();
    if (e.cancelable) { e.preventDefault(); }
  }

  function onKeyDown(e) {
    if (fromHost(e)) { return; }
    if (e.key === 'Escape') {
      if (listBox) { closeList(); removePin(); removeRegion(); }
      else if (state.drag) { state.drag = null; clearHighlight(); }
      else { exitMode(); }
      e.stopPropagation(); e.preventDefault();
      return;
    }
    if (e.key === '`' || e.key === '~') {
      setGhost(!state.ghost);
      e.stopPropagation(); e.preventDefault();
      return;
    }
    if (listBox) {
      if (e.key === 'ArrowDown') { moveList(1); e.stopPropagation(); e.preventDefault(); return; }
      if (e.key === 'ArrowUp') { moveList(-1); e.stopPropagation(); e.preventDefault(); return; }
    }
  }

  function onMouseDown(e) {
    if (fromHost(e)) { return; }
    if (e.ctrlKey || e.shiftKey || e.button === 1) {
      if (state.pin) { removePin(); removeRegion(); closeList(); }
      state.drag = { x0: e.clientX, y0: e.clientY, x1: e.clientX, y1: e.clientY, shift: e.shiftKey };
      e.stopPropagation(); e.preventDefault();
    }
  }

  function onMouseMove(e) {
    if (!state.drag) { return; }
    state.drag.x1 = e.clientX;
    state.drag.y1 = e.clientY;
    var d = state.drag;
    hlBox.className = 'hl';
    hlBox.style.cssText = 'display:block;left:' + Math.min(d.x0, d.x1) + 'px;top:' +
      Math.min(d.y0, d.y1) + 'px;width:' + Math.abs(d.x1 - d.x0) + 'px;height:' +
      Math.abs(d.y1 - d.y0) + 'px';
    e.stopPropagation(); e.preventDefault();
  }

  function pointAnchor(x, y) {
    var nodes = document.elementsFromPoint ? document.elementsFromPoint(x, y) : [];
    var ref = null;
    for (var i = 0; i < nodes.length; i++) {
      if (!isOurNode(nodes[i]) && nodes[i].id) { ref = nodes[i]; break; }
    }
    if (!ref) {
      for (var j = 0; j < nodes.length; j++) {
        if (!isOurNode(nodes[j])) { ref = nodes[j]; break; }
      }
    }
    var r = ref ? visibleRect(ref) : null;
    var docW = Math.max(1, document.documentElement.scrollWidth);
    var docH = Math.max(1, document.documentElement.scrollHeight);
    var ax = window.scrollX + x, ay = window.scrollY + y;
    return {
      mode: 'point',
      nodeRef: ref,
      docPx: { x: Math.round(ax), y: Math.round(ay) },
      docPct: { x: +(ax / docW * 100).toFixed(2), y: +(ay / docH * 100).toFixed(2) },
      viewport: { w: window.innerWidth, h: window.innerHeight },
      nearest: ref ? { tag: ref.tagName.toLowerCase(), idAttr: ref.id || null, cssPath: elementPath(ref) } : null,
      offsetPct: r ? {
        x: +((x - r.left) / Math.max(1, r.width) * 100).toFixed(2),
        y: +((y - r.top) / Math.max(1, r.height) * 100).toFixed(2)
      } : null,
      context: { section: ref ? (sectionOf(ref) || null) : null }
    };
  }

  function elementsInRect(l, t, w, h) {
    var out = [];
    var all = document.body.getElementsByTagName('*');
    var r2 = l + w, b2 = t + h;
    for (var i = 0; i < all.length && out.length < MAX_REGION_ITEMS * 3; i++) {
      var n = all[i];
      if (isOurNode(n)) { continue; }
      var r = n.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0) { continue; }
      var cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      if (cx >= l && cx <= r2 && cy >= t && cy <= b2) { out.push(n); }
    }
    // 优先保留携带语义信息的元素
    var primary = [], other = [];
    out.forEach(function (n) {
      (classify(n) === 'primary' ? primary : other).push(n);
    });
    return primary.concat(other).slice(0, MAX_REGION_ITEMS);
  }

  function onMouseUp(e) {
    if (!state.drag) { return; }
    var d = state.drag;
    state.drag = null;
    clearHighlight();
    e.stopPropagation(); e.preventDefault();

    var w = Math.abs(d.x1 - d.x0), h = Math.abs(d.y1 - d.y0);
    var left = Math.min(d.x0, d.x1), top = Math.min(d.y0, d.y1);

    // Ctrl+单击：直接定点，不展开列表
    if (!d.shift && w < 6 && h < 6) {
      var pa = pointAnchor(d.x0, d.y0);
      var node = pa.nodeRef;
      showPin(d.x0, d.y0);
      toggleSelected({
        node: node, kind: 'point', anchor: pa,
        d: node ? describe(node) : pseudo('', '位置')
      });
      toast('已加入定点批注');
      return;
    }

    // Shift+拖拽：区域选择，列表含「区域本身」与框内元素
    var docW = Math.max(1, document.documentElement.scrollWidth);
    var docH = Math.max(1, document.documentElement.scrollHeight);
    var regionAnchor = {
      mode: 'region',
      docPx: { x: Math.round(left + window.scrollX), y: Math.round(top + window.scrollY) },
      docPct: {
        x: +((left + window.scrollX) / docW * 100).toFixed(2),
        y: +((top + window.scrollY) / docH * 100).toFixed(2)
      },
      viewport: { w: window.innerWidth, h: window.innerHeight },
      rect: { w: Math.round(w), h: Math.round(h) }
    };

    var items = [{
      node: null, kind: 'region', anchor: regionAnchor, tier: 'head',
      d: pseudo(Math.round(w) + ' × ' + Math.round(h), '区域')
    }];

    var rp = [], ro = [];
    elementsInRect(left, top, w, h).forEach(function (n) {
      var tier = (classify(n) === 'primary') ? 'primary' : 'other';
      var it = { node: n, kind: 'element', anchor: null, d: describe(n), tier: tier };
      (tier === 'primary' ? rp : ro).push(it);
    });
    items = items.concat(rp, ro);

    showPin(left, top);
    showRegion(left, top, w, h);
    buildList(items, left, top);
    toast('框选到 ' + (items.length - 1) + ' 个元素');
  }

  function onClick(e) {
    if (fromHost(e)) { return; }
    e.stopPropagation(); e.preventDefault();

    // 固定只保护这一次选择不被误点冲掉；在别处点选意味着开始新的选择，
    // 旧的固定自然结束 —— 否则用户会发现「点第二个没反应」，列表也不刷新
    if (state.pin) { removePin(); removeRegion(); closeList(); }

    var nodes = document.elementsFromPoint ? document.elementsFromPoint(e.clientX, e.clientY) : [];
    if (!nodes.length) { return; }

    var primary = [], other = [];
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (isOurNode(n)) { continue; }
      var tier = (classify(n) === 'primary') ? 'primary' : 'other';
      var it = { node: n, kind: 'element', anchor: null, d: describe(n), tier: tier };
      (tier === 'primary' ? primary : other).push(it);
    }

    var pa = pointAnchor(e.clientX, e.clientY);
    var items = [{
      node: null, kind: 'point', anchor: pa, tier: 'head',
      d: pseudo('', '这个位置')
    }].concat(primary, other);

    showPin(e.clientX, e.clientY);
    buildList(items, e.clientX, e.clientY);
  }

  function attach() {
    BLOCKED.forEach(function (t) { document.addEventListener(t, blocker, true); });
    document.addEventListener('keydown', onKeyDown, true);
    document.addEventListener('mousedown', onMouseDown, true);
    document.addEventListener('mousemove', onMouseMove, true);
    document.addEventListener('mouseup', onMouseUp, true);
    document.addEventListener('click', onClick, true);
  }

  function detach() {
    BLOCKED.forEach(function (t) { document.removeEventListener(t, blocker, true); });
    document.removeEventListener('keydown', onKeyDown, true);
    document.removeEventListener('mousedown', onMouseDown, true);
    document.removeEventListener('mousemove', onMouseMove, true);
    document.removeEventListener('mouseup', onMouseUp, true);
    document.removeEventListener('click', onClick, true);
  }

  // ---------------------------------------------------------------- 模式

  function enterMode() {
    if (state.active) { return; }
    var stat = enterSnapshot();
    state.active = true;
    attach();
    if (fab.parentNode) { fab.remove(); }
    ui.appendChild(bar);
    bar.style.display = 'flex';
    ghostApply(bar);
    buildPanel();
    refreshCount();
    repin();
    toast('批注模式已开启' +
      (stat.total ? '（已移植 ' + stat.transplanted + '/' + stat.total + ' 个 canvas）' : '') +
      (stat.disabled ? ' · 已解除 ' + stat.disabled + ' 个 disabled 控件（仅副本内）' : '') +
      (stat.controls ? ' ⚠ 内有 ' + stat.controls + ' 个控件已失效：需改参数请先退出，在原生模式下调好再进来'
                     : ''));
  }

  function exitMode() {
    if (!state.active) { return; }
    state.active = false;
    detach();
    closeList(); removePin(); removeRegion(); clearPanel(); closePanel();
    while (pinLayer.firstChild) { pinLayer.removeChild(pinLayer.firstChild); }
    clearHighlight();
    exitSnapshot();
    state.selected = [];
    state.panelCollapsed = false;
    setGhost(false);
    if (bar.parentNode) { bar.remove(); }
    ui.appendChild(fab);
    toast('已退出，页面已还原');
  }

  // ---------------------------------------------------------------- 装配

  var ui = el('div');
  ui.style.cssText = 'position:static;pointer-events:none;background:none;border:0;box-shadow:none';
  shadow.appendChild(ui);
  ui.appendChild(fab);

  document.addEventListener('keydown', function (e) {
    if (state.active) { return; }
    if (HOTKEY.alt && e.altKey && e.key && e.key.toLowerCase() === HOTKEY.key) {
      e.preventDefault();
      enterMode();
    }
  }, true);

  fabBtn.addEventListener('click', function () { if (!state.active) { enterMode(); } });
  makeDraggable(bar, grip);
  bGhost.addEventListener('click', function () { setGhost(!state.ghost); });
  bExit.addEventListener('click', exitMode);
  bExpand.addEventListener('click', function () {
    var ds = document.querySelectorAll('details');
    var n = 0;
    Array.prototype.forEach.call(ds, function (d) { if (!d.open) { d.open = true; n++; } });
    repin();
    toast('已展开 ' + n + ' 个折叠区（共 ' + ds.length + '）');
  });
  bList.addEventListener('click', openPanel_);
  bExport.addEventListener('click', exportJSON);

  restore();
  refreshCount();
  repin();

  window.__VPE__ = {
    state: state,
    enter: enterMode,
    exit: exitMode,
    export: exportJSON,
    toggle: toggleSelected,
    commit: commit,
    setGhost: setGhost,
    diag: function () {
      var r = {
        version: '0.1.0-p9',
        active: state.active,
        ghost: state.ghost,
        scrollY: Math.round(window.scrollY),
        pin: state.pin,
        pinStyleTop: pinEl ? pinEl.style.top : null,
        listAnchor: state.listAnchor,
        listDragged: state.listDragged,
        listStyleTop: listBox ? listBox.style.top : null,
        region: state.region ? { dx: state.region.dx, dy: state.region.dy } : null
      };
      console.log('[VPE diag]', JSON.stringify(r));
      return r;
    },
    // 滚动前后对比：能区分「跟随生效」与「压根没滚动过」
    scrollTest: function () {
      var hn = document.getElementById('__vpe_host');
      var pn = hn && hn.shadowRoot.querySelector('.pin');
      var lb = hn && hn.shadowRoot.querySelector('.list');
      if (!pn) { console.log('[VPE] 当前没有图钉，请先点选一个元素'); return null; }
      var a = {
        scrollY: Math.round(window.scrollY),
        pinTop: Math.round(pn.getBoundingClientRect().top),
        pinStyleTop: pn.style.top,
        listTop: lb ? Math.round(lb.getBoundingClientRect().top) : null,
        listStyleTop: lb ? lb.style.top : null
      };
      window.scrollBy(0, 200);
      setTimeout(function () {
        var b = {
          scrollY: Math.round(window.scrollY),
          pinTop: Math.round(pn.getBoundingClientRect().top),
          pinStyleTop: pn.style.top,
          listTop: lb ? Math.round(lb.getBoundingClientRect().top) : null,
          listStyleTop: lb ? lb.style.top : null
        };
        var dScroll = b.scrollY - a.scrollY;
        var dPin = b.pinTop - a.pinTop;
        var out = {
          before: a, after: b,
          scrollMoved: dScroll, pinMovedOnScreen: dPin,
          verdict: dScroll === 0
            ? '页面没滚动（可能已到顶/到底），本次测试无效'
            : (Math.abs(dPin + dScroll) <= 6
                ? '✓ 图钉跟随正常'
                : '✗ 图钉未跟随，dPin=' + dPin + ' dScroll=' + dScroll)
        };
        console.log('[VPE scrollTest]', JSON.stringify(out));
        window.scrollBy(0, -200);
      }, 420);
      return '测试已发出，420ms 后看控制台';
    },
    version: '0.1.0-p9'
  };
})();
