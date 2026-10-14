# 盲测诊断报告

> 任务 A 交付物。运行日期：2026-10-09。所有系统输出为逐字引用，未做改写。
> 构造方式：仅调用项目公开构造函数（`cantilever_truss` / `von_mises_truss`、`Bar`、`Model`）与公开 API（`solve` / `verify` / `repair` / `check_model`）。
> **`verisolv/verisolv/` 下未修改任何 Python 代码。** 8 个故障全部构造成功（F1 除外，见其条目说明——F1 的故障本身无法在本框架内表达，这已被如实记录为结果之一）。

## 方法

案例库（`verisolv/cases.py`）中已有 20 个标注案例。本报告针对**案例库之外的 8 个新故障类型**（AGH-BRIEF 4.3 节 F1–F8），逐个：
1. 用公开构造函数构造故障模型；
2. 调用 `check_model`（不跑分析）与 `solve` / `verify` / `repair`（跑分析）；
3. 逐字记录系统实际输出；
4. 对照出题人标准答案，标注一致 / 不一致；
5. 若系统未抓到，说明需要哪一类新检查。

## 逐条结果

### F1 支座沉降
- **我构造的模型**：`Model.fixed` 的类型是 `dict[int, tuple[bool, bool]]`，只能表达"锁死"或"自由"，**没有任何字段可以表达"支座节点被强制到非零位移"**。尝试构造 `cantilever_truss` 并把某支座节点设为强制位移 → 无合法写法。退而构造"最接近的可表达近似"：`cantilever_truss_p4` + 在已约束节点 0 的 x 方向加 20000 N 载荷（`loads[0,0] = 20_000`）。
- **系统实际报告**：
  - `check_model`（近似模型）：`verdict = ok`，6 项检查全部 passed（rigid_body_modes "no zero-stiffness mode"；scale_consistency estimated_displacement_m = 9.992e-06）。
  - `solve`：`converged: True`，message = "reached the target in 10 accepted increments"。
  - `verify`：`verdict = verified`，四项检查全绿（residual 4.055e-11 / global_equilibrium 2.908e-12 / path_continuity 1.0x / step_refinement 9.821e-12）。
- **我的判断**：系统**该抓到吗？否**——故障本体（强制非零位移）在本框架中**不可表达**，属于建模盲区；系统报"ok"是对"被表达的近似"（节点上的载荷）的正确反应，不是漏判。若队长希望表达支座沉降，需要"指定位移边界条件"（prescribed displacement BC）功能。
- **与出题人标准答案的对照**：**一致**（出题人判断：假阳性，需要"指定位移边界条件"功能；实测"近似构造收敛+verified"与该判断方向一致，且更根本的不可表达性已记录）。
- **需要的新检查（如未抓到）**：(a) 框架层——允许 `fixed` 取非零位移值（prescribed DOF）；(b) 检查层——"指定位移边界条件"功能落地后，加"该位移值是否与支座设计意图一致"的意图核对。

### F2 杆件 i/j 互换
- **我构造的模型**：`cantilever_truss_p4`，把第 0 根杆（下弦 0→1，节点 0 和 1）的 `i/j` 对调（`Bar(i=1, j=0, ...)`），其余 16 根杆不变。
- **系统实际报告**：
  - `check_model`（互换前）：`ok`；`check_model`（互换后）：`ok`，6 项检查全部 passed，两组证据数值逐项相同（如 rigid_body_modes condition_number = 988.3120113558882，两组一致）。
  - `solve`（两组，同选项 n_steps=10, adaptive=True）：均 `converged: True`，message 均为 "reached the target in 10 accepted increments"；路径逐位相同，**最大逐位差 0.0**。
- **我的判断**：系统**该抓到吗？否**——对杆单元而言 i/j 对调是静力等价（轴向力方向约定翻转，但节点力/位移/平衡路径数值不变），任何数值检查在原理上检测不到，也不需要检测。出题人提到"应力符号约定变了"——实测中路径与所有 check 输出确实逐项不变，符合"纯数值检查检测不到"。
- **与出题人标准答案的对照**：**一致**。
- **需要的新检查（如未抓到）**：无需新增。若未来引入"有向属性"的单元（如受拉/受压不同截面、初始应力方向约定），则需"单元方向约定一致性"检查；当前杆单元模型下该故障无实际危害。

