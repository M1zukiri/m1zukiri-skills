// Created: 2026-11-18 23:00:05
// 校验「导入的会话在 DSH 里续聊时，工具不会被全部标成 defer_loading=true」。
// 用法: node dsh_verify_tools.mjs <session.jsonl|.jsonl.zstd>
//         [--tools-file tools.json] [--simulate-resume] [--resume-out file.jsonl]
// 原理: 恢复会话 -> session.toolHistory()（request/header 的工具基线 + developer 增补）
//       -> session.deriveMessages() -> projectToolUpdates(messages, 当前工具表, "addition-only", history)
//       = 下一轮 DSH 真正发给服务端的工具表。deepseek 路由是 addition-only：
//       若基线为空，全部工具都会 deferLoading=true，服务端直接拒绝
//       （tools: at least one tool must have defer_loading=false）。
// --simulate-resume: 再追加 DSH 下一轮会写的事件（turn/start -> step/start -> system/message
//       -> user/message -> step/end -> turn/end），交给 dsh_validate.mjs 校验文件仍合法。
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { platform, tmpdir } from "node:os";
import { fileURLToPath, pathToFileURL } from "node:url";
import { randomUUID } from "node:crypto";
import { zstdDecompressSync } from "node:zlib";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const SIM_SYSTEM = "You are an AI agent powered by DeepSeek Harness. (resume simulation)";

/* ---------------------------------------------------------------- DSH 包定位 */
function scopeOf(base) {
  const scope = "@deepseek-ai";
  const layouts = [
    base,
    join(base, scope),
    join(base, "node_modules", scope),
    join(base, "node_modules", scope, "dsh", "node_modules", scope),
    join(base, scope, "dsh", "node_modules", scope),
    join(base, "dsh", "node_modules", scope),
  ];
  for (const dir of layouts) {
    if (existsSync(join(dir, "dsh-session-format", "lib", "index.js"))) return dir;
  }
  return null;
}

function fromCommand(cmd) {
  const finder = platform() === "win32" ? "where" : "which";
  try {
    const out = execFileSync(finder, [cmd], { encoding: "utf8", timeout: 10000,
      stdio: ["ignore", "pipe", "ignore"] }).split(/\r?\n/)[0].trim();
    if (out) return out;
  } catch {
    /* ignore */
  }
  return null;
}

function npmGlobalRoots() {
  const roots = [];
  const npm = platform() === "win32" ? "npm.cmd" : "npm";
  const noDep = process.noDeprecation;
  process.noDeprecation = true;
  try {
    const out = execFileSync(npm, ["root", "-g"], { encoding: "utf8", timeout: 20000,
      stdio: ["ignore", "pipe", "ignore"], shell: platform() === "win32" }).trim();
    if (out) roots.push(out);
  } catch {
    /* ignore */
  } finally {
    process.noDeprecation = noDep;
  }
  return roots;
}

function desktopRoots() {
  const home = process.env.USERPROFILE || process.env.HOME || "";
  const localAppData = process.env.LOCALAPPDATA || join(home, "AppData", "Local");
  const bases = [
    join(localAppData, "Programs", "DeepSeek Harness", "resources", "app.asar.unpacked"),
    join(localAppData, "Programs", "DeepSeek Harness", "resources", "app.asar.unpacked", "dsh"),
    join(process.env.PROGRAMFILES || "", "DeepSeek Harness", "resources", "app.asar.unpacked"),
    "/Applications/DeepSeek Harness.app/Contents/Resources/app.asar.unpacked",
    "/opt/DeepSeek Harness/resources/app.asar.unpacked",
  ];
  return bases.filter((b) => b && existsSync(b))
    .flatMap((b) => [b, join(b, "dsh"), join(b, "node_modules")]);
}

