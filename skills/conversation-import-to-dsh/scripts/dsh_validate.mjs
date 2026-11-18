// Created: 2026-11-18 22:59:26
// 用 DSH 自带代码校验会话文件（.jsonl 或 .zstd），可选 --canonical 逐行与 DSH encoder 比对。
// 用法: node dsh_validate.mjs <session.jsonl|session.v4.jsonl.zstd> [--canonical]
//   - 自行按 DSH scanZstdFrames 的结构规则扫描 zstd 拼接帧并逐帧解压
//   - 用 @deepseek-ai/dsh-session-format 的 v4 编解码 + 迁移链还原逻辑事件
//   - 用 Session.fromRestore 做「当前安装的 Session」语义校验（surface 折叠 / 消息投影）
//   - --canonical: 再用 DSH 的 encoder 重新编码每一行并逐字节比对
// DSH 包根动态定位（不写死路径）: DSH_PKG_ROOT > dsh 可执行文件 / npm root -g > 桌面安装目录。
import { existsSync, readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { platform } from "node:os";
import { pathToFileURL } from "node:url";
import { zstdDecompressSync } from "node:zlib";

const PKGS = ["dsh-session-format", "dsh-session", "dsh-llm"];

/** 把候选目录展开成可能的 @deepseek-ai 作用域目录（cli 与桌面版布局不同）。 */
function scopeOf(base) {
  const scope = ["@deepseek-ai"];
  const layouts = [
    base,
    join(base, ...scope),
    join(base, "node_modules", ...scope),
    join(base, "node_modules", ...scope, "dsh", "node_modules", ...scope),
    join(base, ...scope, "dsh", "node_modules", ...scope),
    join(base, "dsh", "node_modules", ...scope),
  ];
  for (const dir of layouts) {
    if (existsSync(join(dir, "dsh-session-format", "lib", "index.js"))) return dir;
  }
  return null;
}

function npmGlobalRoots() {
  const roots = [];
  const npm = platform() === "win32" ? "npm.cmd" : "npm";
  const noDep = process.noDeprecation;
  process.noDeprecation = true;                       // 屏蔽 execFile+shell 的 DEP0190 噪音
  try {
    const out = execFileSync(npm, ["root", "-g"], { encoding: "utf8", timeout: 20000,
      stdio: ["ignore", "pipe", "ignore"], shell: platform() === "win32" }).trim();
    if (out) roots.push(out);
  } catch {
    /* 没有 npm 就走后面的兜底 */
  } finally {
    process.noDeprecation = noDep;
  }
  return roots;
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

function desktopRoots() {
  const roots = [];
  const home = process.env.USERPROFILE || process.env.HOME || "";
  const localAppData = process.env.LOCALAPPDATA || join(home, "AppData", "Local");
  const bases = [
    join(localAppData, "Programs", "DeepSeek Harness", "resources", "app.asar.unpacked"),
    join(localAppData, "Programs", "DeepSeek Harness", "resources", "app.asar.unpacked", "dsh"),
    join(process.env.PROGRAMFILES || "", "DeepSeek Harness", "resources", "app.asar.unpacked"),
    "/Applications/DeepSeek Harness.app/Contents/Resources/app.asar.unpacked",
    "/opt/DeepSeek Harness/resources/app.asar.unpacked",
  ];
  for (const base of bases) {
    if (!base || !existsSync(base)) continue;
    roots.push(base, join(base, "dsh"), join(base, "node_modules"));
  }
  return roots;
}

function resolveScopeDir() {
  const attempted = [];
  const fromEnv = process.env.DSH_PKG_ROOT;
  if (fromEnv) {
    attempted.push(fromEnv);
    const found = scopeOf(resolve(fromEnv));
    if (found) return { dir: found, how: "DSH_PKG_ROOT" };
  }
  // 先走 dsh 可执行文件所在目录（能找到 npm 全局安装），再退到 npm root -g
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
  console.error("  解决: 设置环境变量 DSH_PKG_ROOT 指向 npm 全局 node_modules/@deepseek-ai，");
  console.error("        或确认已安装 DSH CLI（npm i -g @deepseek-ai/dsh）/ 桌面版。");
  process.exit(2);
}

const { dir, how } = resolveScopeDir();
const imp = (sub) => import(pathToFileURL(join(dir, sub)).href);

const { createSessionFormatCatalog } = await imp("dsh-session-format/lib/index.js");
const { Session, SessionId, SessionLogOffset, KNOWN_SESSION_EVENT_TYPES } = await imp("dsh-session/lib/index.js");
const { releasedV0SessionFormatCodec, sessionFormatV0ToV1 } = await imp("dsh-session-format-v0-to-v1/lib/index.js");
const { releasedV1SessionFormatCodec, sessionFormatV1ToV2 } = await imp("dsh-session-format-v1-to-v2/lib/index.js");
const { releasedV2SessionFormatCodec, sessionFormatV2ToV3 } = await imp("dsh-session-format-v2-to-v3/lib/index.js");
const { releasedV3SessionFormatCodec, releasedV4SessionFormatCodec, sessionFormatV3ToV4, restoreReleasedV4Artifact, assertReleasedV4Header } = await imp("dsh-session-format-v3-to-v4/lib/index.js");

// 运行中的 Electron 构建词表是 npm CLI 词表的超集（含 job/*、working-directory/change 等）
const EXTRA_EVENT_TYPES = ["job/registered", "job/settled", "working-directory/change"];
const VOCAB = new Set([...KNOWN_SESSION_EVENT_TYPES, ...EXTRA_EVENT_TYPES]);

const catalog = createSessionFormatCatalog({
  currentVersion: 4,
  codecs: [releasedV0SessionFormatCodec, releasedV1SessionFormatCodec, releasedV2SessionFormatCodec, releasedV3SessionFormatCodec, releasedV4SessionFormatCodec],
  migrations: [sessionFormatV0ToV1, sessionFormatV1ToV2, sessionFormatV2ToV3, sessionFormatV3ToV4],
  currentEncoder: releasedV4SessionFormatCodec,
  restoreCurrent: (artifact) => restoreReleasedV4Artifact(artifact, VOCAB),
  restoreTransformedCurrent: (artifact) => restoreReleasedV4Artifact(artifact, VOCAB),
  restoreCurrentHeader: (header) => {
    assertReleasedV4Header(header);
    return header;
  },
});

/** 结构扫描 zstd 拼接帧，规则与 DSH scanZstdFrames 一致。 */
function scanZstdFrames(buffer) {
  const frames = [];
  let offset = 0;
  while (offset < buffer.length) {
    const start = offset;
    if (buffer.length - offset < 4) throw new Error("truncated frame magic at " + offset);
    if (buffer.readUInt32LE(offset) !== 0xfd2fb528) throw new Error("bad zstd magic at " + offset);
    offset += 4;
    if (offset >= buffer.length) throw new Error("truncated frame header descriptor");
    const descriptor = buffer[offset++];
    const fcsFlag = descriptor >> 6;
    if (!((descriptor >> 5) & 1)) offset += 1; // window descriptor
    const dictFlag = descriptor & 3;
    offset += dictFlag === 1 ? 1 : dictFlag === 2 ? 2 : dictFlag === 3 ? 4 : 0;
    offset += fcsFlag === 1 ? 2 : fcsFlag === 2 ? 4 : fcsFlag === 3 ? 8 : 0;
    for (;;) {
      if (offset + 3 > buffer.length) throw new Error("truncated block header at " + offset);
      const header = buffer[offset] | (buffer[offset + 1] << 8) | (buffer[offset + 2] << 16);
      offset += 3;
      const last = header & 1;
      const type = (header >> 1) & 3;
      if (type === 3) throw new Error("reserved block type");
      offset += type === 1 ? 1 : header >> 3; // RLE 块只存 1 字节
      if (last) break;
    }
    if ((descriptor >> 2) & 1) offset += 4;
    if (offset > buffer.length) throw new Error("truncated frame body");
    frames.push([start, offset]);
  }
  return frames;
}

/** 读文件 -> 明文行（支持多帧 .zstd 与 .jsonl）。 */
export function decodeSessionFile(path) {
  const bytes = readFileSync(path);
  if (path.endsWith(".zstd")) {
    const frames = scanZstdFrames(bytes);
    const chunks = frames.map(([start, end]) => zstdDecompressSync(bytes.subarray(start, end)));
    return { text: Buffer.concat(chunks).toString("utf8"), frames: frames.length };
  }
  return { text: bytes.toString("utf8"), frames: 1 };
}

const path = process.argv[2];
const canonical = process.argv.includes("--canonical");
if (!path) {
  console.error("用法: node dsh_validate.mjs <session.jsonl|.jsonl.zstd> [--canonical]");
  process.exit(2);
}
console.log(`DSH pkg root: ${dir} (${how})`);

const { text, frames } = decodeSessionFile(path);
const lines = text.split("\n").filter((line) => line.length > 0);
if (!lines.length) {
  console.error("ERROR: 文件为空");
  process.exit(2);
}

let headerRow;
try {
  headerRow = JSON.parse(lines[0]);
} catch (err) {
  console.error("ERROR: 首行不是合法 JSON header: " + err.message);
  process.exit(2);
}

const classified = catalog.readHeader(headerRow);
console.log("frames=" + frames, "readHeader=" + classified.status,
  "stored=v" + classified.storedVersion, "target=v" + classified.targetVersion);
if (classified.status === "unsupported" || classified.status === "malformed") {
  console.error(classified.reason ?? "unsupported");
  process.exit(2);
}

let artifact;
try {
  const rows = lines.slice(1).map((line) => JSON.parse(line));
  const restore = catalog.createRestore(headerRow, { recovery: "strict", validation: "current" });
  for (const row of rows) restore.decodeRow(row);
  artifact = restore.finish();
} catch (err) {
  console.error("INVALID: 解码/迁移失败: " + (err?.message ?? err));
  process.exit(2);
}

try {
  // 额外用当前安装的 Session 做一次语义校验（surface 折叠 / 消息投影）
  Session.fromRestore(SessionId(artifact.header.id), artifact.events, artifact.header,
    SessionLogOffset(artifact.inheritedEventCount), "detached");
} catch (err) {
  console.error("INVALID: Session.fromRestore 失败: " + (err?.message ?? err));
  process.exit(2);
}
console.log("VALID: id=" + artifact.header.id, "version=v" + artifact.header.version,
  "events=" + artifact.events.length, "inherited=" + artifact.inheritedEventCount);

if (canonical) {
  let mismatches = 0;
  const encodedHeader = JSON.stringify(catalog.encodeCurrentHeader(artifact.header, artifact.inheritedEventCount));
  if (encodedHeader !== lines[0]) {
    mismatches += 1;
    console.log("HEADER not canonical:\n  encoder " + encodedHeader + "\n  file    " + lines[0]);
  }
  artifact.events.forEach((event, index) => {
    const encoded = JSON.stringify(catalog.encodeCurrentEvent(event));
    if (encoded !== lines[index + 1]) {
      mismatches += 1;
      if (mismatches < 4) console.log("ROW " + index + " not canonical:\n  encoder " + encoded + "\n  file    " + lines[index + 1]);
    }
  });
  console.log(mismatches === 0
    ? "CANONICAL: every row byte-identical to DSH encoder output"
    : "NON-CANONICAL rows: " + mismatches);
  if (mismatches > 0) process.exit(3);
}
