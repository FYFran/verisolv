# 可复现运行说明（reproduce.md）

> 别人拿到这个项目，怎么从零跑起来。所有命令均为本项目实测可跑的命令，未修改 `verisolv/verisolv/` 代码。

## 1. 环境要求

| 项 | 要求 |
|---|---|
| 操作系统 | Windows（本项目在 Windows + PowerShell 5.1 上实测） |
| Python | Python 3.14（提交文档不写死本机用户名/绝对路径；运行前确认 `python -c "import numpy"` 可用，版本 3.12+ 应兼容，核心仅依赖 numpy） |
| 依赖 | `numpy`（核心）。无其他第三方依赖（PyNiteFEA 仅用于 `runs/` 中的一次性交叉验证，非运行必需） |
| AGH（可选） | 仅当要跑 AGH 插件工具面时需要：Node ≥24.10（实测 24.16.0）+ pnpm 10.34.5 + MSVC（Windows 需编译原生模块 `agnes-system.node`） |
| 编码 | 全程设 `$env:PYTHONIOENCODING = "utf-8"`，避免 Windows 控制台乱码 |

## 2. 安装

```powershell
# 无 pip 包可装；直接把项目根加入 Python 路径即可（包在 verisolv/ 子目录）
Set-Location <项目根>\verisolv
& python -c "import verisolv, numpy; print('ok')"
```

## 3. 验证命令与预期输出

### 3.1 列出可用模型

```powershell
& "C:\...\python.exe" -m verisolv models
```
预期输出（JSON，`ok: true`）：
```json
{ "ok": true, "models": {
  "cantilever_truss": {"nodes":10,"bars":17,"free_dofs":[2,3,4,5,6,7,8,9,12,13,14,15,16,17,18,19],
                        "groups":["bottom","top","vertical","diagonal"],
                        "default_mass":209.25630585851522,"total_load":50000},
  "von_mises_truss":  {"nodes":3,"bars":2,"free_dofs":[5],"groups":["chord"],
                        "default_mass":1.5778304725159797,"total_load":20000}
}}
```

### 3.2 求解（浅拱，载荷控制）

```powershell
& "C:\...\python.exe" -m verisolv solve --model von_mises_truss --control load --n-steps 10
```
预期：`converged: false`（压过极限点），`failure` 非空，`limit_point_estimate` 存在。
退出码 = 1（表示"跑了，但答案不可信"，这是**结果**不是错误）。

### 3.3 验证

```powershell
& "C:\...\python.exe" -m verisolv verify --model von_mises_truss --control load --n-steps 10
```
预期：不收敛时 `verdict = not_converged`；收敛时 `verified`/`suspect`/`rejected` 之一。

### 3.4 完整闭环（修复）

```powershell
& "C:\...\python.exe" -m verisolv repair --model von_mises_truss --control load --n-steps 10
```
预期：`solved: true`，`conclusion` 给出极限载荷（约 7963.16 N），`peak_load` 字段存在，
策略升级链从 `load` 切到 `displacement_control`，`verdict = verified`。

### 3.5 模型检查（不跑分析）

```powershell
& "C:\...\python.exe" -m verisolv checkmodel --model von_mises_truss
```
预期：`verdict = ok`（或 `suspicious`/`ill_posed`），`findings` 逐条列出。

### 3.6 案例库（20 例，较慢）

```powershell
& "C:\...\python.exe" -m verisolv cases
```
预期：JSON，含 `cases`（20 行）、`confusion`、`summary`；`summary` 中
`detectable_errors=9 detected=9`、`positive_controls=9 controls_clean=9`、
`repair_behaviour_correct=20`、`missed=[]`。
> 注意：`cases` 命令每个案例都跑 求解+验证+诊断+修复，**较慢，耐心等**（实测 < 1 分钟）。

## 4. AGH 插件安装（可选，跑 AGH 工具面时需要）

**本节所有路径均为占位符**，请替换为你自己的实际路径（本节不写死任何本机绝对路径）：