function resolveScopeDir() {
  const attempted = [];
  if (process.env.DSH_PKG_ROOT) {
    attempted.push(process.env.DSH_PKG_ROOT);
    const found = scopeOf(resolve(process.env.DSH_PKG_ROOT));
    if (found) return { dir: found, how: "DSH_PKG_ROOT" };
  }
  const exe = fromCommand("dsh");
  if (exe) {
    attempted.push(exe);
    let dir = dirname(exe);
    for (let i = 0; i < 6 && dir; i += 1) {
      const found = scopeOf(dir);
      if (found) return { dir: found, how: "dsh executable" };
      const parent = dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  }
  for (const root of npmGlobalRoots()) {
    attempted.push(root);
    const found = scopeOf(root);
    if (found) return { dir: found, how: "npm root -g" };
  }
  for (const base of desktopRoots()) {
    attempted.push(base);
    const found = scopeOf(base);
    if (found) return { dir: found, how: "desktop install" };
  }
  console.error("ERROR: 找不到 DSH 的 @deepseek-ai/* 包（校验需要 DSH 自带代码）。");
  console.error("  已尝试: " + attempted.join("\n          "));
  console.error("  解决: 设置 DSH_PKG_ROOT 指向 npm 全局 node_modules/@deepseek-ai，或确认已安装 DSH。");
  process.exit(2);
}

const { dir, how } = resolveScopeDir();
const imp = (sub) => import(pathToFileURL(join(dir, sub)).href);
const { createSessionFormatCatalog } = await imp("dsh-session-format/lib/index.js");
const { Session, SessionId, SessionLogOffset, KNOWN_SESSION_EVENT_TYPES } = await imp("dsh-session/lib/index.js");
const { projectToolUpdates } = await imp("dsh-llm/lib/types/content.js");
const { releasedV0SessionFormatCodec, sessionFormatV0ToV1 } = await imp("dsh-session-format-v0-to-v1/lib/index.js");
const { releasedV1SessionFormatCodec, sessionFormatV1ToV2 } = await imp("dsh-session-format-v1-to-v2/lib/index.js");
const { releasedV2SessionFormatCodec, sessionFormatV2ToV3 } = await imp("dsh-session-format-v2-to-v3/lib/index.js");
const { releasedV3SessionFormatCodec, releasedV4SessionFormatCodec, sessionFormatV3ToV4, restoreReleasedV4Artifact, assertReleasedV4Header } = await imp("dsh-session-format-v3-to-v4/lib/index.js");

const EXTRA_EVENT_TYPES = ["job/registered", "job/settled", "working-directory/change"];
const VOCAB = new Set([...KNOWN_SESSION_EVENT_TYPES, ...EXTRA_EVENT_TYPES]);
const catalog = createSessionFormatCatalog({
  currentVersion: 4,
  codecs: [releasedV0SessionFormatCodec, releasedV1SessionFormatCodec, releasedV2SessionFormatCodec, releasedV3SessionFormatCodec, releasedV4SessionFormatCodec],
  migrations: [sessionFormatV0ToV1, sessionFormatV1ToV2, sessionFormatV2ToV3, sessionFormatV3ToV4],
  currentEncoder: releasedV4SessionFormatCodec,
  restoreCurrent: (a) => restoreReleasedV4Artifact(a, VOCAB),
  restoreTransformedCurrent: (a) => restoreReleasedV4Artifact(a, VOCAB),
  restoreCurrentHeader: (h) => { assertReleasedV4Header(h); return h; },
});

/* ---------------------------------------------------------------- 会话解码 */
function scanZstdFrames(buffer) {
  const frames = [];
  let offset = 0;
  while (offset < buffer.length) {
    const start = offset;
    if (buffer.readUInt32LE(offset) !== 0xfd2fb528) throw new Error("bad zstd magic at " + offset);
    offset += 4;
    const descriptor = buffer[offset++];
    const fcsFlag = descriptor >> 6;
    if (!((descriptor >> 5) & 1)) offset += 1;
    const dictFlag = descriptor & 3;
    offset += dictFlag === 1 ? 1 : dictFlag === 2 ? 2 : dictFlag === 3 ? 4 : 0;
    offset += fcsFlag === 1 ? 2 : fcsFlag === 2 ? 4 : fcsFlag === 3 ? 8 : 0;
    for (;;) {
      const header = buffer[offset] | (buffer[offset + 1] << 8) | (buffer[offset + 2] << 16);
      offset += 3;
      const last = header & 1;
      const type = (header >> 1) & 3;
      offset += type === 1 ? 1 : header >> 3;
      if (last) break;
    }
    if ((descriptor >> 2) & 1) offset += 4;
    frames.push([start, offset]);
  }
  return frames;
}

function decodeLines(path) {
  const bytes = readFileSync(path);
  const text = path.endsWith(".zstd")
    ? Buffer.concat(scanZstdFrames(bytes).map(([s, e]) => zstdDecompressSync(bytes.subarray(s, e)))).toString("utf8")
    : bytes.toString("utf8");
  return text.split("\n").filter((line) => line.length > 0);
}

function restoreSession(path) {
  const lines = decodeLines(path);
  if (!lines.length) throw new Error("文件为空: " + path);
  const headerRow = JSON.parse(lines[0]);
  const restore = catalog.createRestore(headerRow, { recovery: "strict", validation: "current" });
  for (const line of lines.slice(1)) restore.decodeRow(JSON.parse(line));
  const artifact = restore.finish();
  const session = Session.fromRestore(SessionId(artifact.header.id), artifact.events,
    artifact.header, SessionLogOffset(artifact.inheritedEventCount), "detached");
  return { lines, headerRow, artifact, session };
}

function loadTools(path) {
  const obj = JSON.parse(readFileSync(path, "utf8"));
  if (Array.isArray(obj)) return obj;
  if (Array.isArray(obj.tools)) return obj.tools;
  const header = (obj.data?.header) || obj.header || {};
  if (Array.isArray(header.tools)) return header.tools;
  throw new Error("无法从 " + path + " 解析工具表（需要数组或含 header.tools 的对象）");
}

/* ---------------------------------------------------------------- 主流程 */
const argv = process.argv.slice(2);
const positional = [];
let toolsFile = null;
let resumeOut = null;
let simulate = false;
for (let i = 0; i < argv.length; i += 1) {
  const arg = argv[i];
  if (arg === "--tools-file") { toolsFile = argv[++i]; continue; }
  if (arg === "--resume-out") { resumeOut = argv[++i]; continue; }
  if (arg === "--simulate-resume") { simulate = true; continue; }
  if (arg.startsWith("--")) continue;
  positional.push(arg);
}
const input = positional[0];
if (!input) {
  console.error("用法: node dsh_verify_tools.mjs <session.jsonl|.jsonl.zstd>"
    + " [--tools-file tools.json] [--simulate-resume] [--resume-out file.jsonl]");
  process.exit(2);
}
console.log(`DSH pkg root: ${dir} (${how})`);

const { artifact, session, lines, headerRow } = restoreSession(input);
const headerTools = (() => {
  for (const line of lines.slice(1)) {
    const row = JSON.parse(line);
    if (row.type === "request/header" && row.data?.header?.tools?.length) return row.data.header.tools;
  }
  return [];
})();
const currentTools = toolsFile ? loadTools(toolsFile) : headerTools;
if (!currentTools || !currentTools.length) {
  console.error("ERROR: 会话里没有工具基线，且未提供 --tools-file：续聊时全部工具会 defer_loading=true。");
  process.exit(1);
}

const history = session.toolHistory();
const messages = session.deriveMessages();
console.log("session:", artifact.header.id);
console.log(`history.tools=${history.tools.length} history.updates=${history.updates.length}`
  + ` baseline_deferred=${history.tools.filter((t) => t.deferLoading === true).length}`);
console.log(`current_tools=${currentTools.length} (${toolsFile || "会话 request/header 基线"})`);

const projected = projectToolUpdates(messages, currentTools, "addition-only", history);
const deferred = projected.tools.filter((t) => t.deferLoading === true);
console.log(`next_turn_tools=${projected.tools.length} next_turn_deferred=${deferred.length}`);
const pass = projected.tools.length > 0 && deferred.length === 0;
console.log(pass
  ? "PASS: 下一轮至少有 1 个可用工具，defer_loading=true 的数量为 0"
  : "FAIL: 工具会被全部标成 defer_loading=true，服务端会拒绝（tools: at least one tool must have defer_loading=false）");

/* ------------------------------------------------------- 模拟 DSH 续聊追加 */
function appendResumeTurn(linesIn) {
  const rows = linesIn.map((line) => JSON.parse(line));
  const header = rows[0];
  const events = rows.slice(1);
  const lastSeq = events.length ? events[events.length - 1].seq : -1;
  const turns = events.filter((e) => e.type === "turn/start");
  const nextTurn = (turns.length ? Math.max(...turns.map((e) => e.data.turn)) : 0) + 1;
  const now = Date.now();
  const extra = [
    { type: "turn/start", seq: lastSeq + 1, time: now, data: { turn: nextTurn } },
    { type: "step/start", seq: lastSeq + 2, time: now + 1, data: { turn: nextTurn, step: 1 } },
    {
      type: "system/message", seq: lastSeq + 3, time: now + 2, data: {
        turn: nextTurn, step: 1, message: {
          role: "system", source: { kind: "system-prompt" },
          content: [{ type: "text", text: SIM_SYSTEM }], id: randomUUID(),
        },
      }, surfaceOp: "append",
    },
    {
      type: "user/message", seq: lastSeq + 4, time: now + 3, data: {
        content: [{ type: "text", text: "继续（resume 模拟）" }],
        source: { kind: "user", rpcId: randomUUID(), clientTimeZone: "Asia/Shanghai" },
        role: "user", id: randomUUID(),
      }, surfaceOp: "append",
    },
    { type: "step/end", seq: lastSeq + 5, time: now + 4, data: { turn: nextTurn, step: 1 } },
    { type: "turn/end", seq: lastSeq + 6, time: now + 5, data: { turn: nextTurn, reason: { kind: "completed" } } },
  ];
  const outLines = [JSON.stringify(header), ...rows.slice(1).map((r) => JSON.stringify(r)),
    ...extra.map((e) => JSON.stringify(e))];
  return { lines: outLines, nextTurn, appended: extra.length };
}

if (simulate) {
  const resumed = appendResumeTurn(lines);
  const target = resumeOut || join(tmpdir(), `dsh-resume-${artifact.header.id}-${Date.now()}.jsonl`);
  writeFileSync(target, resumed.lines.join("\n") + "\n", "utf8");
  console.log(`resume simulation: +${resumed.appended} events, turn=${resumed.nextTurn}, file=${target}`);

  // 先在进程内用同一条编解码链校验一遍（不依赖外部进程）
  try {
    const restore = catalog.createRestore(headerRow, { recovery: "strict", validation: "current" });
    for (const line of resumed.lines.slice(1)) restore.decodeRow(JSON.parse(line));
    const art = restore.finish();
    Session.fromRestore(SessionId(art.header.id), art.events, art.header,
      SessionLogOffset(art.inheritedEventCount), "detached");
    console.log(`RESUME VALID: events=${art.events.length} turn=${resumed.nextTurn}`);
  } catch (err) {
    console.error("RESUME INVALID: " + (err?.message ?? err));
    process.exit(1);
  }
  // 再交给 dsh_validate.mjs 做一次 --canonical 复核
  const validator = join(SCRIPT_DIR, "dsh_validate.mjs");
  if (existsSync(validator)) {
    try {
      const out = execFileSync(process.execPath, [validator, target, "--canonical"],
        { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"], timeout: 120000 });
      process.stdout.write(out.split("\n").filter((l) => l && !l.startsWith("DSH pkg root"))
        .map((l) => "  " + l).join("\n") + "\n");
      console.log("RESUME CANONICAL: 追加后续聊文件仍可通过 DSH 校验");
    } catch (err) {
      console.error("RESUME 校验失败（dsh_validate.mjs）:\n" + (err.stdout || "") + (err.stderr || err.message));
      process.exit(1);
    }
  } else {
    console.error("[warn] 找不到同目录的 dsh_validate.mjs，跳过外部复核");
  }
}

process.exit(pass ? 0 : 1);
