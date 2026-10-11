# 创建时间: 2026-10-11 20:17:41
# 用途：把批注运行时内联进目标页面，生成可交互的批注副本（不改动源文件）。
#   支持 --selftest：注入自动化验证脚本，检查快照建立/还原、canvas 移植、UI 挂载与 JS 异常。
#   副本为单文件、无外部依赖，可直接以 file:// 打开。
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ANNOTATOR = HERE.parent / "assets" / "annotator.js"

sys.dont_write_bytecode = True   # 不在 skill 目录里留 __pycache__（.pyc 会嵌绝对路径）
sys.path.insert(0, str(HERE))
import build_lexicon  # noqa: E402  —— 同目录脚本，生成运行时反查表

SELFTEST = r"""
<script>
(function(){
  var errors = [];
  window.addEventListener('error', function(e){ errors.push(String(e.message)); });

  function emit(r){
    try {
      document.head.innerHTML = '';
      document.body.innerHTML = '';
      var d = document.createElement('div');
      d.id = 'VPE_SELFTEST';
      d.textContent = 'VPE_SELFTEST:' + JSON.stringify(r);
      document.body.appendChild(d);
    } catch(e){ document.title = 'VPE_SELFTEST_FAIL'; }
  }

  window.addEventListener('load', function(){
    setTimeout(function(){
      var r = { errors: errors };
      try {
        r.loaded = !!window.__VPE__;
        r.version = window.__VPE__ ? window.__VPE__.version : null;

        var before = document.body;
        var cBefore = [];
        var cs = document.querySelectorAll('canvas');
        r.canvasCount = cs.length;
        for (var i = 0; i < cs.length && i < 3; i++) { cBefore.push(cs[i].toDataURL().length); }
        r.canvasBefore = cBefore;

        var host0 = document.getElementById('__vpe_host');
        r.hostPresent = !!host0;
        r.fabPresent = !!(host0 && host0.shadowRoot && host0.shadowRoot.querySelector('.fab'));
        r.barBeforeEnter = !!(host0 && host0.shadowRoot && host0.shadowRoot.querySelector('.bar'));

        // 造一个 disabled 控件：浏览器在命中测试阶段就丢弃它，连 mousedown 都不派发。
        // 副本应只在克隆体上解除它，原页面不受影响。
        var probeBtn = document.createElement('button');
        probeBtn.id = 'vpe-probe-disabled';
        probeBtn.disabled = true;
        probeBtn.textContent = 'probe';
        probeBtn.style.cssText = 'position:fixed;left:4px;bottom:4px;width:80px;height:20px';
        document.body.appendChild(probeBtn);

        // 进入批注模式
        window.__VPE__.enter();
        var st = window.__VPE__.state;
        r.active = st.active;
        r.bodyReplaced = (document.body !== before);
        r.origKept = !!st.origBody;
        var pb = document.getElementById('vpe-probe-disabled');
        r.disabledProbeCleared = !!pb && pb.disabled === false;

        var cs2 = document.querySelectorAll('canvas');
        var cAfter = [];
        for (var j = 0; j < cs2.length && j < 3; j++) { cAfter.push(cs2[j].toDataURL().length); }
        r.canvasAfter = cAfter;
        r.canvasPreserved = (r.canvasBefore.length > 0 &&
          JSON.stringify(r.canvasBefore) === JSON.stringify(cAfter));

        var host1 = document.getElementById('__vpe_host');
        r.hostSurvivedSnapshot = !!host1;
        r.barVisible = !!(host1 && host1.shadowRoot &&
          host1.shadowRoot.querySelector('.bar') &&
          host1.shadowRoot.querySelector('.bar').style.display !== 'none');

        // 走一遍真实点选、多选、取消、提交路径
        var cands = document.querySelectorAll('[id]');
        var pt = null;
        for (var k = 0; k < cands.length; k++) {
          var nd = cands[k];
          if (nd === host1) { continue; }
          var rr = nd.getBoundingClientRect();
          if (rr.width > 40 && rr.height > 12 && rr.top > 60 &&
              rr.bottom < window.innerHeight - 140 && rr.left >= 0) {
            pt = { x: Math.round(rr.left + Math.min(rr.width / 2, 180)),
                   y: Math.round(rr.top + rr.height / 2) };
            break;
          }
        }
        if (!pt) {
          // 应用型页面可能整屏都是 canvas，空态下没有合适的既有元素；
          // 造一个探针元素，保证「点选 → 候选列表 → 提交 → 框选」这条链路仍被覆盖
          var probe = document.createElement('div');
          probe.id = 'vpe-probe-target';
          probe.textContent = '探针元素';
          probe.style.cssText = 'position:fixed;left:120px;top:180px;width:220px;height:60px';
          document.body.appendChild(probe);
          pt = { x: 200, y: 210 };
          r.usedProbeTarget = true;
        }
        if (pt) {
          document.dispatchEvent(new MouseEvent('click', {
            clientX: pt.x, clientY: pt.y, bubbles: true, cancelable: true
          }));
          r.listOpened = !!host1.shadowRoot.querySelector('.list');
          r.pinShown = !!host1.shadowRoot.querySelector('.pin');

          // 钉子对齐：针尖必须精确落在点击坐标
          (function () {
            var pn = host1.shadowRoot.querySelector('.pin');
            if (!pn) { return; }
            var pr = pn.getBoundingClientRect();
            r.pinGlyph = pn.textContent;
            r.pinW = Math.round(pr.width);
            r.pinH = Math.round(pr.height);
            // 针尖位于元素高度的 95% 处（见 .pin 的 translate(-50%,-95%)）
            r.pinTipX = Math.round(pr.left + pr.width / 2);
            r.pinTipY = Math.round(pr.top + pr.height * 0.95);
            r.pinOffsetX = r.pinTipX - pt.x;
            r.pinOffsetY = r.pinTipY - pt.y;
            r.pinAligned = (Math.abs(r.pinOffsetX) <= 1 && Math.abs(r.pinOffsetY) <= 1);
          })();

          var items = window.__VPE__.state.listItems;
          r.listItemCount = items.length;
          r.firstItemKind = items[0] ? items[0].kind : null;

          // 选两个元素项（跳过首项的「位置」伪项）
          if (items.length > 1) { window.__VPE__.toggle(items[1]); }
          if (items.length > 2) { window.__VPE__.toggle(items[2]); }
          r.selectedCount = window.__VPE__.state.selected.length;
          if (items.length > 1) {
            window.__VPE__.toggle(items[1]);            // 再点应取消
            r.afterUntoggle = window.__VPE__.state.selected.length;
            window.__VPE__.toggle(items[1]);            // 加回来
          }

          // 面板折叠 / 展开
          var foldBtn = host1.shadowRoot.querySelector('#vpe-fold');
          if (foldBtn) { foldBtn.click(); }
          r.panelCollapsed = window.__VPE__.state.panelCollapsed;
          var selBox = host1.shadowRoot.querySelector('.sel');
          r.panelBodyHidden = !!(selBox && selBox.style.display === 'none');
          if (foldBtn) { foldBtn.click(); }
          r.panelRestored = !window.__VPE__.state.panelCollapsed;

          // 列表标题栏应可拖拽
          var hdEl = host1.shadowRoot.querySelector('.list .hd');
          r.listDraggable = !!hdEl && hdEl.style.cursor === 'move';

          // 让路：浮层变淡并放行鼠标事件，恢复后还原
          var barEl = host1.shadowRoot.querySelector('.bar');
          var barRect = barEl ? barEl.getBoundingClientRect() : null;
          var bx = barRect ? Math.round(barRect.left + barRect.width / 2) : 0;
          var by = barRect ? Math.round(barRect.top + barRect.height / 2) : 0;
          window.__VPE__.setGhost(true);
          r.ghostOn = window.__VPE__.state.ghost;
          r.ghostBarPassThrough = !!(barEl && barEl.style.pointerEvents === 'none');
          r.ghostRestoreBtn = !!host1.shadowRoot.querySelector('.ghost-back');
          if (barRect) {
            // elementFromPoint 对 shadow 内容返回宿主元素，故「不再是宿主」即已穿透
            var hitAfter = document.elementFromPoint(bx, by);
            r.ghostHitAfter = hitAfter
              ? hitAfter.tagName.toLowerCase() + (hitAfter.id ? '#' + hitAfter.id : '') : null;
            r.ghostPassesThrough = !!hitAfter && hitAfter.id !== '__vpe_host';
          }
          window.__VPE__.setGhost(false);
          r.ghostOff = !window.__VPE__.state.ghost &&
            !!barEl && barEl.style.pointerEvents === '';
          if (barRect) {
            var hitBack = document.elementFromPoint(bx, by);
            r.ghostHitRestored = !!hitBack && hitBack.id === '__vpe_host';
          }

          // 拖动：工具栏与两个面板此前都钉死在边缘，目标元素落在其下就无法指认
          (function () {
            function dragBy(node, handle, dx, dy) {
              if (!node || !handle) { return null; }
              var a = node.getBoundingClientRect();
              handle.dispatchEvent(new MouseEvent('mousedown', {
                clientX: a.left + 2, clientY: a.top + 2,
                button: 0, bubbles: true, cancelable: true
              }));
              document.dispatchEvent(new MouseEvent('mousemove', {
                clientX: a.left + 2 + dx, clientY: a.top + 2 + dy,
                bubbles: true, cancelable: true
              }));
              document.dispatchEvent(new MouseEvent('mouseup', {
                clientX: a.left + 2 + dx, clientY: a.top + 2 + dy,
                bubbles: true, cancelable: true
              }));
              var b = node.getBoundingClientRect();
              return Math.round(b.left - a.left) + ',' + Math.round(b.top - a.top);
            }
            r.dragBar = dragBy(barEl, host1.shadowRoot.querySelector('.bar .grip'), 60, -40);
            var pnEl = host1.shadowRoot.querySelector('.panel');
            r.dragPanel = dragBy(pnEl, pnEl && pnEl.querySelector('.ph'), 40, -30);

            var btns = host1.shadowRoot.querySelectorAll('.bar .btn');
            var bListBtn = null;
            for (var bi = 0; bi < btns.length; bi++) {
              if (btns[bi].textContent === '批注列表') { bListBtn = btns[bi]; }
            }
            if (bListBtn) {
              bListBtn.click();
              var pAll = host1.shadowRoot.querySelectorAll('.panel');
              var lastP = pAll[pAll.length - 1];
              r.dragAnnoPanel = dragBy(lastP, lastP && lastP.querySelector('.ph'), 30, -20);
              bListBtn.click();
            }
          })();

          // 钉子在时，在别处单击应开始新的选择，而不是被静默吞掉
          var pinBefore = host1.shadowRoot.querySelector('.pin');
          var pinLeftBefore = pinBefore ? pinBefore.style.left : null;
          document.dispatchEvent(new MouseEvent('click', {
            clientX: pt.x + 40, clientY: pt.y + 40, bubbles: true, cancelable: true
          }));
          var pinAfter = host1.shadowRoot.querySelector('.pin');
          r.pinMovedOnNewClick = !!(pinAfter && pinAfter.style.left !== pinLeftBefore);
          r.listRefreshedOnNewClick = !!host1.shadowRoot.querySelector('.list');

          // 点大头钉：收起列表并移除钉子
          var pinNode = host1.shadowRoot.querySelector('.pin');
          if (pinNode) {
            pinNode.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }));
          }
          r.listClosedByPin = !host1.shadowRoot.querySelector('.list');
          r.pinRemovedByPin = !host1.shadowRoot.querySelector('.pin');

          // 解锁后可重新选定
          document.dispatchEvent(new MouseEvent('click', {
            clientX: pt.x, clientY: pt.y, bubbles: true, cancelable: true
          }));
          r.reopenAfterUnlock = !!host1.shadowRoot.querySelector('.list');
          r.pinBackAfterUnlock = !!host1.shadowRoot.querySelector('.pin');

          // 滚动诊断 + 跟随验证
          (function () {
            r.diag_docScrollH = document.documentElement.scrollHeight;
            r.diag_bodyScrollH = document.body.scrollHeight;
            r.diag_innerH = window.innerHeight;

            // 找出页面里真正可滚动的容器（可能是内部 overflow 容器而非 window）
            var scrollers = [];
            var all2 = document.querySelectorAll('*');
            for (var q = 0; q < all2.length && scrollers.length < 5; q++) {
              var nd2 = all2[q];
              if (nd2.id === '__vpe_host') { continue; }
              var cs2 = getComputedStyle(nd2);
              if ((cs2.overflowY === 'auto' || cs2.overflowY === 'scroll') &&
                  nd2.scrollHeight > nd2.clientHeight + 30) {
                scrollers.push(nd2.tagName + (nd2.id ? '#' + nd2.id : '') +
                  (nd2.className ? '.' + String(nd2.className).split(' ')[0] : '') +
                  ' sh=' + nd2.scrollHeight + ' ch=' + nd2.clientHeight);
              }
            }
            r.diag_scrollers = scrollers;
            r.diag_docOverflowY = getComputedStyle(document.documentElement).overflowY;
            r.diag_bodyOverflowY = getComputedStyle(document.body).overflowY;

            var sy0 = window.scrollY;
            r.diag_scrollY0 = Math.round(sy0);

            // 先触发一次高亮（模拟悬停列表行），再滚动，才能测出高亮框是否脱节
            var rows = host1.shadowRoot.querySelectorAll('.list .row');
            if (rows.length > 1) { rows[1].dispatchEvent(new MouseEvent('mouseenter')); }
            var hl = host1.shadowRoot.querySelector('.hl');
            var pn = host1.shadowRoot.querySelector('.pin');
            var lb = host1.shadowRoot.querySelector('.list');
            var h0 = hl ? hl.getBoundingClientRect().top : null;
            var p0 = pn ? pn.getBoundingClientRect().top : null;
            var l0 = lb ? lb.getBoundingClientRect().top : null;

            window.scrollTo(0, sy0 + 200);
            window.dispatchEvent(new Event('scroll'));
            r.diag_scrollY1 = Math.round(window.scrollY);
            r.diag_windowScrollable = (r.diag_scrollY1 !== r.diag_scrollY0);

            var h1 = hl ? hl.getBoundingClientRect().top : null;
            var p1 = pn ? pn.getBoundingClientRect().top : null;
            var l1 = lb ? lb.getBoundingClientRect().top : null;

            r.pinScrollDelta = (p0 !== null && p1 !== null) ? Math.round(p1 - p0) : null;
            r.listScrollDelta = (l0 !== null && l1 !== null) ? Math.round(l1 - l0) : null;
            r.hlScrollDelta = (h0 !== null && h1 !== null) ? Math.round(h1 - h0) : null;
            r.pinFollowsScroll = (r.pinScrollDelta !== null) && Math.abs(r.pinScrollDelta + 200) <= 4;
            r.listFollowsScroll = (r.listScrollDelta !== null) && Math.abs(r.listScrollDelta + 200) <= 4;
            r.hlFollowsScroll = (r.hlScrollDelta !== null) && Math.abs(r.hlScrollDelta + 200) <= 6;

            window.scrollTo(0, sy0);
            window.dispatchEvent(new Event('scroll'));
          })();

          window.__VPE__.commit('自测批注内容', 'change-text');
          r.annotationsAfterCommit = window.__VPE__.state.annotations.length;
          r.selectedCleared = (window.__VPE__.state.selected.length === 0);
          var pt2 = host1.shadowRoot.querySelector('#vpe-panel-title');
          r.panelTitle = pt2 ? pt2.textContent : null;
          r.listClosedOnCommit = !host1.shadowRoot.querySelector('.list') ||
            host1.shadowRoot.querySelector('.list') === null;

          // 框选：区域预览应与图钉共存，并随图钉一同关闭
          var pPre = host1.shadowRoot.querySelector('.pin');
          if (pPre) { pPre.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true })); }
          document.dispatchEvent(new MouseEvent('mousedown', {
            clientX: 300, clientY: 320, shiftKey: true, bubbles: true, cancelable: true
          }));
          document.dispatchEvent(new MouseEvent('mousemove', {
            clientX: 520, clientY: 470, bubbles: true, cancelable: true
          }));
          document.dispatchEvent(new MouseEvent('mouseup', {
            clientX: 520, clientY: 470, shiftKey: true, bubbles: true, cancelable: true
          }));
          r.regionShown = !!host1.shadowRoot.querySelector('.region');
          r.pinShownAfterDrag = !!host1.shadowRoot.querySelector('.pin');
          var p2 = host1.shadowRoot.querySelector('.pin');
          if (p2) { p2.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true })); }
          r.regionClosedWithPin = !host1.shadowRoot.querySelector('.region');
          r.pinClosedWithPin = !host1.shadowRoot.querySelector('.pin');
        }

        // 退出
        window.__VPE__.exit();
        r.restored = (document.body === before);
        r.activeAfterExit = window.__VPE__.state.active;
        var pb2 = document.getElementById('vpe-probe-disabled');
        r.disabledProbeRestored = !!pb2 && pb2.disabled === true;
        if (pb2) { pb2.remove(); }

        var host2 = document.getElementById('__vpe_host');
        r.fabBack = !!(host2 && host2.shadowRoot && host2.shadowRoot.querySelector('.fab'));
      } catch (e) {
        r.error = String(e);
        r.stack = (e.stack || '').split('\n').slice(0, 3).join(' | ');
      }
      emit(r);
    }, 500);
  });
})();
</script>
"""


