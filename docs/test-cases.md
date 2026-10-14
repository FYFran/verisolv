# 测试样例（正常 / 边界 / 失败 三类）

> 数据来源：`verisolv_cases`（AGH 工具）2026-10-09 实测输出，与 `runs/case_library.log` / `runs/case_library.json` 一致。
> 本文件为赛事"测试样例"提交项。所有数字逐字取自工具输出，未改写。

## 总览（逐字取自 verisolv_cases 输出）

```
verisolv case library: 20 labelled cases run  [failure 9, normal 7, boundary 4]

detectable errors caught : 9/9
undetectable by design   : 2  B01_load_direction_reversed, B02_unit_slip_load_x1000
  of those, caught anyway: B02_unit_slip_load_x1000 -- caught by scale_consistency once the load magnitude exceeds the small-strain regime; the category (unit slip) remains undetectable in principle: a x10 slip of the same kind is measured silent
positive controls clean  : 9/9
repair acted correctly   : 20/20
missed                   : none
```

- 20 个案例 = 正常 7 + 边界 4 + 失败 9。
- 可检测错误 9/9 抓中；阳性对照 9/9 干净；修复链 20/20 行为正确；漏抓 0。
- **两条"原理上检测不到"的错误**（`B01_load_direction_reversed` 载荷方向反向、`B02_unit_slip_load_x1000` 单位量级写错）被 summary 明确点名：它们的数值完全自洽，只是答错了问题。其中 **B02 的实例（×1000 量级）被 `scale_consistency` 在位移超出小应变适用域时系统性抓到，但"单位写错"这一类别本身仍不可检测**（`caught anyway: B02`）——抓到的是"位移远超小应变域"这一后果，而非"单位写错"这个原因；实测 ×10 量级的同类滑移完全静默（`tools/acceptance_scale_fix.py`：`-500,000 N → PASSED` 静默，`-5,000,000 N → FAILED`）。

## 正常类（7 条）

| # | 案例 | 为什么属正常 | 系统实际观测 | 它证明了什么 |
|---|---|---|---|---|
| 1 | A04_tiny_load_regression | 极小载荷（50 N）回归守卫 | converged_verified（verified） | 灾难性抵消 bug 修复后的回归守卫：必须保持"收敛+验证通过" |
| 2 | A05_tinier_load_regression | 更小载荷（5 N）回归守卫 | converged_verified（verified） | 同上，更极端的量级 |
| 3 | N01_nominal_cantilever_service_lo… | 悬臂 20 kN 端部载荷（40% 原值） | converged_verified（verified） | 普通工况：必须收敛并验证；若系统误报，错的是系统不是结构 |
| 4 | N02_nominal_arch_below_limit | 浅拱 4 kN（约极限载荷 7.96 kN 的一半） | converged_verified（verified） | 远低于极限点：平衡存在且在该分支唯一 |
| 5 | R01_reference_apex_force_at_0.02m | 位移控制至顶点下挠 0.02 m | converged_verified（verified） | 顶点力对照解析解，相对误差 **6.11e-16** |
| 6 | R02_reference_apex_force_at_0.08m | 位移控制至 0.08 m | converged_verified（verified） | 解析解对照，相对误差 **4.58e-16** |
| 7 | R03_reference_apex_force_at_0.15m | 位移控制至 0.15 m | converged_verified（verified） | 解析解对照，相对误差 **2.34e-16** |

解析解对照是**唯一**能区分"公式本身写错"的检查（其余闸门或复用求解器自身装配、或重跑同一套代码），三条 R 案例在容差 1e-9 内全部 AGREES。

## 边界类（4 条）

| # | 案例 | 为什么属边界 | 系统实际观测 | 它证明了什么 |
|---|---|---|---|---|
| 1 | E01_boundary_load_exactly_at_limit | 载荷恰好压在极限点 7963.16 N | limit_point（repair 升级到位移控制） | 极限点刀刃：切线在解本身奇异；系统必须说出哪类结果发生，而不是静默报一个数 |
| 2 | E02_boundary_zero_load | 参考载荷恰为零 | converged_verified（verified） | 收敛判据分母 `max(force, 1N)` 避免 0/0；退化输入下机制存活 |
| 3 | E00_boundary_just_below_limit | 极限载荷下方 1%（7883.5 N） | converged_verified（verified） | 刀刃一侧：平衡存在可达，必须收敛并通过 |
| 4 | E03_boundary_just_above_limit | 极限载荷上方 1%（8042.8 N） | converged_unverified（suspect） | 刀刃另一侧：无平衡存在，"识别出的失败"是诚实结果；在此报"收敛"是系统最危险的行为 |