- `<AGH源码根>` — Agnes Harness 仓库根目录（`https://github.com/AgnesAI-Labs/agnes-harness`）
- `<项目根>` — 本项目根目录（含 `verisolv/` 包与 `agnes-plugin/`）
- `<Python>` — Python 3.12+ 解释器，需 `numpy`

插件文件：`<项目根>/verisolv/agnes-plugin/index.mjs`（薄适配层，注册 6 个工具，逻辑全在 Python 包内）。

```powershell
# 在 AGH 里安装/更新本插件（AGH 会按内容哈希快照插件；改插件需重装并经人工确认）
Set-Location <AGH源码根>
node packages\cli\dist\local\agnes.mjs package inspect "file:./agnes-plugin"
node packages\cli\dist\local\agnes.mjs package add file:./agnes-plugin
# 确认状态（实测已安装并运行）
node packages\cli\dist\local\agnes.mjs package status
# 期望：@hackathon/verisolv-agnes-plugin@0.1.0 desired=enabled actual=running trusted=true
```

> 插件来源必须用**相对形式** `file:./agnes-plugin`（相对于 AGH 的工作区解析）。
> 用绝对路径会报 `_agnes/v1/packages.inspect params: Expected union value`。
> 安装/启用需要人工在 Web UI（或真实 TTY）确认——AGH 在没有 TTY 时**不会**代替你同意。

插件环境变量（在 AGH 配置或调用环境设置）：
- `VERISOLV_ROOT` = `<项目根>`（含 `verisolv/cli.py` 的目录）
- `VERISOLV_PYTHON` = `<Python>` 解释器路径（默认 `python`）

安装后 AGH 会话内可调用 6 个工具：`verisolv_models` / `verisolv_solve` / `verisolv_verify` /
`verisolv_repair` / `verisolv_checkmodel` / `verisolv_cases`。

## 5. 交叉验证（一次性，非运行必需）

`runs/cross_validation.log` 由 `tools/cross_validate.py` 生成，与独立库 **PyNiteFEA 3.2.0** 对照。
**复现该 log 需要额外安装**：

```powershell
& <Python> -m pip install "PyNiteFEA==3.2.0"
```

> **注意两个易错点**：
> 1. PyPI 上的 `pynite` 是**另一个包**（Fortnite API 封装），正确的包名是 `PyNiteFEA`。
> 2. `tools/cross_validate.py` 用 `TINY_I = 1e-14` 把框架单元模拟成两力杆。
>    **这个值不能随意改**——它是最小化"用框架单元模拟桁架"所引入弯曲柔度的手段，
>    改大误差会上一个数量级。敏感性依据见 `docs/REVIEW-BRIEF.md` 的 I-敏感性扫描表。

求解器与验证器本身**不依赖** PyNiteFEA。

## 6. 已知不可复现点（如实说明）

- `runs/` 下的 `physics_validation.txt` / `closed_loop.txt` / `case_library.*` 是**已产出的证据快照**，
  数值可被上面的命令重新跑出（确定性：同输入同结果），但**文件本身不随包再跑生成**——
  复核请重跑命令 3.2–3.6，对比 `runs/` 快照。
- **哪些数字必须逐位一致、哪些允许有小差异**：
  - **必须一致**（确定性算法，无随机性）：`cases` 的全部计数（20 / 9 / 9 / 9 / 20 / 0）、
    `check_physics.py` 的闭式解相对误差（~1e-16）、`cross_validate.py` 的相对差（6.8e-8）。
  - **允许小差异**：**极限载荷的采样值**。它是位移控制路径上**离散采样点的最大值**，
    随步长变化——40 步 7957.60 N、120 步 7962.69 N、400 步 7963.01 N、闭式解 7963.2 N。
    差异在**千分之一量级即为正常**，不是复现失败。
- **依赖版本**：Python 3.12+ 与 `numpy`；交叉验证另需 `PyNiteFEA==3.2.0`。
  本项目的 `numpy` 版本未 pin——核心包只用基础线性代数（`linalg.solve` / `svd` / `norm`），
  跨版本行为稳定。

