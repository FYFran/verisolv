# AGH 在本项目中的作用

> 本文件对应赛事"技术信息"提交项，回答：AGH 提供了什么、Agnes 模型在哪些环节参与、
> 调用方式是什么。所有版本号与工具链均从本机实测取得，未推测。

## 模型声明

| 项 | 值 | 来源 |
|---|---|---|
| 名称 | agnes-3.0-flash | `agh sessions list` + 会话记录 seq 1（`modelSettings[].model`） |
| 版本 | agnes-3.0-flash（AGH 端点 `https://api.agnes-ai.cn/v1` 下发，无子版本号；`agh --version` 报 `agh 0.0.0`） | `agh --version` + 会话记录 |
| 上下文窗口 | 200,000 tokens（所有槽位统一） | 会话记录 seq 1 `modelSettings` |
| 使用环节 | 见下节"AGH 的作用" | 本任务 AGH 执行记录 |
| 调用方式 | 通过 AGH 智能体会话内的**工具调用**（`tool/call` → 插件工具 → Python 包）与 **shell**（PowerShell/Python）双通道 | AGH 插件 `verisolv/agnes-plugin/index.mjs` + 会话原始记录 |

## AGH 的作用

AGH 不是"调了个 API"的外壳，而是本项目的**运行与执行底座**，承担四个具体角色：

1. **工具注册面**：`verisolv/agnes-plugin/index.mjs` 把 6 个 Python 求解/验证/诊断/修复/案例工具
   （`verisolv_models` / `verisolv_solve` / `verisolv_verify` / `verisolv_repair` /
   `verisolv_checkmodel` / `verisolv_cases`）注册为 AGH 可调用工具。缺了 AGH，这些工具
   没有统一的调用与记录通道，"可供人工核查"的执行记录（赛事 3.2 项）不存在。
2. **执行记录与工具调用合规信号**：AGH 对每次 `tool/call` 记录 `ts`、哈希链与
   `verifier/signal`（tier-0 verdict）。
   **必须说清这是什么**：`verifier/signal` 是 **AGH 平台层对工具调用本身**的合规检查
   （格式、授权、可重放性），**不是**项目验证层对数值结果的第五道闸门。
   本项目的四道数值闸门全部在 `verify.py` 里，与 AGH 平台层处于**不同层面**，
   两者不应被读成"五道独立闸门"。
3. **诊断与策略判断的宿主**：盲测（任务 A）中"系统该不该抓到某故障"的判断，
   由 AGH 会话中的 Agnes 模型在工具结果之上完成——这是赛事 3.2(c)"Agnes 模型参与核心任务证据"的实质内容。
   确定性代码（`checkmodel.py`/`repair.py`）只会报 `ok`/`ill_posed`/`mechanism`，
   说不出"这是需要新检查覆盖的一类错误"。
4. **会话持久化与导出**：`agh sessions` / `agh export` 提供可人工核查的执行记录
   （本任务 `docs/agh-execution-record.raw.jsonl` 即由此导出）。

**缺了 AGH 会少哪一环**：少"可供人工核查的模型执行记录 + 模型层判断"这两环。
求解器本身（`verisolv/` 包）可独立运行，但赛事 3.2 要求上传的 AGH 执行记录、
以及"模型参与核心任务"的证据链，只能由 AGH 底座产生。

## 工具调用链（至少一条完整，带输入输出）

完整链见 `docs/agh-execution-record.md`"完整工具调用链示例 1（F4）"。此处摘录关键节点：

```
verisolv_checkmodel(F4_model)
  → verdict=ill_posed, rigid_body_modes=2
  → "2 zero-stiffness mode(s) at zero load: ... a restraint is missing"
模型判断（AGH 会话内）：机构是结构性事实，应抓 → 抓到
verisolv_solve(F4_model)
  → converged=False, failure=step_exhausted,
    "13 consecutive cutbacks without progress; last converged control value 0"
verisolv_repair(F4_model)
  → solved=False, diagnosis.kind=rigid_body_mechanism,
    "No change of increment size or control variable can fix this;
     a restraint is missing or the model is otherwise under-constrained",
    attempts=[]
模型判断：修复链正确地没有升级策略（机制不是策略能修的）
交叉印证：verisolv_cases 的 A07/B04 同类案例 caught_by=model_check+diagnoser
```

## 关键配置

| 项 | 值 |
|---|---|
| AGH 版本 | 0.0.0（`agh 0.0.0`） |
| Node 版本 | 24.16.0（v24.16.0） |
| 协议 | `_agnes/v1` |
| 插件 | `verisolv/agnes-plugin/index.mjs`（AGH 插件，注册 6 个 verisolv 工具；薄适配层，所有逻辑在 Python 包内） |
| 存储 | SQLite（`node:sqlite` 3.53.0，journal_mode=wal，`agh doctor storage` 通过） |
| 模型端点 | `https://api.agnes-ai.cn/v1`（比赛 Key 仅授权 agnes-3.0-flash 一个模型） |
| 会话 preset | standard-windows |
| 会话 key | `445e4c18-e8ef-4ce2-b167-12def9584fde` |
