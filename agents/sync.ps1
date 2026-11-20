# 创建时间: 2026-11-20 13:07:44
# 用途: 把 agents/AGENTS.md 分发到本机各 Agent 环境副本，并校验逐字节一致；
#       可选地检查所有已知项目的内联状态。
# 用法:
#   .\sync.ps1              分发 + 校验 + 项目内联检查
#   .\sync.ps1 -Check       只校验，不写入
#   .\sync.ps1 -SkipPublic  跳过分发前的敏感信息扫描
#   .\sync.ps1 -SkipProjects 跳过项目内联检查
# 回滚: 目标文件在覆盖前会保存为 <目标>.bak，或直接用 git 还原本仓库。

param(
    [switch]$Check,
    [switch]$SkipPublic,
    [switch]$SkipProjects
)

$ErrorActionPreference = 'Stop'

$repo   = Split-Path -Parent $PSScriptRoot
$source = Join-Path $repo 'agents\AGENTS.md'

if (-not (Test-Path $source)) { throw "找不到源文件: $source" }

# 本机各 Agent 环境的全局规范副本位置
$targets = @(
    (Join-Path $env:USERPROFILE '.dsh\AGENTS.md')
    (Join-Path $env:USERPROFILE '.omp\agent\AGENTS.md')
)

if (-not $SkipPublic) {
    $checker = Join-Path $PSScriptRoot 'check-public.ps1'
    if (Test-Path $checker) {
        Write-Host '--- 敏感信息扫描 ---'
        & $checker
        if ($LASTEXITCODE -ne 0) { throw 'check-public 发现敏感信息，已中止分发' }
    }
}

$sourceHash = (Get-FileHash $source).Hash
Write-Host "`n--- 分发 ---"
Write-Host ("源: {0}  ({1} B, {2})" -f $source.Replace($env:USERPROFILE, '~'), (Get-Item $source).Length, $sourceHash.Substring(0, 8))

$drift = 0
foreach ($t in $targets) {
    $dir = Split-Path -Parent $t
    if (-not (Test-Path $dir)) {
        Write-Host ("  [跳过] {0}  (目录不存在)" -f $t.Replace($env:USERPROFILE, '~'))
        continue
    }

    $rel = $t.Replace($env:USERPROFILE, '~')
    if (Test-Path $t) {
        $targetHash = (Get-FileHash $t).Hash
        if ($targetHash -eq $sourceHash) {
            Write-Host ("  [一致] {0}" -f $rel)
            continue
        }
        $drift++
        if ($Check) {
            Write-Host ("  [漂移] {0}  ({1} vs {2})" -f $rel, $targetHash.Substring(0, 8), $sourceHash.Substring(0, 8))
            continue
        }
        Copy-Item $t "$t.bak" -Force
        Copy-Item $source $t -Force
        Write-Host ("  [更新] {0}  (旧版已存为 .bak)" -f $rel)
    }
    else {
        $drift++
        if ($Check) {
            Write-Host ("  [缺失] {0}" -f $rel)
            continue
        }
        Copy-Item $source $t -Force
        Write-Host ("  [创建] {0}" -f $rel)
    }
}

Write-Host ''

# 项目内联状态检查（可选）
function Find-Python {
    foreach ($cand in @('python', 'python3', 'py')) {
        $cmd = Get-Command $cand -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        if ($cand -eq 'py') {
            $ver = & py -3 -c "import sys;print(sys.version_info[0])" 2>$null
            if ($ver -ne '3') { continue }
            return @{ Exe = 'py'; Args = @('-3') }
        }
        $ver = & $cmd.Source -c "import sys;print(sys.version_info[0])" 2>$null
        if ($ver -eq '3') { return @{ Exe = $cmd.Source; Args = @() } }
    }
    return $null
}

$projectCheckFailed = $false
if (-not $SkipProjects -and -not $Check) {
    $cli = Join-Path $repo 'skills\agents-profile\scripts\profile_cli.py'
    $listFile = Join-Path $PSScriptRoot 'profiles\local\projects.txt'
    if ((Test-Path $cli) -and (Test-Path $listFile)) {
        $py = Find-Python
        if ($py) {
            Write-Host '--- 项目内联检查 ---'
            $env:AGENTS_REPO = $repo
            $pyArgs = @($py.Args) + @($cli, 'check', '--all')
            & $py.Exe @pyArgs
            if ($LASTEXITCODE -ne 0) { $projectCheckFailed = $true }
            Write-Host ''
        }
        else {
            Write-Host '--- 项目内联检查: 跳过（未找到 Python 3） ---'
            Write-Host ''
        }
    }
}

if ($Check) {
    if ($drift -eq 0) { Write-Host '结果: 全部一致' ; exit 0 }
    Write-Host "结果: $drift 处与源不一致" -ForegroundColor Yellow
    exit 1
}

# 分发后复核
$bad = @()
foreach ($t in $targets) {
    if ((Test-Path $t) -and ((Get-FileHash $t).Hash -ne $sourceHash)) { $bad += $t }
}
if ($bad.Count -eq 0) {
    Write-Host '结果: 分发完成，全部副本与源逐字节一致'
    if ($projectCheckFailed) { exit 1 }
    exit 0
}
$bad | ForEach-Object { Write-Host "  仍不一致: $_" -ForegroundColor Red }
exit 1
