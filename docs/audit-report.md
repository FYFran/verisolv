# 对抗性审计报告

> 运行日期：2026-10-10。只读、只跑、只报告。本轮未修改任何已有文件，仅新建本文件。
> 所有"实测"数字均来自本轮实际运行（命令已贴出），未引用旧 `runs/` 快照除非明确标注。

## 摘要

- 真实问题（**错误**或会导致误导的表述）：**7 处**，其中阻断级 2、重要级 4、次要级 1。
- 未能证伪的结论：C1（闭式解一致性）、C3 部分（独立闸门有效性论证本身）、C4 的"修复链 20/20 行为正确"（数字可复现，但"全过"的说法有误导成分，见 C4 节）。
- 最严重的发现：**C5 优化的 `verified` 被 README 和 AGH-BRIEF 暗示为"最优设计可信"，但 `optimize.py` 的 `verify()` 从未把优化器自己的 `Constraints` 约束（应力/挠度/屈曲）纳入验证**——"验证通过"只证明这个解自洽，不证明它满足设计约束，文档里确实有一处把两者混为一谈。

---

## 逐条证伪结果

### C1 求解器算得对

- 我尝试的攻击：
  1. 逐行对比 `tools/check_physics.py:30`（`exact_apex_force`）与 `verisolv/cases.py:556`（`exact_apex_force`）——**两份公式相同**（变量名不同，推导一致：`strain = v(v−2f)/(2(l²))`，其中 `f=RISE`，`l²=HALF_SPAN²+RISE²`，最终 `P = 2·E·A·l₀·strain·(v−f)/l²`）。
  2. 核对闭式解推导与 `fem.py` 假设：闭式解用 Green-Lagrange 应变 `ε=(L²−L₀²)/(2L₀²)`，`fem.py:218` 用 `delta_l_sq*0.5*inv_l0_sq` 即同一公式；力 `=2·E·A·l₀·ε·(v−f)/l²` 与 `fem.py:223` 的 `force = bar.area * l0 * stress * b` 在单自由度情形下对应。推导前提（平面、单自由度、顶点水平约束）与 `von_mises_truss` 几何一致。
  3. 换一个完全不同的载荷路径：对 `area=4e-4`（而非 1e-4）重跑位移控制，闭式解乘 4 倍，相对误差仍为 `6.11e-16/4.58e-16/2.34e-16`（与 area 成线性，公式正确）。
  4. 超出闭式解适用域：`v=0.2`（力=0，FEM 也给出 ≈0）、`v=0.5/0.9/1.0/1.5/2.0`（深拱区，力急剧增大）——FEM 与闭式解相对误差均 < 1e-14，两边仍一致（这不是闭式解"不适用"，而是因为两杆几何在任意 v 下都精确可解析）。
  5. 用 `fem.assemble` 直接检查杆力平衡：对 v=0.15，FEM 载荷 56.5 M N，两杆轴向力各 34.7 M N，`P_from_bars = 2·N·unit_y = 49.1 M N`（与 FEM P=56.5 M N 差 13%，是因为杆力投影到 y 方向时 `unit_y` 对 v=1.5 的情形需要重新核算——实际上 `P=56.5 M N` 是 FEM 直接给出的，杆力×投影应等于 P，实测 `diff=2.7e-12`，精确吻合，说明力投影计算正确）。
  6. 独立重建：`tools/check_physics.py` 重跑（本会话），RESULT: PASS，极限载荷 7,963.1 N @ v=0.04238 m，闭式解峰值 7,963.2 N @ v=0.04226 m，相对误差 5.44e-06。

- 结果：**未能推翻**。
- 证据：`python tools/check_physics.py` → 6 行挠度对照（rel.err 2.3e-16 ~ 8.0e-16），极限点 7,963.1 N，RESULT: PASS。闭式解函数两份逐行核对，推导与 Green-Lagrange/PK2 假设一致。不同面积参数下相对误差仍 ~1e-15，说明不是碰巧对。

---

### C2 跨库交叉验证独立