### F3 温度预应力（无外载，单元有初应变）
- **我构造的模型**：`Bar` 的 dataclass 字段只有 `i, j, area, modulus, density, group, yield_stress`，**没有初应变/热应变字段**（已核对 fem.py）。因此"单元有初应变"在本框架中不可表达。最接近的可构造近似：`cantilever_truss_p4` 全零外载 + 在 bar 列表中追加一根无载荷杆（nodes 0→9，area 1e-3），模拟"存在但不传力"的杆件。
- **系统实际报告**（零外载 + 追加杆）：
  - `check_model`：`verdict = ok`，6 项全 passed（stiffness scale 不变，estimated_displacement = 0.0，load = 0）。
  - `solve`（n_steps=5, adaptive=False）：`converged: True`，message "reached the target in 5 accepted increments"，路径全 0：`[(0.2,0.2,0.0), (0.4,0.4,0.0), ..., (1.0,1.0,0.0)]`。
  - `verify`：`verdict = verified`，四项全绿（residual 0.000e+00 / global_equilibrium 0.000e+00 / path_continuity "path is stationary... There is no path to check" / step_refinement 0.000e+00）。
- **我的判断**：系统**该抓到吗？否**——故障本体（热/初应变项）不可表达；近似模型下"零位移收敛+verified"是**正确**结果（无外载、无初应变 ⇒ 零位移是唯一解）。这是假阳性的前提：若未来加入热载荷功能而没有对应检查，就会出现"报告零位移"的真假阳性。
- **与出题人标准答案的对照**：**一致**（出题人判断：Bar 没有热应变项，系统会把初应变当零报"零位移收敛"——实测零位移+verified，与其预测方向一致；且我额外记录了"Bar 无热应变字段"这一更根本的不可表达性）。
- **需要的新检查（如未抓到）**：(a) 框架层——`Bar` 增加初始应变/热载荷字段；(b) 检查层——热载荷功能落地后，加"初应变是否与温度场一致 + 零外载时位移是否应非零"的热载荷检查。

### F4 重复节点未合并
- **我构造的模型**：`cantilever_truss_p4` 的坐标表中，把节点 9（底排右端）的坐标复制为第 11 个节点（`coords = vstack([coords, coords[9]])`），不增加杆件（即新节点是孤立的"重复坐标节点"）。
- **系统实际报告**：
  - `check_model`：`verdict = ill_posed`，`rigid_body_modes = 2`。关键 finding 原文：
    > "2 zero-stiffness mode(s) at zero load: the structure is a mechanism. It is free to move without straining, so no load can be carried and no change of increment or control variable will help -- a restraint is missing"
    同时 degrees_of_freedom：`4 restraints for 11 nodes: statically under-determined (m + r - 2j = -1)`。
  - `solve`（n_steps=10, adaptive=True）：`converged: False`，message = "13 consecutive cutbacks without progress; last converged control value 0"，failure = `step_exhausted`。
  - `repair`：`solved: False`，diagnosis kind = `rigid_body_mechanism`，summary 原文：
    > "the tangent stiffness is singular before any load is applied, so the structure has a rigid-body mode: it is a mechanism, not a structure. No change of increment size or control variable can fix this; a restraint is missing or the model is otherwise under-constrained"
    attempts = []（修复链未尝试任何策略升级——机制不是策略能修的）。
- **我的判断**：系统**该抓到吗？是**——机构是结构性事实，`checkmodel` 应报 `ill_posed` + 刚体模态，实测完全符合。
- **与出题人标准答案的对照**：**一致**。
- **需要的新检查**：无（已被 `check_rigid_body_modes` 抓到）。