DEMO = r"""
<script>
/* 演示脚本：进入批注模式并在首个合适元素上派发一次点击，用于无头截图验证 UI。 */
(function(){
  window.addEventListener('load', function(){
    setTimeout(function(){
      if (!window.__VPE__) { return; }
      window.__VPE__.enter();
      var cands = document.querySelectorAll('[id]');
      var pt = null;
      for (var i = 0; i < cands.length; i++) {
        var n = cands[i];
        if (n === document.getElementById('__vpe_host')) { continue; }
        var r = n.getBoundingClientRect();
        if (r.width > 40 && r.height > 12 && r.top > 60 &&
            r.bottom < window.innerHeight - 140 && r.left >= 0) {
          pt = { x: Math.round(r.left + Math.min(r.width / 2, 180)),
                 y: Math.round(r.top + r.height / 2) };
          break;
        }
      }
      if (pt) {
        document.dispatchEvent(new MouseEvent('click', {
          clientX: pt.x, clientY: pt.y, bubbles: true, cancelable: true
        }));
        // 再点一次列表首行，以呈现「已加入待批注」的选中态
        setTimeout(function () {
          var h = document.getElementById('__vpe_host');
          var row = h && h.shadowRoot && h.shadowRoot.querySelector('.row');
          if (row) {
            row.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }));
          }
        }, 120);
      }
    }, 600);
  });
})();
</script>
"""


