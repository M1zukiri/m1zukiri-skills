# Created: 2026-11-18 22:59:08
"""DSH 会话 .jsonl.zstd 容器工具（压缩 / 解压 / 帧信息）。

DSH 的 .zstd 不是普通 zstd 流，而是一串**完整、独立、可单独解压**的 zstd 帧顺序拼接：
  帧 1    = header 行（{"type":"session",...} + "\\n"）
  帧 2..N = 每次落盘的批次（若干事件行，行间 "\\n"，批尾 "\\n"）
帧参数（复刻 DSH 的 compressZstdFrame，Node zlib.zstdCompress 默认）：
  level 3、windowLog 21（帧头 04 58）、开 checksum、不写 content size（必须用 stream_reader 解）、无 dict id。
追加语义：新批次 append 一个新帧，不重压旧帧；所以只要按批生成独立帧，就能与 DSH 产物逐字节互操作。

用法:
  python dsh_pack.py compress   <in.jsonl> <out.jsonl.zstd> [--batch N]
  python dsh_pack.py decompress <in.zstd> <out.jsonl> [--strict]
  python dsh_pack.py info       <in.zstd>
"""
import argparse
import io
import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

LEVEL = 3
WINDOW_LOG = 21
MAGIC = b"\x28\xb5\x2f\xfd"


def _zstd():
    try:
        import zstandard
    except ImportError:
        raise SystemExit("缺少依赖：pip install zstandard")
    return zstandard


def _compressor():
    zstandard = _zstd()
    params = zstandard.ZstdCompressionParameters.from_level(
        LEVEL, window_log=WINDOW_LOG, write_checksum=1, write_content_size=0, write_dict_id=0)
    return zstandard.ZstdCompressor(compression_params=params)


def compress_frame(comp, payload):
    """流式压缩单帧：一次性 compress() 会写 content size 并缩小窗口，帧头就变了。"""
    zstandard = _zstd()
    obj = comp.compressobj()
    return obj.compress(payload) + obj.flush(zstandard.COMPRESSOBJ_FLUSH_FINISH)


def compress(text, batch=256):
    """按 DSH 布局压：帧 1 单独放 header 行，其余事件行按 batch 行一批一帧。"""
    lines = text.encode("utf-8").split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()                                   # 末尾换行不算一行
    if not lines:
        raise SystemExit("输入为空")
    comp = _compressor()
    frames = [compress_frame(comp, lines[0] + b"\n")]
    body = lines[1:]
    if body:
        batches = [body] if batch <= 0 else [body[i:i + batch] for i in range(0, len(body), batch)]
        for chunk in batches:
            frames.append(compress_frame(comp, b"\n".join(chunk) + b"\n"))
    return b"".join(frames)


def decompress(data, strict=False):
    """跨帧解压；末帧被截断时尽力恢复已完整解出的前缀。"""
    zstandard = _zstd()
    out = bytearray()
    reader = zstandard.ZstdDecompressor().stream_reader(io.BytesIO(data), read_across_frames=True)
    try:
        while True:
            chunk = reader.read(1 << 20)
            if not chunk:
                break
            out += chunk
    except zstandard.ZstdError:
        if strict:
            raise
        print(f"[warn] 尾部帧损坏或被截断，已恢复前 {len(out)} 字节明文", file=sys.stderr)
    return bytes(out)


def scan_frames(data):
    """结构扫描帧边界（魔数 + 帧头 + block 链 + checksum），不解压。返回 [(start, end, checksum, fcs_flag)]。"""
    frames, offset = [], 0
    while offset < len(data):
        start = offset
        if data[offset:offset + 4] != MAGIC:
            raise SystemExit(f"偏移 {offset} 处不是 zstd 帧魔数")
        offset += 4
        descriptor = data[offset]
        offset += 1
        fcs_flag = descriptor >> 6
        single_segment = (descriptor >> 5) & 1
        checksum = (descriptor >> 2) & 1
        dict_flag = descriptor & 3
        if not single_segment:
            offset += 1
        offset += {0: 0, 1: 1, 2: 2, 3: 4}[dict_flag]
        offset += {0: 0, 1: 2, 2: 4, 3: 8}[fcs_flag]
        while True:
            header = data[offset] | (data[offset + 1] << 8) | (data[offset + 2] << 16)
            offset += 3
            last = header & 1
            block_type = (header >> 1) & 3
            offset += 1 if block_type == 1 else header >> 3   # RLE 块只存 1 字节
            if last:
                break
        if checksum:
            offset += 4
        if offset > len(data):
            raise SystemExit(f"偏移 {start} 处帧体被截断")
        frames.append((start, offset, bool(checksum), fcs_flag))
    return frames


def cmd_compress(args):
    text = Path(args.inp).read_text(encoding="utf-8")
    raw = text.encode("utf-8")
    blob = compress(text, batch=args.batch)
    Path(args.out).write_bytes(blob)
    print(f"in {len(raw)} bytes -> out {len(blob)} bytes, frames={len(scan_frames(blob))}, "
          f"first frame header {blob[:6].hex()}")


def cmd_decompress(args):
    data = Path(args.inp).read_bytes()
    plain = decompress(data, strict=args.strict)
    if not plain:
        print("ERROR: 没有解出任何明文", file=sys.stderr)
        return 1
    Path(args.out).write_bytes(plain)
    lines = plain.count(b"\n")
    print(f"in {len(data)} bytes -> out {len(plain)} bytes, lines={lines}")
    return 0


def cmd_info(args):
    data = Path(args.inp).read_bytes()
    frames = scan_frames(data)
    sizes = [end - start for start, end, _, _ in frames]
    plain = decompress(data[:sizes[0]], strict=True)
    header = json.loads(plain.decode("utf-8").split("\n")[0])
    print(f"frames: {len(frames)}  sizes(min/max/first): {min(sizes)}/{max(sizes)}/{sizes[0]}")
    print(f"checksummed: {all(f[2] for f in frames)}  fcs-present: {any(f[3] for f in frames)}")
    print(f"file: {len(data)} bytes, first frame header {data[:6].hex()}")
    print("header:", json.dumps(header, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="DSH .jsonl.zstd 多帧容器工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("compress", help="明文 JSONL -> DSH 多帧容器")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--batch", type=int, default=256, help="每帧事件行数；0=所有事件一帧")
    p.set_defaults(func=cmd_compress)

    p = sub.add_parser("decompress", help="DSH 多帧容器 -> 明文 JSONL")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--strict", action="store_true", help="末帧截断时报错而非前缀恢复")
    p.set_defaults(func=cmd_decompress)

    p = sub.add_parser("info", help="打印帧数/大小/校验位与 header")
    p.add_argument("inp")
    p.set_defaults(func=cmd_info)

    args = ap.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