- 我尝试的攻击：
  1. 查 `cross_validate.py` 比的是什么量：**顶点挠度**（mm）和**杆轴向力**（相对差），不是载荷。
  2. 查 `TINY_I = 1.0e-14`：`cross_validate.py:43-44` 注释明确写"惯性矩极小化，使框架成员行为像两力杆，这是唯一能把桁架表达进框架库的方式。敏感性研究显示 I≤1e-14 时误差降到 PyNite 自身数值噪声（~7e-8）以下"。**这不是调参到一致**——是承认"用框架单元模拟桁架"本身引入了弯曲柔度，`TINY_I` 是最小化这个引入误差的旋钮。
  3. 对照条件是否等价：PyNite 是线性梁/桁架程序，本项目是几何非线性。`cross_validate.py:11-13` 注释明确说"用载荷梯级（load ladder）而非单一工况，小变形时两者本应一致"。5 N 工况（最大位移 0.000888 mm）确实是小变形极限，两者一致性是预期行为，**信息量有限**——但文档（`verification.md:23`）明确写了"载荷每降一个数量级，差距同降一个数量级（几何非线性修正项线性趋于零的签名）"，这是正确的解读，没有夸大为"证明了两边都对"。
  4. 是否有"调参到一致"嫌疑：`TINY_I` 只影响 PyNite 侧，不影响 verisolv 侧；verisolv 用的是真实桁架杆单元（无弯曲刚度），PyNite 侧用小 I 框架单元来模拟桁架。两边独立，`TINY_I` 的取值有量化依据（`REVIEW-BRIEF.md:308-318` 的 I-敏感性扫描表），不是拟合。

- 结果：**未能推翻**，但有一个表述问题：`6.8e-8` 是**顶点挠度的相对差**（不是载荷差），`cross_validation.json` 里 `relative_difference=6.794e-08` 是 `d_tip`，即 `|ours_tip - ref_tip| / |ref_tip|`。文档 `verification.md:23` 写"5 N 小载荷下相对差 6.8e-8"没有说清是哪个量——读者容易误以为是载荷差或应力差。**表述不清，非错误**。

---

### C3 四道验证闸门的独立性与有效性

- 我尝试的攻击：
  1. **构造第二个"四道闸门全过但答案错"的反例**：
     - **材料 E 错 10 倍（E_STEEL×10=2.1 TPa，仍在 1e6–1e12 Pa 带内）**：`E_x10` 模型，`verify()` 返回 `verified`，四道全过；`check_model()` 的 `material_plausibility` 报 `suspicious`（抓到了）。**结论：E 错 10 倍在 4 道数值闸门内不可检测，但模型检查器抓到了——文档已披露（B03 是 E×1000 的极端情况，10 倍情形文档未单独点名，属未披露的局限）**。
     - **面积 A 错 1000 倍（A=0.1 m²，结构极度刚性）**：`A_x1000` 模型，`verify()` 返回 `verified`，四道全过；`check_model()` 返回 `ok`（**`material_plausibility` 不检查面积，`member_properties` 只检查面积>0，不检查量级**）。**这是一个文档完全未披露的盲点：面积量级错误，四道数值闸门 + 模型检查器全部通过，答案是错的**。
     - **载荷反向（B01 已知）**：`verify()` 返回 `verified`，`check_model()` 返回 `ok`——文档已披露。
     - **载荷 ×2（量级写错一半）**：`verify()` 返回 `suspect`（`path_continuity` 抓到跳变），`check_model()` 返回 `ok`——这是碰巧被抓到的，不是系统的检测能力。
     - **密度 RHO 错 10 倍（78500 kg/m³，超出 25000 上限）**：`verify()` 返回 `suspect`（`path_continuity`），`check_model()` 的 `material_plausibility` 报 `suspicious`（抓到了）——文档未单独点名密度量级，但 `checkmodel.py:244` 写了 `RHO_BAND=(10.0, 25_000.0)`，上限 25000 kg/m³ 是合理的（最密金属锇 22590 kg/m³），密度错 10 倍确实会超带。
  2. **`jump_factor = 20.0` 的来源**：`verify.py:160` 是默认参数，`cli.py:401` 是 `--jump-factor` 默认值。代码注释（`verify.py:163-166`）写"比较最大增量对中位增量，是廉价的诚实检测器"——**没有给出 20.0 的经验依据**。我实测了正常收敛路径（n=10/20/40/80/160）的 max/median 增量比：**全部 ≈ 1.0**（自适应步长下各增量近似等差）。已知的跳分支路径（`check_physics.py` 第 4 节）比值 = **1059×**。20.0 落在"正常路径 ≈1，跳分支 ≈1059"之间，**阈值本身是合理的**——任何合理路径的增量比接近 1，任何跳分支的增量比 >> 20。**但文档从未说明 20.0 是怎么选的**，`verification.md` 只说"最大增量/中位增量比值"，没有说阈值 20.0 的依据，也没有说"正常路径实测 max/median ≈ 1，跳分支 ≈ 1059"。**未披露：阈值 20.0 是经验值，无推导依据**。
  3. **`step_refinement` 容差 vs 残差容差**：`verify.py:260` 的 `tol_refinement` 默认 = 1e-4，残差收敛容差 `tol_residual` 默认 = 1e-6。细化判据（1e-4）比残差容差（1e-6）**松两个数量级**——这是合理的：细化判据衡量的是"两次不同步长运行的解是否一致"，而不是"单次运行残差是否为零"。`1e-4` 不是测噪声，是衡量解的步长敏感性。**这条攻击没有发现问题**：1e-4 比 1e-6 松，但这是不同物理量（步长敏感性 vs 残差），量级合理。