def json_for_script(obj) -> str:
    """内联进 <script> 的 JSON。

    必须把 `</` 转义成 `<\\/`：倒排表里存的是源码字符串字面量，而页面源码
    本身就经常含 `</script>` —— 不转义会提前闭合标签，把整个注入块劈成
    语法错误，运行时拿不到任何数据（表现为「注入了但读不到」）。
    U+2028/2029 在 JS 源码里是换行符，同样要转义。
    """
    s = json.dumps(obj, ensure_ascii=False)
    return (s.replace("</", "<\\/")
             .replace("\u2028", "\\u2028")
             .replace("\u2029", "\\u2029"))


def probe(html: str) -> dict:
    """页面特征探测：决定副本的已知局限与使用提示。"""
    def n(pat: str) -> int:
        return len(re.findall(pat, html, re.I))

    return {
        "canvas": n(r"<canvas\b"),
        "svg": n(r"<svg\b"),
        "details": n(r"<details\b"),
        "controls": n(r"<(?:input|select|textarea)\b"),
        "script": n(r"<script\b"),
        "elements": n(r"<[a-zA-Z][a-zA-Z0-9-]*[\s/>]"),
    }


def offline_index(src: Path, out_json: Path, sources: list) -> dict:
    """对没有生成器注入的页面做离线反查：CSS 路径 -> 源码坐标。

    返回 {cssPath: {coord, confidence, why, kind, line_text}}。页面自带
    data-src 时不需要这一步（生成器知道的比反查准）。
    """
    cmd = [sys.executable, str(HERE / "index_elements.py"), str(src), "-o", str(out_json)]
    for s in sources:
        cmd += ["--source", str(s)]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        print("  [警告] 离线反查失败：%s" % (proc.stderr or proc.stdout or "").strip()[:200])
        return {}, {}
    data = json.loads(out_json.read_text(encoding="utf-8"))

    index = {}
    for e in data.get("elements", []):
        srcs = e.get("src") or []
        if not srcs:
            continue
        s = srcs[0]
        coord = None
        if s.get("file") and s.get("line"):
            coord = "%s:%s" % (s["file"], s["line"])
        elif s.get("file"):
            coord = s["file"]
        index[e["path"]] = {
            "coord": coord,
            "confidence": s.get("confidence"),
            "why": s.get("why"),
            "kind": s.get("kind"),
            "line_text": (s.get("line_text") or "")[:120] or None,
        }
    return index, data.get("stats", {})


