# 修复记录（fixes.md）

> 第二轮任务：修 3 个缺陷，然后重新验证，证明修复没有破坏任何既有结果。
> 改动范围严格限于任务书第 6 节点名的三处。所有数字逐字取自实际运行输出，未编造。

## 改动范围自查（验收 #7 硬性）

| 文件 | 改动前 LastWriteTime | 改动后 | 改动内容 |
|---|---|---|---|
| verisolv/verisolv/checkmodel.py | 2026/10/9 23:03:53 | 未再改 | 缺陷① check_scale_consistency |
| verisolv/verisolv/cli.py | 2026/10/9 23:04:15 | 未再改 | 缺陷② cmd_cases |
| agnes-plugin/index.mjs | 2026/10/9 23:04:25 | 未再改 | 缺陷③ verisolv_cases 描述 |

**未改动**：fem.py / solver.py / verify.py / repair.py / cases.py（20 案例定义）/ models.py / optimize.py / sections.py / __init__.py / __main__.py——本轮回归全程只调用这些文件，时间戳保持 2026/10/9 14:12 至 22:19 原值，零改动。

## 缺陷① check_scale_consistency 实际失效（最重要）

### 问题
位移估计式 estimated = max_load / sum(E*A/L, 全部杆)，分母是"全杆轴向刚度之和"（悬臂 17 杆 = 5.004e9 N/m），不是结构刚度（尖端实际感受 5.63e6 N/m），差约 890 倍。后果：载荷型过载从不触发，只抓到刚度崩塌（E x1000、零刚度杆）。

### 根因
分母取所有杆刚度之和而非"载荷作用路径上的结构刚度"。悬臂尖端位移由最外 4 段主导，但分母把 17 根杆全加进来，对载荷型过载系统性低估 890 倍。

### 修法
把位移估计从"全杆刚度之和"换成"装配刚度矩阵的一次线性解 K_ff u = f"（np.linalg.solve，不调用非线性求解器，不继承任何 Newton/路径机制）：
- 线性区精确（nominal 估计/实际 = 1.001）；大变形时高估约 2 倍（x1000 = 2.132），高估是警告方向，可用（队长候选精度表，"线性解在 x1000 下 9 m vs 实际 4.89 m，差 2.1 倍"）。
- 奇异矩阵不崩：机构（F4 那种）让 K_ff 数值奇异（SVD 末/首比 1.38e-17，低于 1e-12 阈值），先做 svd 检测；奇异则如实报"无法估计"（evidence.cannot_estimate=True，不判 FAIL，不双重计数 check_rigid_body_modes 的职责）；精确奇异再套一层 LinAlgError 兜底。
- Finding 数据结构不变：仍返回 check / passed / severity / detail / evidence。
- 历史写进 docstring：说明该检查"曾经是死的、被盲测发现"，2026-10-09 修复，阈值 0.1*span 保留并说明理由。

### 修复前后实测对比（tools/acceptance_check.py + 载荷级扫描）

| 验收项 | 修复前 | 修复后（实测） |
|---|---|---|
| x1000 载荷 -50,000,000 N | PASSED（错，估计 9.99e-3 m） | FAILED，est = 8.884216309282005 m |
| 标称载荷 -50,000 N | PASSED | 仍 PASSED，est = 0.008884216309282005 m |
| F4 机构模型 | np.linalg.solve 会抛 LinAlgError 崩 | check_model 正常返回 ill_posed，scale_consistency 报 "cannot be estimated"，无异常 |

### 各载荷级触发情况表（span = 1.414 m，阈值 0.1*span = 0.1414 m）

| 载荷 | 修复后估计位移 | 与阈值 0.1414 m 比较 | 结果 |
|---|---|---|---|
| -50,000 N | 0.008884 m | 小于 | PASSED |
| -500,000 N | 0.088842 m | 小于 | PASSED |
| -5,000,000 N | 0.888422 m | 大于 | FAILED |
| -50,000,000 N | 8.884216 m | 大于 | FAILED |

阈值"estimated 大于 0.1*span"保留未动：线性解在标称载荷下 0.0089 m，远小于 0.1414 m（PASS）；x1000 下 8.88 m，远大于 0.1414 m（FAIL）。两端都落在正确一侧，无需调整，未出现"什么都能过"或"什么都报警"。