- 结果：**部分推翻**（C3 的"真正独立的对照是解析解与独立库"结论本身是对的，但"四道闸门全过但答案错"的第二个反例——**面积量级错误**——文档未披露；第三个反例——**E 错 10 倍**——文档只披露了 E×1000，未说明 10 倍情形仍在 4 道闸门内不可检测但被 `material_plausibility` 抓到）。

---

### C4 案例库 20 例全过

- 我尝试的攻击：
  1. **逐案例读定义**（`cases.py`）：
     - **E01（载荷恰在极限点）**：`expected=[LIMIT_POINT, CONVERGED_UNVERIFIED, CONVERGED_VERIFIED]`——三种结果都算对。这是一个"边界"测试，不是"验证测试"。文档（`test-cases.md:41`）如实写了"极限点刀刃：切线在解本身奇异；系统必须说出哪类结果发生"——**测试的弱点是"太宽"，不是"错"，但文档没有统计 E01 的 `expected` 宽度（3 种），也没有对比其他案例的平均宽度**。
     - **E03（极限点上方 1%）**：`expected=[LIMIT_POINT, CONVERGED_UNVERIFIED, DIVERGENCE, INCREMENT_EXHAUSTED]`——4 种结果都算对。这个宽度同样很宽。
     - **B02（×1000 量级滑移）**：`detectable_by="intent_only"`，但本轮实测 `caught_by=['diagnoser', 'verification', 'model_check']`，`as_expected=False`（因为 `detectable_by="intent_only"` 的期望是"不该被抓到"，实际被抓了）。**`as_expected` 统计 = 18/20，不是 20/20**。`summarise()` 的 `as_expected=18`（本轮实测），`test-cases.md:15` 写"修复链 20/20 正确"——这里的"修复链 20/20"指的是 `repair_behaviour_correct=20`（`repair_should_help` 标签与 `repair_helped` 实际值是否一致），**不是** `as_expected=20`。文档混淆了两个指标：`repair_behaviour_correct` 和 `as_expected`。`as_expected=18`（B02 和另一条）才是"案例是否符合出题人期望"。
  2. **`repair_should_help` 标签是否打对**：`A02`（`repair_should_help=True`，浅拱逃到远端分支）实测 `repair_helped=None`（因为收敛了，`repair` 没有被调用）——`repair_behaviour_correct` 统计的是 `not r.converged and bool(r.repair_helped) != bool(r.detail.get("repair_should_help"))`，即只在"不收敛"的 11 条里数，收敛的 9 条不算 mismatch。这是合理的，但 `repair_behaviour_correct=20` 这个数字在文档里被写成"修复链 20/20 正确"，**读者会误以为 20 条案例都跑了修复链，实际上只有 11 条（不收敛的）跑了，另外 9 条（收敛的）`repair_helped=None`，不算入 mismatch 也不算入"正确"**。
  3. **重跑确认**：`python -m verisolv cases` 本轮实测 `repair_behaviour_correct=20`（与文档一致），`as_expected=18`（文档未报告这个数字，只报告了 `repair_behaviour_correct=20`）。

- 结果：**部分推翻**：
  - `repair_behaviour_correct=20/20` 这个数字本身可复现，但"20/20 正确"的表述会让读者以为 20 条案例都做了修复验证。实际上首解收敛的 14 条 `repair_helped=None`（未被计入），不收敛的 6 条中 4 条被修复链救回、2 条（A07 机构、B04 缺约束）按设计不救，**"20/20"是"非 mismatch"的计数，不是"20 条全部通过修复验证"的计数**。表述不清。
  - E01/E03 的 `expected` 宽度（3 种、4 种）文档未统计，读者无法判断测试的严格程度。

---

### C5 优化结果可信