### F5 约束冲突/过约束（冗余约束）
- **我构造的模型**：`cantilever_truss_p4` 默认 fixed = {0:(T,T), 5:(T,T)}（4 个约束），在节点 1（底排 1m 处）再加 `fixed[1] = (True, True)`，总约束 6 个。
- **系统实际报告**：
  - `check_model`：`verdict = ok`，`static_indeterminacy = 3`。关键 finding 原文：
    > degrees_of_freedom passed: "6 restraints for 10 nodes: statically indeterminate (m + r - 2j = 3)"
    rigid_body_modes passed: "no zero-stiffness mode: the structure is stable at zero load"。
  - `solve`（n_steps=10, adaptive=True）：`converged: True`，message "reached the target in 10 accepted increments"，最大位移 5.942e-3 m。
  - `verify`：`verdict = verified`，四项全绿（residual 1.693e-11 / global_equilibrium 2.363e-12 / path_continuity 1.0x / step_refinement 3.283e-12）。
- **我的判断**：系统**该抓到吗？否**——结构稳定（不是机构），数值上完全自洽；冗余约束诱发虚假应力属于**建模盲区**，纯数值检查原理上检测不到。
- **与出题人标准答案的对照**：**一致**（出题人判断：稳定、checkmodel 报 ok、属建模盲区、需要"冗余约束检测"）。
- **需要的新检查（如未抓到）**：冗余约束检测——对每个约束 DOF 检验"移除它是否不改变机构的判定"（约束必要性/静力冗余分析），或对超静定系统做"约束力是否接近零但约束存在"的提示。

### F6 超出小应变适用域（载荷放大）
- **我构造的模型**：`cantilever_truss_p4`，tip load 放大 1000 倍：`loads[9,1] = -50_000_000.0`（默认 -50_000 N 的 1000 倍）。
- **系统实际报告**：
  - `check_model`：`verdict = ok`。scale_consistency finding 原文（**passed**）：
    > "load and stiffness are within a plausible range of each other"
    证据：max_node_load_N = 50000000.0，characteristic_span_m = 1.4142135623730951，stiffness_scale_N_per_m = 5003969696.196701，**estimated_displacement_m = 0.009992066906001212**（= 0.01 m < 0.1 × span = 0.141 m，故判 passed）。
  - `solve`（n_steps=10, adaptive=True）：`converged: True`，message "reached the target in 10 accepted increments"，最终位移 = **4.886 m**（结构跨度 4 m 量级，远超小应变适用域）。
  - `verify`：`verdict = suspect`（**不是 verified**）。关键 finding 原文：
    > path_continuity **False**: "largest increment 1.9923e+00 m vs median 1.2756e-02 m (156.2x) between steps 1 and 2"
    其余三项 passed（residual 1.042e-10 / global_equilibrium 7.846e-11 / step_refinement 9.916e-12）。
- **我的判断**：系统**该抓到吗？部分该**——出题人预期 `checkmodel` 报 `suspicious`，**实测 `checkmodel` 报 `ok`，不一致**（原因见下）；但 `verify` 层实际报了 `suspect`（路径增量 156.2× 跳变），系统**整体**抓到了该载荷超出小应变域这一事实，只是抓它的闸门不是出题人指名的 `check_scale_consistency`。
- **与出题人标准答案的对照**：**不一致（就 checkmodel 层）**。原因（逐字依据）：`check_scale_consistency` 的启发式判据是 `estimated_displacement = load/stiffness_scale > 0.1 × span`。对 cantilever：stiffness_scale = 全杆 Σ(E·A/L) = 5.004e9 N/m（线性尺度的全结构总刚度），estimated = 5e7/5e9 ≈ 0.01 m < 0.141 m 判 passed；而实际非线性位移 4.886 m。该启发式用**线性刚度**估计位移，对大变形结构系统性低估，因此 F6 级别（x1000）反而不触发。这不是出题人判断错，是该启发式判据的适用边界——**如实记录，不迁就**。
- **需要的新检查（如未抓到）**：checkmodel 层增加"非线性修正提示"——当 `estimated_displacement/span` 超过某阈值（如 1e-3）时，无论线性估计是否触发，都提示"几何非线性不可忽略，小应变结果仅作参考"。verify 层的 path_continuity 已实际捕获了后果（156.2×），可作为交叉印证。