**薄弱处如实说明**：边界类只有 4 条，是三类中数量最少的一组。赛事要求三类齐全，本库已齐全但边界覆盖相对薄。

## 失败类（9 条）

| # | 案例 | 为什么属失败 | 系统实际观测 | 它证明了什么 |
|---|---|---|---|---|
| 1 | A01_limit_point_baseline | 载荷控制压过极限点 | limit_point | 极限点：载荷控制无法越过，诊断正确命名 |
| 2 | A02_limit_point_shallower | 更浅拱 + 8 kN | converged_unverified（suspect） | 浅拱逃到远端分支"收敛"，由验证层（路径不连续）抓到 |
| 3 | A03_limit_point_fine_steps | 40 步细步仍压极限点 | limit_point | 步长细化救不了极限点（与诊断结论一致） |
| 4 | A06_divergence_single_step | 全载荷一步 + 极小迭代预算 | divergence | 残差增长型发散，区别于极限点 |
| 5 | A07_singular_mechanism_zero_load | 移除支座约束 → 机构 | rigid_body_mechanism | 零载荷时切线奇异 = 机构的签名，区别于极限点；修复链正确地不升级 |
| 6 | B01_load_direction_reversed | 载荷符号翻转为 +Y | converged_verified（verified） | **原理上检测不到**：收敛、自洽、可复现，只是答错问题；只能由模型层意图核对覆盖 |
| 7 | B02_unit_slip_load_x1000 | 载荷按 kN 写但读作 N | converged_unverified（suspect） | **类别层面原理上检测不到**；B02 实例（×1000 量级）被 `scale_consistency` 在位移超出小应变适用域时系统性抓到，但"单位写错"这一类别本身不可检测——实测 ×10 量级同类滑移完全静默（`tools/acceptance_scale_fix.py`：`-500,000 N → PASSED`，`-5,000,000 N → FAILED`） |
| 8 | B03_material_typo_E_x1000 | E 写成 210 TPa | converged_verified（verified），model-check = **suspicious** | 材料量级错误：求解器与验证器均盲目（算术全对），只有模型检查器的 `material_plausibility` 报出 |
| 9 | B04_missing_x_restraint | 两个基点 x 向全释放 | rigid_body_mechanism | 机构（无约束平移）：model-check + diagnoser 双层抓中 |

## 四项检查并非完全独立（必须说明）

四项验证检查（residual / global_equilibrium / path_continuity / step_refinement）中，**residual 与 global_equilibrium 都调用了同一个 `assemble()`**——如果单元公式本身错了，两项会同时通过。真正独立的外部对照是**解析解**（R01–R03，6e-16 量级）和**独立库 PyNiteFEA 交叉验证**（`runs/cross_validation.log`，6.8e-8）。本库的"verified"更准确的定位是**自洽性检查 + 外部对照**的组合，不是四道相互独立的闸门。

## 与 AGH-BRIEF 第 2 节关键数字的逐字对照

- 案例库：`正常 7 / 边界 4 / 失败 9` —— 与"案例库 20 个案例：正常 7 / 边界 4 / 失败 9"一致。
- `可检测错误 9/9 抓中，阳性对照 9/9 干净，修复链 20/20 正确，漏抓 0` —— 逐字一致。
- 解析解相对误差 `6.11e-16 / 4.58e-16 / 2.34e-16` —— 逐字一致。
- 两条"原理上检测不到"为 B01、B02；其中 B02 的实例（×1000 量级）被 `scale_consistency` 在位移超出小应变适用域时系统性抓到，但"单位写错"这一类别本身仍不可检测——实测 ×10 量级同类滑移完全静默（`tools/acceptance_scale_fix.py`：`-500,000 N → PASSED`，`-5,000,000 N → FAILED`）。