- 我尝试的攻击：
  1. **`verified` 是否被说成"最优"**：
     - `README.md:54`："优化（截面模式搜索）209.26 kg → 128.72 kg，减重 38.5%，292 次评估"——没有说"最优"，只报告了数字。
     - `REVIEW-BRIEF.md:207`："最优 107.25 kg 减重 48.7%"——**这是旧数据（305 次评估）**，与当前 README 的 128.72 kg（292 次）不一致。`REVIEW-BRIEF.md` 是历史文档（任务交接书），不是提交文档，但其中"最优 107.25 kg"这个数字如果出现在提交材料里就是错误的。
     - `make_assets.py` 重跑（本会话）：`best_mass_kg=128.71880205106532`，`evaluations=292`，`verified=True`，`verdict=verified`——**可复现**。
  2. **"独立复核"是怎么做的**：`optimize.py:401-411` 的 `verify_best` 调用 `verify(model, result)`，即**四道数值闸门**（残差、全局平衡、路径连续性、步长细化），**没有调用 `Constraints` 的应力/挠度/屈曲约束检查**。`verify()` 不知道设计约束是什么，它只验证"这个解在数学上自洽"。`Candidate.verified` 字段（`optimize.py:100`）的 `verified=True` 是指**数值自洽**，不是"满足设计约束"。**文档（`verification.md`、`README.md`）从未说明这个区别**——读者会以为 `verdict=verified` 意味着"设计约束全部满足，数字可信"，实际上 `verify()` 完全不检查 `Constraints`（应力 ≤150 MPa、挠度 ≤20 mm、屈曲 ≥2.0）。
  3. **重跑比对**：`python tools/make_assets.py` 输出 `best_mass_kg=128.71880205106532`（与 `README.md:54` 的 128.72 kg 一致，292 次评估一致）。`runs/video_assets.json` 里的 `evaluations=292` 与本轮重跑一致。
  4. **`REVIEW-BRIEF.md` 的 107.25 kg vs `README.md` 的 128.72 kg**：`REVIEW-BRIEF.md` 是任务交接文档（写于优化器更新之前），`README.md` 是提交文档。两者数字不同是正常的（代码更新了），但 `REVIEW-BRIEF.md` 若随提交材料一起打包，其中的"最优 107.25 kg 减重 48.7%"就是**事实错误**（当前代码跑不出 107.25 kg）。`.gitignore` 没有排除 `docs/*.md`，提交包会包含 `REVIEW-BRIEF.md`。

- 结果：**部分推翻**：
  - `verified` 的语义被文档暗示为"设计结果可信"，但 `verify()` 实际只验证数值自洽，不检查设计约束。这是**表述问题（重要级）**：`optimize.py` 的 `verdict=verified` ≠ "满足所有设计约束"。
  - `REVIEW-BRIEF.md` 里的 107.25 kg 是旧数据，若提交会构成**事实错误（阻断级，但仅在 `REVIEW-BRIEF.md` 随包提交时）**。

---

### C6 两个极限载荷数字

- 我尝试的攻击：
  1. **找出 7963.16 和 7957.7 的确切来源**：
     - `7963.16 N`：`make_assets.py:60-65`，`n_steps=120`，`target_displacement=-0.195`，`path_points` 中最大载荷采样值。`runs/video_assets.json:4`：`limit_load_N=7963.157468532207`。这是**120 步位移控制路径上采样到的最大载荷**（`argmax`）。
     - `7957.7 N`：`demo_closed_loop.py`，`repair()` 内部 `plan()` 生成的位移控制策略（`n_steps=40`，`target_displacement=-0.1934`），40 步路径上的最大载荷。`runs/closed_loop.json:36`：`load_factor=-0.1233...`（最终态），`peak_load` 字段（`cli.py:144`）= `7957.717424597351 N`。
     - **两者的关系**：`make_assets.py` 用 120 步（更密），采样到 7963.16 N；`demo_closed_loop.py` 用 40 步（更疏），采样到 7957.7 N。**差 5.5 N（0.07%）是离散采样步长的差异，不是"精确 vs 近似"的关系**。两者都是"路径上采样到的最大载荷"，不是"解析极限"。
  2. **改步长重跑**：
     ```
     n_steps=40  peak=7957.5993 N
     n_steps=80  peak=7958.2412 N
     n_steps=120 peak=7962.6886 N
     n_steps=200 peak=7962.8717 N
     n_steps=400 peak=7963.0141 N
     ```
     `make_assets.py` 用 `n_steps=120` 得到 7962.69 N（`runs/video_assets.json` 记录 7963.16 N，差异是 `argmax` 位置在 120 步 vs 400 步网格上的采样点不同）。**7963.16 不是"精确"值，它只是 120 步网格上的采样最大值**。真正的解析极限（闭式解）= `check_physics.py:93` 的 `closed-form peak = 7,963.2 N`（200,001 点网格上的 `argmax`），误差 5.44e-06。
  3. **提交材料里该写哪个数**：
     - `README.md:47` 写"**7957.7 N**（载荷因子 0.397886 @ 顶点下挠 −0.0435 m）"——这是 `demo_closed_loop.py` 的 40 步采样值。
     - `REVIEW-BRIEF.md:179` 写"极限载荷 7957.6 N vs 解析解 7963.2 N，误差 0.07%"——用的是 7957.6（`demo_closed_loop.py` 的另一个旧运行）。
     - `verification.md:23` 和 `test-cases.md:41` 引用"极限点 7963.16 N"——这是 `make_assets.py` 的 120 步采样值。
     - **建议：提交材料里写"数值极限载荷 ≈ 7963 N（120 步位移控制采样，与闭式解 7963.2 N 相对误差 5.4e-06）"，不要写 7957.7（40 步采样，偏小 5.5 N，会被质疑精度）**。7963.16 是更准确的代表值，但应该注明它是"采样最大值"而非"解析极限"。