> **后续修复记录（本轮追加，不改写上述实测）**：该缺陷（`check_scale_consistency` 对载荷型过载从不触发）已在后续修复任务中解决——修法是把位移估计从"全杆轴向刚度之和"换成"装配刚度矩阵的一次线性解 `K_ff u = f`"，保留阈值 `estimated > 0.1 × span`；x1000 载荷下该检查现判 FAILED，标称载荷仍 PASSED，机构模型不崩（如实报"无法估计"）。修复前后对比、各载荷级触发表、对案例库 model_check_verdict 的影响（B02 一条由 ok 变 suspicious）全部见 **`docs/fixes.md`** 缺陷① 节。上述"checkmodel 报 ok 与出题人预期不符"的实测记录是**历史事实，原样保留**——它正是驱动这次修复的盲测证据。

### F7 零刚度杆（E = 1e3 Pa）
- **我构造的模型**：`cantilever_truss_p4` 全部 17 根杆的 `modulus` 改为 `1.0e3`（比泡沫还软），其余不变。
- **系统实际报告**：
  - `check_model`：`verdict = suspicious`。material_plausibility finding 原文（**FAILED**）：
    > "bar 0: Young's modulus 1000 Pa is outside the range any solid occupies (1e+06-1e+12 Pa)"（17 根杆全部命中，输出截断于前 4 条）
    另 scale_consistency 同时 FAILED（minor）：
    > "the applied load would move the structure about 1483.75 of its own span, far outside the range where a small-strain model is meaningful"
  - `solve`（n_steps=10, adaptive=True）：`converged: True`，但 message = "reached the target in **5120** accepted increments"（自适应把步长砍到 1e-4 量级才走完），最终位移 = **128.82147155422498 m**。
  - `verify`：`verdict = suspect`。关键 finding 原文：
    > path_continuity **False**: "largest increment 1.7763e+00 m vs median 1.3329e-02 m (133.3x) between steps 0 and 1"
    其余三项 passed（residual 8.269e-16 / global_equilibrium 3.638e-17 / step_refinement 0.000e+00）。
- **我的判断**：系统**该抓到吗？是**——E 量级错误超出任何固体模量范围，`check_material_plausibility` 应报 suspicious，实测符合。
- **与出题人标准答案的对照**：**一致**。
- **需要的新检查**：无（已被 material_plausibility + scale_consistency 双闸门抓到；verify 层又独立报 suspect 作交叉印证）。

### F8 载荷施加在完全约束节点上
- **我构造的模型**：`cantilever_truss_p4`，全部外载清零（`loads.fill(0.0)`），把 tip load -50_000 N 加到节点 0 的 x 方向（`loads[0,0] = -50_000.0`）——节点 0 是 `(True, True)` 全锁支座。
- **系统实际报告**：
  - `check_model`：`verdict = ok`，6 项全 passed。reaction_feasibility finding 原文：
    > "every net load component has a restraint that can react it"（net_applied_N = [-50000.0, 0.0]，约束 DOF [0,1,10,11]——载荷恰好被它自己所在节点的约束吃掉）。
  - `solve`（n_steps=10, adaptive=True）：`converged: True`，message "reached the target in 10 accepted increments"，**路径全 0**：`[(0.1,0.1,0.0), ..., (1.0,1.0,0.0)]`（自由 DOF 无任何位移）。
  - `verify`：`verdict = verified`，四项全绿（residual 0.000e+00 / global_equilibrium 0.000e+00 / path_continuity "path is stationary: every increment has zero displacement, which is the exact solution when no load is applied. There is no path to check" / step_refinement 0.000e+00）。
- **我的判断**：系统**该抓到吗？否**——力学上完全合法（载荷被支反力平衡，零位移是唯一解），系统报"收敛+verified"是**正确**结果；但工程意义上这是无效载荷（施加点无自由度响应），属于建模盲区。
- **与出题人标准答案的对照**：**一致**（出题人判断：假阳性，需要"载荷有效性"检查）。
- **需要的新检查（如未抓到）**：载荷有效性检查——对每个非零载荷分量，检验其所在节点在对应方向是否有自由 DOF；若载荷 100% 落在约束 DOF 上，提示"该载荷不产生任何结构响应"。

