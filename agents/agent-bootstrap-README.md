# agent-bootstrap

One-command setup for Codex and Oh My Pi: plugins, agent config, custom skills, and unified behavioral constraints.

## Usage (new machine)

### PowerShell (Windows)

```powershell
git clone https://github.com/M1zukiri/agent-bootstrap.git $HOME/agent-bootstrap
cd $HOME/agent-bootstrap
.\install.ps1
# Edit ~/.omp/agent/settings.json to set your shellPath
```

### Bash (Linux/macOS/Git Bash)

```bash
git clone https://github.com/M1zukiri/agent-bootstrap.git ~/agent-bootstrap
cd ~/agent-bootstrap
./install.sh
# Edit ~/.omp/agent/settings.json to set your shellPath
```

### Universal install (any agent)

For any agent environment (Codex, Claude Code, OpenClaw, OpenCode, ...), follow **[INSTALL.md](INSTALL.md)**: the agent checks compatibility, installs, and verifies the result itself. `install.ps1` / `install.sh` are OMP-only quick paths.

- **8 plugins** from the official Claude Code marketplace (security-guidance, commit-commands, code-review, nvidia-skills, ralph-loop, frontend-design, superpowers, playground)
- **11 skills**:
  - color-palette — 1589 palette schemes from 《配色设计速查手册》 (CMYK/RGB from printed color codes)
  - [storage-analyzer](https://github.com/KKKKhazix/khazix-skills) — disk space analysis with tri-color cleanup (macOS/Windows)
  - [neat-freak](https://github.com/KKKKhazix/khazix-skills) — end-of-session knowledge reconciliation (docs + CLAUDE.md + memory)
  - [pua](https://github.com/tanweai/pua) — productivity pressure system to prevent agent complacency
  - [pdf](https://github.com/anthropics/skills/tree/main/skills/pdf) — PDF generation with proper formatting (Anthropic official)
  - [skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator) — generate custom skills from natural language (Anthropic official)
  - grill-me — relentless interview questioning for design/plan review
  - [docx](https://github.com/anthropics/skills/tree/main/skills/docx) — Word document generation (Anthropic official)
  - [xlsx](https://github.com/anthropics/skills/tree/main/skills/xlsx) — Excel spreadsheet generation (Anthropic official)
  - [pptx](https://github.com/anthropics/skills/tree/main/skills/pptx) — PowerPoint generation (Anthropic official)
  - [frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design) — distinctive UI design direction before code (Anthropic official)
- **Unified AGENTS.md** — 9-section behavioral constraints, distributed to both `~/.codex/AGENTS.md` (Codex) and `~/.omp/agent/AGENTS.md` (Oh My Pi)
- **Agent config** (theme, TUI, compaction, memory, tool policies)

## AGENTS.md sections

1. 先思考再编码 — surface assumptions, expose tradeoffs, default skepticism
2. 简洁优先 — minimum code, no speculation
3. 外科手术式修改 — touch only what's needed
4. 目标与执行纪律 — verifiable success criteria + real-time todo discipline
5. 准确性与推理效率 — cite `file:line`, mark inferences, proportional reasoning
6. 版本号与 Git 仓库管理 — `A.B.C` versioning, mandatory git init, conventional commits
7. 文件操作纪律 — timestamped headers, backups, delete authorization, checkpointing
8. 配置安全 — no secrets in public repos, no unauthorized tool-config changes
9. 中文写作规范 — bilingual thinking + Chinese typesetting

## ⚠️ PUBLIC REPO — NO SECRETS

This repository is public. Never commit:

- API keys, tokens, or passwords
- `settings.json` with real paths (use the template)
- `.gitconfig` or proxy settings
- `auth.json`, `config.toml`, or any Codex credential files
- Any file containing credentials, even in comments

## Structure

```
agent-bootstrap/
├── AGENTS.md                   # 9-section unified behavioral constraints (Codex + OMP)
├── INSTALL.md                  # Universal cross-agent install workflow
├── README.md
├── install.sh                  # Bash bootstrap script
├── install.ps1                 # PowerShell bootstrap script
├── config/
│   ├── config.yml              # Agent config (symlinked or copied)
│   └── settings.template.json  # Template — fill shellPath manually
├── extensions/
│   └── pua/                    # PUA OMP extension (failure counter + /pua-* commands)
└── skills/
    ├── color-palette/        # Palette schemes (SKILL.md + 11 references)
    ├── docx/SKILL.md              # Word generation (Anthropic official)
    ├── frontend-design/SKILL.md # Distinctive UI design (Anthropic official)
    ├── grill-me/SKILL.md       # Design review interview skill
    ├── neat-freak/             # Knowledge reconciliation (full dir with references)
    ├── pdf/SKILL.md            # PDF generation (Anthropic official)
    ├── pptx/SKILL.md           # PowerPoint generation (Anthropic official)
    ├── pua/SKILL.md            # Productivity pressure system
    ├── skill-creator/SKILL.md  # Generate skills from natural language
    ├── xlsx/SKILL.md            # Excel generation (Anthropic official)
    └── storage-analyzer/       # Disk space analysis (full dir with scripts + assets)
```