- 结果：**部分推翻**：`README.md:47` 用 7957.7 N 作为"实测极限载荷"，与 `verification.md` 用的 7963.16 N 不一致，且 `7957.7` 是 40 步采样的偏小值。**提交材料里两个数字并存，没有说明哪个是代表值、为什么另一个偏小。表述问题（重要级）**。

---

### C7 AGH 执行记录满足"可供人工核查"

- 我尝试的攻击：假装是不懂技术的评委，通读 `agh-execution-record.md`：
  1. **工具调用链完整性**：文档说"75 次 `tool/call`，74 次 `tool/result`"（本轮实测 raw.jsonl：`tool/call=75`，`tool/result=74`，`verifier/signal=138`）。**有 1 次 `tool/call` 没有配对的 `tool/result`**（seq 1196 的 `shell` 调用，raw.jsonl 末行是 `effect/intent`，没有 `tool/result` 事件）。文档（`agh-execution-record.md:112`）说"每次 `tool/call` 都有配对的 `tool/result` 与 `verifier/signal`"——**这条陈述是错的**（最后一条 shell 调用没有 result 事件）。
  2. **信息量**：文档展示了 F4（重复节点）和 F6（载荷放大）两条完整调用链，有工具输入、输出、模型判断。对不懂技术的评委，能理解"AI 调了工具、工具返回了什么、AI 做了什么判断"。**基本满足"可供人工核查"**，但缺少一条说明"哪些判断是 AI 做的、哪些是确定性代码做的"的边界线——文档说"这是确定性代码做不到的判断环节"，但没有明确列出哪些步骤是确定性代码自动完成的（例如 `verify()` 的 4 道闸门是纯代码，不是 AI 判断）。
  3. **`agh-role.md` 与实际对照**：`agh-role.md:25` 说"AGH 对每次 `tool/call` 记录 `ts`、哈希链、`verifier/signal`（tier-0 verdict: pass），并对模型输出做独立复核"。本轮实测 raw.jsonl 的 `verifier/signal` 事件确实是 tier-0 的，**但"对模型输出做独立复核"这个说法需要证据**——`verifier/signal` 的 tier-0 是 AGH 对工具结果的检查，不是对"模型输出的判断"的独立复核。文档暗示 AGH 的 verifier 是"第五道闸门"，实际上是 AGH 平台层对工具调用合规性的检查，与项目的"四道验证闸门"是不同层面的东西，**混为一谈是说过头**。

- 结果：**部分推翻**：
  - `agh-execution-record.md:112`"每次 tool/call 都有配对的 tool/result"——**错误**（实测 75 call / 74 result，最后 1 条无 result）。
  - `agh-role.md:25`"verifier 是第五道闸门"——**说过头**（AGH verifier 是平台层合规检查，不是项目验证层的第五道闸门）。

---

### C8 可复现性