## 缺陷② cases --strict 抛 KeyError

### 问题
运行 python -m verisolv cases --strict 输出 {"ok": false, "error": "'accuracy'"}，退出码 2。

### 根因
cmd_cases 里引用 data["summary"]["accuracy"]，但 summarise() 重构后已无 accuracy 键。核对了 cases.py 中 summarise() 的现有键：total_cases / detectable_errors / detected / detection_rate / missed / undetectable_by_design / undetectable_cases / unexpectedly_detected_anyway / positive_controls / controls_clean / controls_false_alarm / repair_behaviour_correct / repair_mismatch / as_expected / as_expected_of / by_expected_detector / by_layer / observed_label_counts / legacy_matched，确认 accuracy 不存在。

### 修法
按队长建议方向：--strict 检查三个列表，missed 为空 且 controls_false_alarm 为空 且 repair_mismatch 为空。任一非空则打印失败原因并 return EXIT_UNTRUSTWORTHY；三者全空则打印 {"strict": "passed"} 并 return EXIT_OK。没有重新引入 accuracy 键，避免退回被废弃的单一数字口径。

### 修复前后实测
- 修复前：{"ok": false, "error": "'accuracy'"} exit 2
- 修复后：{"ok": true, "command": "cases", "strict": "passed"} exit 0（见回归输出 #8）

## 缺陷③ 插件描述与实际不符

### 问题
index.mjs 中 verisolv_cases 描述写 eleven cases，实际为 20 个（正常 7 / 边界 4 / 失败 9）。

### 修法（逐句核对）
改为：

Run the labelled case library: twenty cases (7 normal, 4 boundary, 9 failure) whose root cause is known by construction, each carrying a deterministic expected outcome. Returns, per case, the ground truth, what the solver reported, the verification verdict, the model-check verdict, and whether the repair chain rescued it - plus a summary that separates errors something can detect from errors that are undetectable in principle: detectable_errors, detected, missed, undetectable_by_design, positive_controls, controls_clean, controls_false_alarm, repair_behaviour_correct, repair_mismatch. Use it to test a change to the solver, the diagnoser or the model checker, and to answer "how do you know your diagnosis is right?". The closed-form reference rows also print a per-case comparison against an analytical value - the only gate that can catch a wrong formulation, not just an inconsistent one.

逐句核对（对照 summarise() 实际键名与 CaseResult.to_dict() 字段）：
- "twenty cases (7 normal, 4 boundary, 9 failure)"：与 total_cases=20、failure 9 / normal 7 / boundary 4 分布一致
- 描述的 summary 字段 detectable_errors / detected / missed / undetectable_by_design / positive_controls / controls_clean / controls_false_alarm / repair_behaviour_correct / repair_mismatch：全部为 summarise() 现存键
- "closed-form reference rows ... against an analytical value"：与 R01 至 R03 的 analytical 字段（quantity / relative_error / passed）一致
- 新描述无"已不存在的字段"，全部陈述属实。

未重新安装插件（铁律 4：install 需 TTY 确认，由队长做）。只改源码，新版本待装。

## 第 4 节全部回归命令实际输出

### 1. python tools\check_physics.py（RESULT: PASS，exit 0）

    1) displacement control vs closed form
    apex drop v (m)      FEM P (N)    exact P (N)    rel.err
             0.0200         5958.4         5958.4   6.11e-16
             0.0800         3972.3         3972.3   4.58e-16
             0.1500        -7758.3        -7758.3   2.34e-16
    2) limit point: numerical peak 7,963.1 N @ v=0.04238 m; closed-form 7,963.2 N @ 0.04226 m; peak rel.err 5.44e-06
    4) adaptive load control: largest step jump 0.17816 m (median 1.683e-04 m, ratio 1,059x)
    RESULT: PASS

解析解对照：6.11e-16 / 4.58e-16 / 2.34e-16（完整值 6.105629e-16 / 4.579222e-16 / 2.344562e-16），与基线一致。

### 2. python tools\cross_validate.py（RESULT: PASS，exit 0）

    tip load 5.0 N : verisolv -0.000888 mm, PyNite -0.000888 mm, rel diff 6.794e-08
    RESULT: PASS

跨库交叉验证：6.8e-8（5 N 行 rel diff 6.794e-08）。