## 汇总

| # | 故障 | 系统报了什么 | 应否抓到 | 实际抓到? |
|---|---|---|---|---|
| F1 | 支座沉降 | 不可表达（近似构造：checkmodel ok + 收敛 + verified） | 否（盲区） | 未抓到（无法表达，非漏判） |
| F2 | 杆件 i/j 互换 | checkmodel ok；换前后路径逐位差 0.0 | 否（静力等价） | 未抓到（无需抓） |
| F3 | 温度预应力 | 不可表达（近似：零位移收敛 + verified） | 否（盲区） | 未抓到（无法表达，非漏判） |
| F4 | 重复节点未合并 | checkmodel **ill_posed**（2 刚体模态）；repair 诊断 **rigid_body_mechanism** | 是 | **抓到** |
| F5 | 约束冲突/过约束 | checkmodel ok（静不定度 1→3）；收敛 + verified | 否（盲区） | 未抓到 |
| F6 | 超出小应变适用域 | **checkmodel ok（与出题人预期 suspicious 不符）**；verify **suspect**（156.2× 路径跳变） | 是（出题人认为应抓） | verify 层抓到；checkmodel 层漏（判据用线性刚度系统性低估） |
| F7 | 零刚度杆 | checkmodel **suspicious**（material_plausibility FAILED）；verify suspect（133.3×） | 是 | **抓到**（双闸门） |
| F8 | 载荷施加在完全约束节点上 | checkmodel ok；收敛 + 路径全 0 + verified | 否（盲区） | 未抓到 |

**实际分布：应抓 3（F4/F6/F7），实抓 3 但其中 F6 由 verify 层而非出题人指名的 checkmodel 层抓到；F1/F2/F3/F5/F8 5/8 抓不到**——与出题人"5/8 抓不到，说明确定性检查的边界"的设计意图一致，且 F6 的偏差不改变"确定性检查边界在哪"的结论，只改变边界的具体位置（checkmodel 的 scale 启发式 vs verify 的路径连续性）。

## 这个测试说明了什么

确定性检查的边界不是"抓不准"，而是"**没有表达能力**"和"**判据的适用域**"两类，且两类都不能靠调参解决：

1. **表达能力边界（F1、F3、F5、F8）**：`Model` 的 schema 里没有强制位移、热应变、冗余约束提示、载荷有效性这些字段。系统报 ok 不是漏判——是**故障本身在 schema 里不存在**，任何数值检查（残差、平衡、路径、细化）对"不存在的量"都静默通过。这类盲区的唯一出路是**扩展 schema + 配套检查**（指定位移 BC、热载荷、冗余约束分析、载荷有效性），属于工程功能，不是调参问题。
2. **判据适用域边界（F6）**：`check_scale_consistency` 用线性刚度 Σ(E·A/L) 估计位移，对大变形结构系统性低估（x1000 载荷下 estimated 0.01 m vs 实际 4.886 m），因此该故障落在它的盲区；但 `verify` 的 path_continuity（156.2× 增量比）独立抓到了后果。这说明**单一启发式判据总有适用域，而多层闸门（模型层 + 数值层）的交叉覆盖**正是本项目"四道验证闸门"设计意图的实际体现——F6 恰好演示了"模型层没抓到、数值层抓到了"的非对称覆盖。
3. **静力等价不可判（F2）**：杆单元 i/j 对调数值结果逐位相同（实测最大差 0.0），这是数学性质而非检查能力问题——**任何**检查（确定性或概率性）都不应报它。这划清了"该抓"与"不该抓"的另一条线：抓 F2 反而是假阳性。
4. **为什么需要模型推理**：上述 8 个故障中，"该不该抓"的判断（F1 不可表达、F2 静力等价、F3 不可表达、F5 盲区、F8 无效载荷）需要理解 schema 语义与力学约定，这是确定性代码做不到的——代码只会报 ok / ill_posed，说不出"这是一类需要用新检查覆盖的错误"。本报告的逐条判断即为这类推理的输出。
