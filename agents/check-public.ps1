# 创建时间: 2026-11-20 13:12:08
# 用途: 扫描 agents/ 公开区是否写入了本机敏感信息。命中即失败（退出码 1）。
# 范围: agents/ 下除 local/ 之外的全部文件。
#       skills/ 不扫描——那是既有内容，公开前已人工复核；本脚本只守新增的规范区。
# 模式: 只保留高精度、低误报的两类。故意不查 UNC 与通用盘符路径：
#       JSON 转义会把示例路径写成 D:\\Work\\MyProject，无法与真实 UNC 区分。

$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$agentsRoot = Join-Path $repo 'agents'

# 用户目录路径：真实用户名泄露是最高风险
$userPath = '[A-Za-z]:\\Users\\[^\\\s"'']+'

# 非回环 IPv4：排除 127.*、0.* 、255.* 与 0.0.0.0
$ipv4 = '\b(?!127\.)(?!0\.)(?!255\.)(\d{1,3}\.){3}\d{1,3}\b'

$targets = Get-ChildItem $agentsRoot -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\local\\' -and $_.Extension -in '.md', '.json', '.yml', '.yaml', '.ps1', '.py' }

$hits = 0
foreach ($f in $targets) {
    $text = [System.IO.File]::ReadAllText($f.FullName, [System.Text.Encoding]::UTF8)
    $lines = $text -split "`r?`n"
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $rel = $f.FullName.Replace($repo + '\', '')
        if ($lines[$i] -match $userPath) {
            $hits++
            Write-Host ("[用户目录] {0}:{1}  {2}" -f $rel, ($i + 1), $lines[$i].Trim())
        }
        if ($lines[$i] -match $ipv4) {
            $hits++
            Write-Host ("[IPv4]    {0}:{1}  {2}" -f $rel, ($i + 1), $lines[$i].Trim())
        }
    }
}

if ($hits -eq 0) {
    Write-Host "check-public: 未发现敏感信息（扫描 $($targets.Count) 个文件）"
    exit 0
}

Write-Host ""
Write-Host "check-public: 发现 $hits 处疑似敏感信息，公开前必须处理" -ForegroundColor Red
exit 1