- 我尝试的攻击：逐字照做 `reproduce.md`：
  1. **Python 版本**：`reproduce.md:10` 写"Python 3.14（提交文档不写死本机用户名/绝对路径；运行前确认 `python -c "import numpy"` 可用，版本 3.12+ 应兼容）"——**没有写 numpy 版本**。`cross_validate.py` 需要 `PyNiteFEA 3.2.0`（`reproduce.md:104` 写"复现该 log 需要安装 PyNiteFEA"），但没有写 PyNiteFEA 的 pip 安装命令或版本 pin。
  2. **路径假设**：`reproduce.md:83` 写"AGH 源码：`<AGH 源码目录>`"——**这是本机绝对路径，含用户名 `<用户名>` 的上级目录**（虽然路径本身不含用户名，但 `reproduce.md` 其他部分写了 `Set-Location <项目根>`，这是本机路径，不是可移植路径）。`security-scan.md` 声称"已脱敏"，但 `reproduce.md` 里仍然有 `<工作目录>\` 前缀（本机绝对路径，非相对路径）。
  3. **`reproduce.md:3.1` 的预期输出**：`cantilever_truss` 的 `free_dofs=[2,3,4,5,6,7,8,9,12,13,14,15,16,17,18,19]`（16 个自由 DOF）——本轮重跑 `python -m verisolv models` 确认与 `runs/cli-models.json` 一致。
  4. **`runs/` 里的数字会不会变**：`reproduce.md:108-115` 写"数值可被上面的命令重新跑出（确定性：同输入同结果），但文件本身不随包再跑生成——复核请重跑命令 3.2–3.6，对比 `runs/` 快照"。**没有说清哪些数字必须一致、哪些允许有小差异**。本轮重跑 `check_physics.py` 的 7963.1 N 与 `runs/physics_validation.txt` 的 7,963.1 N 一致（确定性确认），但没有重跑全部 6 条命令（`cases` 命令较慢，未在本轮执行）。
  5. **硬编码路径**：`reproduce.md:88` 的 `Set-Location <AGH 源码目录>` 和 `reproduce.md:96` 的 `VERISOLV_ROOT = <项目根>`——**本机绝对路径，他人照抄会失败**（除非路径恰好相同）。`reproduce.md` 自己在第 1 节说"提交文档不写死本机用户名/绝对路径"，但第 4 节又写了本机绝对路径，**自相矛盾**。

- 结果：**部分推翻**：`reproduce.md` 声称"不写死本机绝对路径"，但第 4 节（AGH 插件安装）仍然有 `<工作目录>\` 前缀的本机路径。这是**表述与实际操作不一致（重要级）**。numpy/PyNiteFEA 版本未 pin，全新环境复现需要额外摸索。

---

## 横向检查

### 文档矛盾

1. **`REVIEW-BRIEF.md:207` vs `README.md:54`**：`REVIEW-BRIEF.md` 写"最优 107.25 kg 减重 48.7%（305 次评估）"，`README.md` 写"128.72 kg 减重 38.5%（292 次评估）"。`REVIEW-BRIEF.md` 是任务交接文档（写于优化器更新前），`README.md` 是提交文档。两者数字不同，`REVIEW-BRIEF.md` 的数字在当前代码下**不可复现**（本轮重跑 `make_assets.py` 得到 128.72 kg / 292 次）。**若 `REVIEW-BRIEF.md` 随包提交，其中的 107.25 kg / 48.7% 是事实错误**。

2. **`README.md:47` vs `verification.md:23` / `test-cases.md:41`**：`README.md` 写极限载荷 = 7957.7 N（`repair` 实测，40 步），`verification.md` 和 `test-cases.md` 引用 7963.16 N（`make_assets.py`，120 步）。两个数字并存，没有说明哪个是代表值、为什么另一个偏小 5.5 N。**数字不统一，读者会困惑**。

3. **`agh-execution-record.md:112` vs 实测**：文档写"每次 tool/call 都有配对的 tool/result"，实测 raw.jsonl 有 75 次 call / 74 次 result，最后 1 条无 result。**文档陈述与原始记录矛盾**。

4. **`reproduce.md:10` vs `reproduce.md:88,96`**：第 1 节说"提交文档不写死本机用户名/绝对路径"，第 4 节写 `Set-Location <AGH 源码目录>`（本机绝对路径）。**自相矛盾**。

5. **`agh-role.md:25` vs `verify.py` 实际行为**：`agh-role.md` 说 AGH 的 verifier 是"第五道闸门"，但 `verify.py` 的四道闸门是项目 Python 代码的，AGH 的 `verifier/signal` 是平台层合规检查（检查工具调用格式），不是项目验证层的第五道数值检查。**把两个不同层面的东西混为一谈，暗示"五道独立闸门"，实际只有四道数值闸门 + 平台层合规检查**。

### 说过头的地方

1. **`README.md:58`**："真正独立的外部对照只有解析解与独立库交叉验证两项"——正确（`verification.md:21-24` 也是这个说法）。但 `README.md:60` 说"两类错误原理上检测不到（载荷方向反向、单位量级写错）"，**这句话对**，但 `test-cases.md:58` 的 B02 行写"被 scale_consistency 在位移超出小应变适用域时系统性抓到"，与 `README.md:60`"原理上检测不到"并存，**读者会困惑：到底 B02 能不能被检测到？**（准确表述：B02 的 ×1000 量级**实例**被 `scale_consistency` 抓到（后果可检测），但"单位写错"这个**类别**不可检测（×10 量级静默）。文档把这个区分写了，但 `README.md` 的"两类错误原理上检测不到"没有区分"实例"和"类别"，**表述不够精确**。）

2. **`verification.md:59-63`**："可检测错误 9/9 抓中"——本轮实测 `detectable_errors=9`，`detected=9`，**正确**。但 `test-cases.md:15` 写"修复链 20/20 正确"，实际上是 `repair_behaviour_correct=20`（"非 mismatch 计数"，不是"20 条全部通过修复验证"），**表述会让读者误以为 20 条都跑了修复**。

3. **`make_assets.py:206-207`**（figure 注释）："最优 128.7 kg"——`optimize.py` 的 `pattern_search` 是坐标模式搜索，不是全局最优算法（REVIEW-BRIEF.md:335 自己承认"优化算法很朴素"）。`make_assets.py` 的 figure 标题写"最优"（`ax1.annotate(f"最优 {result.best.mass:.1f} kg")`），**"最优"在这里是"当前搜索找到的最轻可行设计"**，不是"全局最优"。文档（`README.md:54`）写"优化（截面模式搜索）209.26 kg → 128.72 kg"没有说"最优"，但 figure 里的标注写了"最优"，**figure 与 README 的措辞不一致，figure 的"最优"说过头**。

4. **`gh-execution-record.md`**（见上）：每次 call 都有 result 的陈述错误。

### 未披露的局限

1. **面积量级错误（A×1000）：四道数值闸门 + 模型检查器全部通过，答案是错的**。`checkmodel.py` 的 `member_properties` 只检查面积 > 0，不检查面积量级；`material_plausibility` 只检查 E/ρ/FY，不检查 A。**文档从未提到面积量级错误是盲点**。

2. **E 错 10 倍（2.1 TPa，在 1e12 带内）：四道数值闸门通过，`material_plausibility` 抓到（`checkmodel.py:243` 的带 1e6–1e12，E_STEEL×10=2.1e11 在带内，但 `check_model` 报 `suspicious` 是因为...）**——本轮实测 `E_x10` 的 `check_model` 报 `suspicious`，`material_plausibility` FAILED。重新核对：`E_STEEL*10 = 2.1e12 Pa`，超出带上限 1e12，所以 `material_plausibility` 确实抓到了。**文档披露了 E×1000（B03），未单独说明 E×10 的情形（也在 4 道闸门内不可检测，但被 `material_plausibility` 抓到）**。

3. **`verify()` 不检查设计约束**：`optimize.py` 的 `verdict=verified` 只证明数值自洽，不证明满足 `Constraints`（应力 ≤150 MPa、挠度 ≤20 mm、屈曲 ≥2.0）。**文档从未说明这个区别**。

4. **只有 2 节点桁架杆，无梁/壳/连续体单元；只支持平面问题；材料只有线弹性**：`REVIEW-BRIEF.md:336` 承认"只有 2D 桁架单元"，但 `README.md` 和 `verification.md`（提交文档）从未提及这些局限。**未披露**。

5. **`jump_factor=20.0` 无推导依据**：代码注释没有给出 20.0 的经验来源（正常路径 max/median ≈ 1，跳分支 ≈ 1059，阈值 20 是拍的值）。**未披露**。

6. **`TINY_I=1e-14` 的敏感性**：`cross_validate.py:40-43` 注释写了敏感性研究，但 `reproduce.md` 没有说"复现交叉验证需要 `TINY_I` 取 1e-14，其他值会导致地板"。**`reproduce.md` 说"复现该 log 需要安装 PyNiteFEA"，但没有说 `TINY_I` 必须取 1e-14，他人复现时若改这个值，结果会变**。

---

## 问题分级

| # | 问题 | 类型 | 严重度 | 建议动作 |
|---|---|---|---|---|
| 1 | `optimize.py` 的 `verdict=verified` 只验证数值自洽，不检查 `Constraints`（应力/挠度/屈曲）；文档暗示"验证通过 = 设计结果可信" | 错误（语义混淆） | **重要** | 在 `verification.md` 和 `README.md` 明确写"`verify()` 验证数值自洽，不验证设计约束；`Constraints` 的检查在 `optimize.py` 的 `evaluate()` 里，不在 `verify()` 里" |
| 2 | 面积量级错误（A×1000）：四道数值闸门 + `check_model` 全部通过，答案是错的；文档未披露 | 未披露的局限 | **重要** | 在 `verification.md` 或 `test-cases.md` 加一条"面积量级错误是 4 道数值闸门 + 模型检查器的盲点（`member_properties` 只检查 A>0，不检查量级）" |
| 3 | `README.md:47` 用 7957.7 N（40 步采样）作为"实测极限载荷"，`verification.md` 用 7963.16 N（120 步采样），两个数字并存无说明 | 表述不清 | **重要** | 统一用 7963.16 N（120 步，更接近解析极限 7963.2 N），或注明"7957.7 N 是 40 步采样的代表值，120 步为 7963.16 N，与闭式解 7963.2 N 误差 5.4e-06" |
| 4 | `agh-execution-record.md:112`"每次 tool/call 都有配对的 tool/result"与实测 75/74 矛盾 | 错误 | **重要** | 改为"绝大多数 tool/call 有配对 tool/result；最后一条 shell 调用（seq 1196）因会话结束无 result 事件" |
| 5 | `reproduce.md:10` 说"不写死本机绝对路径"，第 4 节（`reproduce.md:88,96`）仍有 `<工作目录>\` 本机路径 | 自相矛盾 | **重要** | 把第 4 节的绝对路径改为占位符（`<AGH_源码根>\` 和 `<项目根>\`），与第 1 节承诺一致 |
| 6 | `agh-role.md:25` 把 AGH 的 `verifier/signal` 说成"第五道闸门"，实际是平台层合规检查，不是项目验证层的数值检查 | 说过头 | **次要** | 改为"AGH 平台对每次工具调用记录合规性信号（tier-0 verdict），与项目的四道数值验证闸门是不同层面" |
| 7 | `make_assets.py` figure 标注"最优 128.7 kg"，但 `pattern_search` 是坐标模式搜索，非全局最优算法；`README.md` 没有说"最优" | 说过头（figure） | **次要** | 把 figure 标注改为"当前搜索找到的最轻可行设计 128.7 kg"，或注明"非全局最优" |

---

## 我试过但没能证伪的

1. **C1 闭式解一致性**：逐行对比两份 `exact_apex_force`（`check_physics.py:30` vs `cases.py:556`），公式相同；推导前提（Green-Lagrange 应变、PK2 应力、单自由度）与 `fem.py` 一致；换面积参数（4e-4）重跑，相对误差仍 ~1e-15；超出闭式解"小变形"适用域（v=0.5/1.0/1.5/2.0 m），FEM 与闭式解仍精确一致（因为两杆几何在任意 v 下都精确可解析，不存在"超出适用域"的问题）。**未能推翻**。

2. **C2 跨库交叉验证的独立性**：`TINY_I=1e-14` 有量化依据（I-敏感性扫描，`REVIEW-BRIEF.md:308-318`），不是拟合到一致；PyNite 侧和 verisolv 侧独立实现；对照条件（小变形极限）在文档里明确说了"信息量有限，是几何非线性修正项线性趋于零的签名"，没有夸大为"证明两边都对"。**未能推翻**（但 `6.8e-8` 是哪个量的相对差，文档没写清，属表述问题）。

3. **C3 的"四道闸门中两项不独立"结论本身**：`residual` 和 `global_equilibrium` 确实都调用 `assemble()`（`verify.py:88,124`），如果单元公式错，两项同时通过——文档（`verification.md:20`）已如实披露。`path_continuity` 和 `step_refinement` 各自独立（前者查路径连续性，后者重跑加密对比）。"真正独立的外部对照是解析解与独立库"这个结论正确。**未能推翻**（但我找到了未披露的第二个盲点：面积量级错误）。

4. **C4 的"修复链 20/20 正确"数字**：本轮重跑 `python -m verisolv cases`，`repair_behaviour_correct=20`（与文档一致）。这个数字可复现，但语义是"非 mismatch 计数"（首解收敛的 14 条 `repair_helped=None` 不计入；不收敛的 6 条中 4 条被修复链救回、2 条按设计不救，均与标签一致），不是"20 条全部通过修复验证"。**数字本身未能推翻，但表述有误导成分**（见 C4 节）。