def default_sources(src: Path) -> list:
    """离线反查的默认源码集合：页面同目录 + src/ 子目录。

    单文件可视化页通常由「组装脚本 + 模板 + 前端逻辑」拼成（如
    build_page.py + src/page_template.html + src/app.js），只喂组装脚本会
    漏掉页面的绝大部分字面量。
    """
    exts = (".py", ".js", ".mjs", ".ts", ".html", ".htm")
    out = []
    for d in (src.parent, src.parent / "src"):
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if p.is_file() and p.suffix.lower() in exts and p.resolve() != src.resolve():
                out.append(p)
    return out


def find_browser() -> str:
    """本机可用的无头浏览器。"""
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if Path(p).is_file():
            return p
    for n in ("msedge", "chrome", "google-chrome", "chromium"):
        w = shutil.which(n)
        if w:
            return w
    return ""


def run_selftest(out: Path, budget_ms: int = 12000, timeout: int = 180):
    """驱动无头浏览器跑副本里的自检探针，返回结果字典（失败返回 None）。

    浏览器 profile 会在系统临时目录里展开数百 MB，且每个会话一份、互不复用，
    因此它是一次性垃圾而不是缓存。这里用 TemporaryDirectory 兜底删除；
    调用方不要自己去拼 --user-data-dir，否则每验证一次就留下一个几百 MB 的目录。
    """
    exe = find_browser()
    if not exe:
        print("  [自检] 未找到 Edge/Chrome，已跳过。探针已在副本内，"
              "可自行用浏览器打开后读取 #VPE_SELFTEST")
        return None
    with tempfile.TemporaryDirectory(prefix="vpe-verify-") as td:
        cmd = [exe, "--headless=new", "--disable-gpu", "--no-sandbox",
               "--window-size=1600,1100", "--user-data-dir=" + td,
               "--virtual-time-budget=%d" % budget_ms, "--dump-dom",
               out.resolve().as_uri()]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as e:
            print("  [自检] 浏览器执行失败：%s" % e)
            return None
    m = re.search(r"VPE_SELFTEST:(\{.*?\})</div>", proc.stdout or "", re.S)
    if not m:
        print("  [自检] 未读到结果：副本未注入探针，或页面脚本自身抛错")
        return None
    try:
        return json.loads(m.group(1))
    except ValueError as e:
        print("  [自检] 结果不是合法 JSON：%s" % e)
        return None