### 3. python tools\demo_closed_loop.py（exit 0）

    diagnosis: limit_point; repair [ACCEPTED] displacement_control, verdict=verified
    step_refinement: refined solution differs by 1.005e-15 (displacement) and 3.050e-14 (load factor)
    global_equilibrium: force imbalance 0.000e+00, moment imbalance 0.000e+00
    limit load found: 7,957.6 N @ 0.04351 m

步长细化相对差约 1e-15（满足基线 1e-10 要求）；全局平衡力/力矩残差 0.000e+00（满足 5.8e-10 要求）。

### 4. python tools\make_assets.py（exit 0）

    limit_load_N 7963.157468532207 ; branch_jump_m 0.1781558214183939 (ratio 1058.556)
    baseline_mass_kg 209.25630585851522 to best_mass_kg 128.71880205106532 (reduction 38.49%, 292 evals), verdict verified

### 5. python tools\run_case_library.py（exit 0）

    total_cases 20 ; detectable 9/9 ; undetectable_by_design 2 ; positive_controls 9/9 clean
    repair_behaviour_correct 20 ; repair_mismatch none ; missed none
    closed-form: R01 6.11e-16 / R02 4.58e-16 / R03 2.34e-16 (AGREES)

### 6. node tools\check_tool_text.mjs（exit 0）

全部 5 个工具文本面通过。verisolv_cases 显示 20 labelled cases [failure 9, normal 7, boundary 4]，detected 9/9、undetectable 2、positive controls 9/9、repair 20/20、missed none。

### 7. python -m verisolv cases（exit 0）

完整 JSON：summary = total_cases 20 / detectable_errors 9 / detected 9 / detection_rate 1.0 / missed none / undetectable_by_design 2 / positive_controls 9 / controls_clean 9 / controls_false_alarm none / repair_behaviour_correct 20 / repair_mismatch none / as_expected 18 of 18。

### 8. python -m verisolv cases --strict（exit 0）

    {"ok": true, "command": "cases", "strict": "passed"}
    ===STRICT EXIT:0===

不再 KeyError，退出码 0。

## 回归基线核对（改前 = 改后）

| 基线项 | 任务书要求 | 实测 | 一致 |
|---|---|---|---|
| 案例库总数 | 20 | 20 | 一致 |
| 可检测错误抓中 | 9/9 | detected=9 / detectable_errors=9 | 一致 |
| 原理不可检测 | 2 | undetectable_by_design=2 | 一致 |
| 阳性对照 | 9/9 干净 | controls_clean=9 / controls_false_alarm none | 一致 |
| 修复行为正确 | 20/20 | repair_behaviour_correct=20 / repair_mismatch none | 一致 |
| 漏抓 | 0 | missed none | 一致 |
| 解析解对照 | 6.106e-16 / 4.579e-16 / 2.345e-16 | 6.1056e-16 / 4.5792e-16 / 2.3446e-16 | 一致 |
| 跨库交叉验证 | 6.8e-8 | 5 N 行 rel diff 6.794e-08 | 一致 |
| 步长细化 | 1e-10 | 1.005e-15 / 3.050e-14 | 一致 |
| 全局平衡 | 5.8e-10 | 力/力矩 0.000e+00 | 一致 |

10 个基线数字无一变化。

## 特别检查：缺陷① 修复是否改变案例库结果

check_scale_consistency 修好后，B02_unit_slip_load_x1000 的 model_check_verdict 从 ok 变为 suspicious（model_check_findings 含 scale_consistency）。

原因：B02 是"载荷按 kN 写但读作 N（x1000）"，载荷 5e7 N。旧公式下估计位移 9.99e-3 m，小于阈值 0.141 m，判 ok（漏判）；新线性解给出 8.884 m，远大于 0.141 m，判 suspicious（抓到）。

这是修复的正确后果，不是回归破坏。B02 仍归 undetectable_by_design（其 root_cause 是 unit_slip，detectable_by=intent_only），但现被 diagnoser+verification+model_check 三层同时抓住，as_expected=false（与 run_case_library 输出中 B02 标 MISS 一致：它被多抓一层，不算 as_expected，但不属于漏判，missed 仍为空）。

