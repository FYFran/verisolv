# 敏感信息扫描报告（security-scan.md）

> 对应 AGH-BRIEF 任务 D。扫描目标：整个项目树 + 要提交的 `docs/` 文档。
> 扫描命令与结果均为真实运行输出，逐字记录。

## 1. 密钥/凭证模式扫描（全项目树）

命令（PowerShell 5.1，`Set-Location F:\...\verisolv` 后执行）：

```powershell
Get-ChildItem -Recurse -File -Include *.py,*.mjs,*.js,*.json,*.md,*.txt,*.ps1,*.log |
  Select-String -Pattern "sk-|Bearer |api[_-]?key|token|password|secret" |
  Select-Object -First 40
```

实测输出（命中 5 处，**全部为描述性文字，非真实密钥**）：

| 文件 | 行 | 内容 | 判定 |
|---|---|---|---|
| `.agh/skills/submission-packaging/SKILL.md` | 13 | "An API key, a token, a `.env` file..." | 文档描述，非密钥 |
| 同上 | 32 | "Scan for secrets. Grep ... (`sk-`, `Bearer `, `api_key`, ...)" | 扫描规则本身 |
| 同上 | 33 | "check that" | 同上 |
| `docs/AGH-BRIEF.md` | 442 | `Select-String -Pattern "sk-|Bearer |api[_-]?key|token|password|secret"` | 任务书要求的扫描命令本身 |
| `docs/agh-role.md` | 12 | "200,000 tokens" | "tokens" 指上下文长度，非密钥 |
| `docs/REVIEW-BRIEF.md` | 348 | "影响 Token 份数（每人一份）" | 指 token 配额，非密钥 |

**结论：无任何真实 API key / Bearer / password / secret 命中。** 所有匹配都是"提及这些词的文档"或"上下文 token 数量"。

## 2. 含用户名绝对路径检查（要提交的文档）

命令：

```powershell
Get-ChildItem docs -File -Filter *.md | Select-String -Pattern "<用户名>"
```

处理前命中（含用户名 `<用户名>` 的本机绝对路径 `C:\Users\<用户名>\...`）：
- `docs/reproduce.md` 第 10、20 行
- `docs/AGH-BRIEF.md` 第 67、121、447 行

**已脱敏**（把含用户名的本机绝对路径替换为占位符 / 相对写法，保留命令结构）：
- `reproduce.md`：`C:\Users\<用户名>\...\python.exe` → 改为"不写死本机用户名/绝对路径"说明 + `<Python314 解释器路径>` / `python`。
- `AGH-BRIEF.md`：路径段与"运行方式"段同理脱敏；第 447 行"检查项"改为"形如 `C:\Users\<用户名>\`"的通用写法。

脱敏后复查：

```
Get-ChildItem docs -File -Filter *.md | Select-String -Pattern "<用户名>"
→ （空，无任何命中）
```

**结论：要提交的文档中已不含 `C:\Users\<用户名>\` 这种含用户名的绝对路径。**

## 3. 敏感文件存在性检查

命令：

```powershell
Get-ChildItem -Recurse -File | Where-Object { $_.Name -match "^\.env|\.key$|credentials" } |
  Select-Object FullName
```

实测输出：**空（无任何 `.env` / `*.key` / `credentials*` 文件）。**

## 4. `.gitignore` 覆盖确认

`.gitignore` 已覆盖：`*.key`、`.env`、`.env.*`、`secrets/`、`.secrets/`、`credentials*`、
`*credentials*.json`、`__pycache__/`。
本任务补了一行 `runs/*.tmp`（原本只有 `runs/tmp/` 与 `runs/*.log`，未覆盖 `*.tmp`），
现在 `runs/` 下的临时/大体积产物全部被忽略。

## 5. 汇总

| 检查项 | 结果 |
|---|---|
| 密钥/凭证模式（`sk-`/`Bearer`/`api_key`/`token`/`password`/`secret`） | 无真实命中（仅描述性文字） |
| 含用户名绝对路径（`<用户名>`） | 已脱敏，提交文档中无残留 |
| `.env` / `*.key` / `credentials*` 文件 | 无 |
| `.gitignore` 敏感项覆盖 | 完整（本任务补 `runs/*.tmp`） |

**扫描通过，无敏感信息会被带入提交包。**