def report_selftest(r) -> None:
    if not r:
        return
    errs = [e for e in (r.get("errors") or []) if e]
    print("  [自检] 运行版本 %s" % r.get("version"))
    if errs:
        print("  [自检] ✗ JS 异常：%s" % "; ".join(errs)[:200])
    checks = [
        ("进入/退出批注模式", r.get("active") is True and r.get("activeAfterExit") is False),
        ("快照建立与还原", r.get("restored") is True and r.get("origKept") is True),
        ("canvas 像素移植", r.get("canvasPreserved") is not False),
        ("图钉与点击对齐", r.get("pinAligned") is not False),
        ("点选能展开候选", r.get("listOpened") is True),
        ("连续点选不被吞", r.get("pinMovedOnNewClick") is not False),
        ("disabled 控件可点", r.get("disabledProbeCleared") is not False),
        ("disabled 只改副本", r.get("disabledProbeRestored") is not False),
        ("让路能穿透", r.get("ghostPassesThrough") is not False),
        ("让路可还原", r.get("ghostOff") is not False),
    ]
    for name, ok in checks:
        print("    %s %s" % ("✓" if ok else "✗", name))
    known = {"activeAfterExit", "barBeforeEnter", "listClosedOnCommit"}
    bad = sorted(k for k, v in r.items() if v is False and k not in known)
    if bad:
        print("    其余为 false 的项: %s" % ", ".join(bad))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="源 HTML")
    ap.add_argument("out", nargs="?", help="输出副本（默认 <src>.annotate.html）")
    ap.add_argument("--annotator", default=str(DEFAULT_ANNOTATOR))
    ap.add_argument("--source", action="append", default=[],
                    help="离线反查用的源码文件（可重复；默认取页面同目录的 .py）")
    ap.add_argument("--selftest", action="store_true",
                    help="只注入自检探针，结果需自行用浏览器读取")
    ap.add_argument("--verify", action="store_true",
                    help="注入探针并驱动无头浏览器跑一遍，直接打印结论（临时 profile 自动清理）")
    ap.add_argument("--demo", action="store_true",
                    help="注入演示脚本，用于无头截图验证 UI")
    args = ap.parse_args()
    if args.verify:
        args.selftest = True

    src = Path(args.src)
    if not src.is_file():
        print("源文件不存在: %s" % src)
        return 2

    ann_path = Path(args.annotator)
    if not ann_path.is_file():
        print("运行时不存在: %s" % ann_path)
        return 2

    out = Path(args.out) if args.out else src.with_suffix(".annotate.html")

    raw = src.read_bytes()
    html = raw.decode("utf-8", errors="replace")
    js = ann_path.read_text(encoding="utf-8")

    # 页面指纹：副本是独立文件、浏览器无法回溯原文件，所以由副本生成器
    # 算出源页面哈希，连同页面自报的生成器指纹一起交给运行时。
    page_meta = {
        "path": str(src.resolve()),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "annotatedAt": datetime.now().isoformat(timespec="seconds"),
    }
    for key in ("generator", "generator-sha256", "generator-bytes"):
        m = re.search(r'<meta name="vpe-%s" content="([^"]*)"' % re.escape(key), html)
        if m:
            page_meta[key] = m.group(1)

    feat = probe(html)

    # 坐标来源：页面自带 data-src 最准（生成器自己知道）；否则两路并用——
    # 静态索引管静态页面（一次算好、点选即得），倒排表管运行时反查
    # （JS 运行时生成的弹窗、列表天然有覆盖，不需要预先遍历状态）
    has_inline_src = 'data-src="' in html
    index: dict = {}
    lexicon: dict = {}
    sources: list = []
    if not has_inline_src:
        raw = [Path(s) for s in args.source] if args.source else default_sources(src)
        missing = [str(p) for p in raw if not p.exists()]
        if missing:
            print("  [警告] --source 不存在，已跳过: %s" % ", ".join(missing))
        # 目录会被递归展开（此前传目录是静默跳过，容易被误以为已生效）
        sources = [s for s in build_lexicon.collect_files([p for p in raw if p.exists()])
                   if s.resolve() != src.resolve()]
        if sources:
            with tempfile.TemporaryDirectory(prefix="vpe-index-") as td:
                index, _ = offline_index(src, Path(td) / "index.json", sources)
            lexicon = build_lexicon.build(sources, build_lexicon.common_root(sources))
        elif not raw:
            print("  [警告] 未指定源码且默认集合为空（页面不在源码目录旁）："
                  "批注将不含源码坐标，请用 --source 指定")

    if "</script" in js.lower():
        print("运行时含 </script 字面量，需转义后再内联")
        return 3

    idx_js = ("<script>window.__VPE_INDEX__=%s;</script>\n"
              % json_for_script(index)) if index else ""
    lex_js = ("<script>window.__VPE_LEXICON__=%s;</script>\n"
              % json_for_script(lexicon)) if lexicon.get("lex") else ""
    payload = ("<script>window.__VPE_PAGE__=%s;</script>\n"
               % json_for_script(page_meta)
               + idx_js + lex_js
               + "<script>\n" + js + "\n</script>")
    if args.selftest:
        payload += SELFTEST
    if args.demo:
        payload += DEMO

    if "</body>" in html:
        html = html.replace("</body>", payload + "</body>", 1)
    else:
        html = html + payload

    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        out.write_text(html, encoding="utf-8")
    except PermissionError:
        # 目标常因正被浏览器打开而锁定；改写为同名 .new 副本，避免整个流程失败
        alt = out.with_name(out.stem + ".new" + out.suffix)
        alt.write_text(html, encoding="utf-8")
        print("目标被占用（可能正被浏览器打开），已改写到: %s" % alt)
        out = alt
    print("副本已生成: %s (%.2f MB)" % (out, out.stat().st_size / 1048576))
    print("  页面特征: canvas %(canvas)d · svg %(svg)d · details %(details)d · "
          "控件 %(controls)d · script %(script)d · 元素约 %(elements)d" % feat)
    if feat["canvas"]:
        print("  [提示] 含 %d 个 canvas：像素在进入批注时移植；图形若依赖参数，"
              "请先在原生模式调好参数再进入" % feat["canvas"])
    if feat["controls"]:
        print("  [提示] 含 %d 个交互控件：快照内控件不可交互（值保留、拖动无效），"
              "请在进入批注前把参数调到位" % feat["controls"])
    print("  页面指纹: sha256 %s…  (%d bytes)" % (page_meta["sha256"][:12], page_meta["bytes"]))
    if has_inline_src:
        print("  坐标来源: 页面自带 data-src（生成器注入，最准）")
    elif index or lexicon.get("lex"):
        lex = lexicon.get("lex", {})
        multi = sum(1 for v in lex.values() if len(v) > 1)
        print("  坐标来源: 静态索引 %d 个元素 ｜ 运行时反查表 %d 个锚点（源文件 %d 个）"
              % (len(index), len(lex), len(sources)))
        if multi:
            print("    其中 %d 个锚点有多候选：运行时只标 ambiguous 并列候选，"
                  "由上下文投票决定采信哪一个" % multi)
    else:
        print("  坐标来源: 无 —— 页面无 data-src 且未能反查，批注将不含源码坐标")
    if "generator-sha256" in page_meta:
        print("  生成器指纹: %s sha256 %s…"
              % (page_meta["generator"], page_meta["generator-sha256"][:12]))
    else:
        print("  生成器指纹: 页面未声明（非 generate_page.py 产物，或页面版本过旧）")
    if args.verify:
        report_selftest(run_selftest(out))
    elif args.selftest:
        print("  自检: 探针已注入，用浏览器打开副本后读取 #VPE_SELFTEST")
    return 0


if __name__ == "__main__":
    sys.exit(main())