其余 19 个案例的 model_check_verdict 逐一核对未变（逐字来自 cases --strict 完整 JSON 输出）：
- 所有正常/边界/A 类：ok（载荷不超过 5000 N 量级，线性解位移远小于 0.1*span）
- A07 / B04（机构）：ill_posed（scale_consistency 报 cannot_estimate，rigid_body_modes 主导）
- B03（E x1000）：suspicious，由 material_plausibility 命中而非 scale_consistency——E 放大 1000 倍反而让结构更硬、位移更小，scale_consistency 判 ok，只有 material_plausibility 抓到（E=1e12 Pa 超出任何固体模量上限）

## 改动文件清单（铁律 7）

本轮回归未再改动任何 .py / .mjs（三处修复在更早时点已落盘，本轮仅运行验证）：
- verisolv/verisolv/checkmodel.py（LastWriteTime 2026/10/9 23:03:53）
- verisolv/verisolv/cli.py（LastWriteTime 2026/10/9 23:04:15）
- agnes-plugin/index.mjs（LastWriteTime 2026/10/9 23:04:25）

新增辅助脚本（tools/，非改动范围）：acceptance_check.py（验证三项验收标准）。
新增交付：docs/fixes.md（本文件）、docs/blind-diagnosis.md F6 段已追加"后续修复记录"（不改写历史实测）。

## 第三轮：B02 表述更正（2026-10-09）

### 为什么原表述错了
缺陷①修复前，B02（载荷 ×1000）只被 diagnoser + verification 层顺带抓到，checkmodel 报 ok——所以当时文档在 B02 那一行把这次捕获定性为意外性质、而非系统的检测能力（插件输出的英文标注见 index.mjs L265，本轮已改写）。

缺陷①修复后，`check_scale_consistency`（改用装配刚度矩阵的一次线性解）在载荷 ×1000 时给出估计位移 8.884 m，远超 0.1*span=0.1414 m 阈值，判 suspicious——B02 现被三层系统性抓到（diagnoser + verification + model_check），不再是“意外”性质。

但任务书第 2 节实测（tools/acceptance_scale_fix.py）指出关键反例：

```
载荷 ×1   （-50,000 N）    scale_consistency PASSED  → 静默
载荷 ×10  （-500,000 N）   scale_consistency PASSED  → 静默   ← 关键反例
载荷 ×100 （-5,000,000 N） scale_consistency FAILED  → 抓到
载荷 ×1000（-50,000,000 N）scale_consistency FAILED  → 抓到
```

"任何量级的单位错误都会触发"是错的——×10 量级完全静默，只有大到超出小应变适用域的才触发。

### 准确表述（核心区分）
可检测的是"载荷超出结构适用域"这个后果，不是"单位写错"这个原因。
- B02 实例（×1000）：被 scale_consistency 系统性抓到（后果可检测），但抓它的理由不是识别出了单位错误。
- "单位写错"作为类别仍不可检测：×10 量级实测静默（-500,000 N → PASSED，-5,000,000 N → FAILED，tools/acceptance_scale_fix.py）。
- B02 仍归 undetectable_by_design（detectable_by=intent_only，类别层面）。

### 改动的 8 处（逐一）
| # | 文件 | 位置 | 改动 |
|---|---|---|---|
| 1 | agnes-plugin/index.mjs | L265 | 旧英文那一句 → "caught by scale_consistency once the load magnitude exceeds the small-strain regime; the category (unit slip) remains undetectable in principle: a x10 slip of the same kind is measured silent" |
| 2 | docs/AGH-BRIEF.md | L403 | 历史文档，不改原句，追加一行更正说明 |
| 3 | docs/test-cases.md | L13 | 代码块引用（工具输出本身已变，引用必须同步） |
| 4 | docs/test-cases.md | L21 | 长段落，改为"后果可检测、原因不可检测"区分 + ×10 静默实测 |
| 5 | docs/test-cases.md | L58 | 表格行，同上 |
| 6 | docs/test-cases.md | L71 | 尾部核对行，同上 |
| 7 | docs/verification.md | L59 | 代码块引用，同 #1 |
| 8 | docs/verification.md | L66 | 要点，同上 |
| 9 | README.md | L61 | 诚实声明第 2 条，同上 |

### 插件重装
agnes-plugin/index.mjs 已改源码，未重新安装（铁律 4：install 需 TTY 确认，由队长做）。新版本待装，改动仅在 L265 一句文案。
