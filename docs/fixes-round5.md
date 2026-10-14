# 第五轮修复报告：GCI / MMS / 计数 / 表述 更正（2026-10-11）

> 依据 `docs/AGH-ROUND5-FIX-BRIEF.md`（外部对抗性评审后的修复任务书）。
> 本轮**撤回了第四轮的两个量化声称**（GCI 误差带、MMS 收敛阶），
> 修复了 GCI 观测阶公式的符号错误，并用**不共享被测代码的独立判据**重新验证。
> 冻结的求解器内核（`fem.py`/`solver.py`/`repair.py`/`cases.py` 案例定义）**未修改**。

---

## 总览

| 缺陷 | 问题 | 根因 | 修法 | 独立判据 |
|---|---|---|---|---|
| 1（最严重） | GCI 观测阶公式方向反，误报 `GCI(fine) = 0.00485 %` | `gci.py` 里 `p = ln((f3−f2)/(f2−f1))/ln(r)`，与 docstring「f1 最粗、f3 最细」约定**方向相反**；单调收敛序列返回 **负的** p，`n=40/80/160` 增量递增序列被误判为 `p=+1.28`、`conditional` | 翻正公式为 `p = ln((f2−f1)/(f3−f2))/ln(r)`；`p≤0`（增量递增/发散特征）一律 `reject`；渐近比（绝对形式）经代数验证为恒等式，改用文献的相对形式一致性比 | **构造上已知阶的序列**（`tools/verify_gci_formula.py`）：`f = f_exact + C·h^p`、`h = 1, 1/2, 1/4` 按 docstring 约定粗→细喂入，期望 `p` 精确恢复；不共享被测公式 |
| 2 | MMS「验证通过」声称无效 | 制造源项**从未注入求解器**；SymPy 推导两处代数错误（应变应为 a+a²/2、节点力应为 ±N）；`theory_p=1` 与饱和实测矛盾；**且无空间网格可细化** | 按队长决定**撤回、不修**：`docs/mms.md` 改写为「MMS 尝试记录（未成功）」；`tools/mms_verification.py` 加显著头部警告；撤回全部 MMS 有效性声称 | n/a（撤回）；判据 = 全项目 grep `MMS 通过 / 验证通过` 零残留（见 §9） |
| 3 | 案例库计数「9 条首解、11 条修复」错误 | 「9」取自阳性对照数、「11」取自非 `converged_verified` 标签数，被误粘为首解/修复计数 | 改为实测 14 / 6 / 4，并逐条列出案例名与来源命令 | `python -m verisolv cases` 重跑逐行核对（`runs/cases_round5.json`） |
| 4 | `EVIDENCE.md` 两处倒装 + 逐行复核 | 「GCI 是误差上界」漏否定词；「非线性闭式解」误标「线性测试」；0.00485% 与 SOURCE-BACKED GCI 行未撤回 | 逐行改写；补「尚未证明的东西」与 GCI/MMS 诚实定位节 | 人工逐行读 + §9 的 grep |
| 5 | 跨库验证 3 处表述 | 头条 6.8e-8 缺载荷水平；「每降一个数量级差距同降」错；「按 I² 下降」错（实为线性） | 补完整梯子表；改「平坦地板 ~7e-8，50 kN 处跳 80×」；TINY_I 注释改线性并配扫描 | `tools/tiny_i_scan.py`（1e-8→1e-16 扫描）：~87× 收缩（线性 ~100×，非 10000×），后到噪底 |
| 6 | 两个新「四闸门通过 + verified + 答案错」反例 | `material_plausibility` 带宽 1e6–1e12 Pa 内的 E=21 GPa；载荷加在全约束节点 | 构造验证并披露（EVIDENCE.md / verification.md §8） | 两个现场构造运行（`runs/ce1_e21gpa.txt`、`runs/ce2_load_on_fixed.txt`） |

---

## 1. 缺陷一：GCI 观测阶公式（修 gci.py）

### 1.1 修复前后实测对比（同一真实序列 `n = 40/80/160`，峰值载荷）

样本（由 `tools/verify_gci_usefulness.py` 扫出）：
`7959.445105 → 7960.520968 → 7963.136754 N`，增量 `+1.075863`、`+2.615786`（**递增**）。

| 量 | 修复前（符号反） | 修复后 |
|---|---|---|
| 观测阶 p | +1.2818（应为 −1.2818，比值方向反导致符号反） | **−1.2818** |
| 闸门判定 | `conditional`（渐近比 5.911 出界） | **`reject`**（`nonpositive_p`：增量递增、非单调收敛，Richardson/GCI 不适用） |
| GCI(fine) | 0.00485 %（**无效数字，已全文撤回**） | n/a（rejected，不报 GCI） |

### 1.2 独立判据：`tools/verify_gci_formula.py`

**判据构造（不共享被测公式）**：按 `f = f_exact + C·h^p`、`h ∈ {1, 1/2, 1/4}`（粗→细）
**构造出阶数已知的序列**，期望闸门报出 p_true（1e-6 精度）。p_true 来自构造本身，
**不是**从被测公式推出来的——因此判据与代码不共享假设。

实测（`runs/verify_gci_formula_post.txt`）：

- **A（教科书正例）**：`p_true ∈ {2, 1, 1.5, 3}`，粗→细喂入 → 报 `p = 2.0000 / 1.0000 / 1.5000 / 3.0000`，status = `pass`。**修复前该判据对 `p_true=2` 会报 −2.0000（reject）**——这就是评审用的「决定性测试」。
- **B（细→粗喂入，次序反）**：同一批序列倒序喂 → `p = −2 / −1 / −1.5 / −3`，全部 `reject`。证明公式现在对喂入次序**敏感且方向正确**。
- **C（真实序列 `n=40/80/160`）**：增量递增 → `p = −1.2818` → `reject`，不报 GCI。
- **D（代数恒等式核查）**：旧版绝对形式渐近比 = `GCI_asymptotic/GCI_fine`，在符号反公式下**恒等于 r^(2p)**（= 2^(2×1.2818) ≈ 5.911）——是恒等式、不携带 p 之外的信息，**不是独立判据**；修复后恒等于 1。已改为文献的相对形式一致性比 `GCI_32·r^p/GCI_21`（Celik et al. 2008），并如实记录：观测阶下它退化为 |f1|/|f2|，仅为同量级 sanity check。

### 1.3 `tools/check_gci.py` 的循环自证已消除

第四轮 `check_gci.py` 的合成样本**按细→粗倒序喂入**，恰好与符号反的公式**两个错误抵消**，
所以「5 个已知阶全部精确恢复」是假的。本轮改为按 docstring 约定粗→细喂入；
`verify_gci_formula.py` 承担独立的「构造上已知阶」判据。修复后 `check_gci.py` 与
`verify_gci_formula.py` **各自**通过，且次序与 docstring 一致。

### 1.4 0.00485% 的全项目撤回

撤回范围：`README.md`、`EVIDENCE.md`、`docs/upgrade-report.md`、`COMPLETION-SUMMARY.md`、
`docs/correction-recheck-report.md`（加撤回横幅）、`docs/AGH-VV-UPGRADE-BRIEF.md`（历史任务书，
只许追加 → 追加注记）。全项目 grep `0.00485` 的残留命中**全部**位于：
(a) 任务书/评审简报（`AGH-ROUND5-FIX-BRIEF.md`、`EXTERNAL-REVIEW-BRIEF.md`）——引用缺陷是任务的一部分；
(b) 各撤回横幅/更正注记内——明确标注该数字已作废；
(c) `tools/verify_gci_usefulness.py` 的历史注记——明确标注「曾误报」。
**没有任何一处把 0.00485% 当作当前有效结果。**

### 1.5 GCI 闸门现状（如实）

修复后，本项目的真实载荷步细化序列**不在渐近区**（增量递增），闸门正确判 `reject`。
**我们没有量化的离散误差带。** GCI 是渐近假设下的误差*估计*，**不是误差上界**；
载荷步细化**不是**空间网格收敛研究。`claim_level` 在真实问题上封顶 `engineering`
（`signoff` 需要一个可判 `pass` 的 GCI，目前不存在）。

---

## 2. 缺陷二：MMS 撤回（不修）

根因（详见 `docs/mms.md`）：
1. 制造源项从未注入求解器（位移是强加的，测的是因变量载荷因子，不是 `f_int ≈ q`）；
2. SymPy 推导两处错误：应变 `a` 应为 `a + a²/2`；节点力 `±N/2` 应为 `±N`；
3. `theory_p=1` 与 1.4e-11 饱和实测矛盾；
4. **根本原因：模型没有空间网格，MMS 的核心（空间细化测阶）在本框架内不适用。**

处置：`docs/mms.md` 改写为「MMS 尝试记录（未成功，已撤回）」；`tools/mms_verification.py`
加显著头部警告、payload 加 `"retracted": true`；1.4e-11 仅保留为**步长细化稳定性观察**。
撤回范围：`EVIDENCE.md`、`README.md`、`docs/upgrade-report.md`、`COMPLETION-SUMMARY.md`。
**全项目不再存在「MMS 通过 / MMS 已验证」的有效声称。**

---

## 3. 缺陷三：案例库计数

`docs/verification.md` §5 与 `docs/audit-report.md` C4 原写「9 条首解收敛、11 条经修复」。
`python -m verisolv cases`（全量 JSON，`runs/cases_round5.json`）逐行核对，实际：

- **首解即收敛 14 条**：A02, A04, A05, N01, N02, E02, E00, E03, R01, R02, R03, B01, B02, B03
- **首解未收敛、真正调用修复链 6 条**：A01, A03, A06, A07, E01, B04
- **修复链救回 4 条**：A01, A03, A06, E01（A07 机构、B04 缺约束按设计**不救**，修复链正确地不升级）

「9」实为阳性对照数、「11」实为「非 `converged_verified`」观测标签数，均非首解/修复计数。
来源命令已写在文档计数旁：`python -m verisolv cases`（全量）；严格回归 `python -m verisolv cases --strict`。

---

## 4. 缺陷四：EVIDENCE.md 逐行复核

修正（逐行读全部 75 行后）：
- 「GCI **是误差上界**」→「GCI **不是误差上界**」（漏否定词）；该行整体改为「量化误差带 = 没有」；
- 「闭式解一致性」行「多自由度/桁架/梁路径精度」与「线性化测试」误标 → 改为
  **单自由度两杆几何非线性（Green-Lagrange/PK2）精确解析解**，明确「不是线性化测试」；
- MMS 各行 → 已撤回（见 §2）；
- 「尚未证明的东西」补 3 条：E=21 GPa、载荷全约束节点、位移控制下 `step_refinement` 近乎空转；
- 新增「GCI / MMS 的诚实定位」节；「仅引用」表补 Celik et al. 2008 一致性比的非独立性说明；
- 里程碑表「落进渐近区的 GCI」与「二次制造场 MMS」均标未达成/撤回。

---

## 5. 缺陷五：跨库验证三处表述

`docs/verification.md` §2/§6、`README.md`：
- 头条 6.8e-8 **必须带载荷水平**：完整梯子（`tools/cross_validate.py` 实测）
  `5 N → 6.794e-8`；`50 N → 6.813e-8`；`500 N → 6.989e-8`；`5000 N → 8.814e-8`；
  **`50000 N（设计载荷）→ 7.139e-4`**。头条 6.8e-8 是最小载荷 5 N（线性极限）处的值；
  设计载荷处差 7.14e-4，比头条数字大 1 万倍；小载荷段是**平坦地板**（~7e-8），
  50 kN 处跳 80×（非线性效应超出小变形对照适用范围）。**原「每降一个数量级差距同降一个数量级」的说法错误。**
- `cross_validate.py` 注释「按 I² 下降」改为**线性**：`tools/tiny_i_scan.py` 实测
  `TINY_I = 1e-8/1e-10/1e-12/1e-14/1e-16` @ 5000 N：
  `3.292e-3 → 3.768e-5（~87×）→ 7.098e-5 → 7.132e-5 → 7.132e-5（噪底）`。
  若为 I² 每 100× 的 I 应使差缩 10000×；实测 ~87×（≈线性 100×），之后到噪底不再变。

---

## 6. 缺陷六：两个新反例（构造验证 + 披露）

均按评审提示**亲自构造并运行**（非引用评审数字）：

| 反例 | 构造 | 实测（`runs/*.txt`） | 结论 |
|---|---|---|---|
| CE1：E = 21 GPa | `von_mises_truss`，模量 2.1e10（默认 2.1e11 的 1/10，**仍在 `material_plausibility` 带宽 1e6–1e12 Pa 内**），位移控制到 −0.15 m、n=20 | `converged=True`；四道数值闸门**全过**；`verdict = verified`；峰值路径载荷因子 **0.0397**（默认 E=210 GPa 为 0.3968） | 载荷能力低 **10.0×**（评审说的位移错 ~9.2× 等价于等目标位移下载荷差 10×）；数值自洽、答案错 |
| CE2：载荷全加全约束节点 | `cantilever_truss`，整个 −50 kN 顶点载荷移到节点 0（两 DOF 均被约束） | `converged=True`；四道数值闸门**全过**；`verdict = verified`；`max_displacement = 0.0`（零响应） | 零响应 + verified；载荷施加位置是意图类错误，数值层抓不到 |
| 位移控制下 `step_refinement` 近乎空转 | 终点强加（同一目标值），2N 步与 N 步在终点必然相同 | 真正变化的量（路径峰值载荷）**不被该闸门比较** | 位移控制下该闸门只验证「收敛重现性」，不验证「路径载荷精度」 |

已披露：`EVIDENCE.md`「尚未证明的东西」第 8–10 条 + `docs/verification.md` §8 第 3–5 条
（与既有「面积量级盲点」并列）。

---

## 7. 回归基线（10 个数字不变）

`python -m verisolv cases --strict` 重跑（本轮）：

| 基线 | 值 | 是否不变 |
|---|---|---|
| total_cases | 20 | ✅ |
| detected | 9/9 | ✅ |
| undetectable_by_design | 2 | ✅ |
| positive_controls | 9 | ✅ |
| controls_clean | 9 | ✅ |
| repair_behaviour_correct | 20/20 | ✅ |
| missed | [] | ✅ |
| 闭式解相对误差 | 6.1056294e-16 / 4.5792221e-16 / 2.3445617e-16 | ✅ |
| `cases --strict` | `passed` / exit 0 | ✅ |

另：`tools/check_physics.py` → PASS（峰值 7,963.1 N）；`tools/check_gci.py` → PASS
（次序已修，p=0.5/1/1.5/2/3 全对、失败模式全对、增量递增 reject、end-to-end 非单调 reject）；
`tools/verify_gci_formula.py` → 独立判据通过（§1.2）。

---

## 8. 每条修复的独立判据是什么（任务书要求节）

| 修复 | 独立判据（不共享被测代码的假设） |
|---|---|
| GCI 公式 | **构造上已知阶**：`f = f_exact + C·h^p`、`h=1,1/2,1/4` 粗→细，`p_true` 来自构造本身；修复前该判据对 p_true=2 报 −2.0000（reject），修复后报 2.0000（pass）。喂入次序倒转必须使结果变号。 |
| 渐近比非独立性 | **代数核查**（`verify_gci_formula.py` §D）：旧版绝对形式 ≡ r^(2p)（修复前）/ ≡1（修复后），手推 + 程序双重验证；据此弃用旧口径、改用 Celik et al. 2008 相对形式并如实标注其观测阶下退化为 \|f1\|/\|f2\|。 |
| 案例计数 | 重跑 `python -m verisolv cases` 逐行核对（`runs/cases_round5.json`）；队长可再跑一次确认。 |
| TINY_I 线性 | `tools/tiny_i_scan.py`：连续 100× 的 I 网格；线性缩 ~100×、二次缩 ~10000×；实测 ~87× 后到噪底。 |
| CE1/CE2 反例 | 现场构造两个模型并跑 `verify()`，`runs/ce1_e21gpa.txt`、`runs/ce2_load_on_fixed.txt` 为原始输出。 |
| MMS 撤回 / 0.00485% 撤回 | 判据 = 全项目 grep（`MMS 通过`、`0.00485` 的非撤回上下文、`SOURCE-BACKED.*GCI`）零残留有效声称（见 §9）。 |

---

## 9. 残留声称审计（队长可直接复跑）

```powershell
# 1) 0.00485：允许残留仅在任务书/评审简报、撤回横幅、历史注记中
powershell -Command "Get-ChildItem -Recurse -Include *.py,*.md | Select-String '0\.00485' | ForEach-Object { \"$_`.Path`:$($_.LineNumber)\" }"

# 2) MMS 通过/已验证：必须零残留（不含 docs/mms.md 内「已撤回」的自述）
powershell -Command "Get-ChildItem -Recurse -Include *.py,*.md | Select-String 'MMS\s*通过|MMS.*已验证|验证通过.*MMS' | ForEach-Object { \"$_`.Path`:$($_.LineNumber): $($_.Line)\" }"

# 3) SOURCE-BACKED + GCI：必须无「GCI 的 SOURCE-BACKED 证据行」
powershell -Command "Get-ChildItem -Recurse -Include *.md | Select-String 'SOURCE-BACKED' | Select-String 'GCI' | ForEach-Object { \"$_`.Path`:$($_.LineNumber)\" }"
```

本轮已逐行核对：`0.00485` 的全部残留命中均在「引用缺陷 / 撤回横幅 / 历史注记」语境；
`SOURCE-BACKED` 已不再与 GCI/MMS 同行出现；`MMS 通过 / 已验证` 仅出现在 `docs/mms.md`
「已撤回」自述与任务书引用中。

---

## 10. 我没做到的（如实报告）

1. **没有可用的 GCI 误差带。** 公式修对了，但真实载荷步细化序列不在渐近区（增量递增），
   闸门正确判 `reject`。我们**至今没有任何量化的离散误差带**，也没有一组能判 `pass`
   的三重序列。这比第四轮「声称有 0.00485%」更糟，但**诚实**。
2. **没有 MMS。** 框架没有空间网格，MMS 核心不适用；本轮按队长决定撤回、不修。
3. **没有独立验证 GCI 公式之外的 V&V 层**：渐近区假设本身、载荷步细化能否代表
   空间离散误差，均未验证。
4. **CE1/CE2 的反例只构造了评审指出的两个**；「在合理带内、数值自洽、但答错」
   这一类盲点没有穷尽（例如密度写错、屈服应力写错但仍在带内，预期同类行为，未逐一验证）。
5. **半天预算**：本轮在预算内完成全部 9 项；若队长复核发现新缺陷，属于下一轮，不在本轮承诺内。
6. **没有为「渐近区内的 GCI」提供任何序列**——这是开放问题，已在 `EVIDENCE.md`
   「尚未证明的东西」第 7 条如实标注。

---

## 11. 立场声明（任务书第 10 节）

> 我们尝试把 V&V 的量化层接进来。GCI 的第一次实现是错的（公式方向反），由外部评审
> 发现，现已修复，并用一个不共享代码的独立判据重新验证。修复后，它在我们的问题上
> 正确地判定为「不在渐近区」，因此我们至今没有得到任何误差带。MMS 我们做不了——
> 我们的模型没有空间网格，而 MMS 的核心正是空间细化测阶。我们把这些都写下来了，
> 因为一个声称自己有误差带而其实没有的项目，比一个承认自己没有的更危险。

---

## 12. 文件改动清单（本轮）

| 文件 | 改动 |
|---|---|
| `verisolv/gci.py` | 观测阶公式翻正；`p≤0 → reject`；新增 `consistency_ratio` 字段；渐近比（绝对形式）降级为透明输出并文档化为恒等式；模块头文档重写 |
| `verisolv/verify.py` | `check_gci` 随 gci.py 修复同步（未改 4 闸门 verdict 逻辑，gci 仍为 MINOR） |
| `tools/check_gci.py` | 合成样本次序改为 docstring 约定（粗→细）；新增「增量递增 → reject」测试；消除循环自证 |
| `tools/verify_gci_formula.py` | 新增（独立判据）：构造上已知阶 + 次序反转 + 真实序列 + 代数恒等式核查 |
| `tools/verify_gci_usefulness.py` | 更新为修复后闸门口径；真实序列判 reject；历史注记 |
| `tools/tiny_i_scan.py` | 新增：TINY_I 线性性扫描 |
| `tools/cross_validate.py` | 注释改线性 |
| `tools/mms_verification.py` | 撤回横幅 + `retracted` 字段 + CLI 描述 |
| `docs/mms.md` | 改写为「MMS 尝试记录（未成功，已撤回）」 |
| `docs/verification.md` | 计数 14/6/4 + 来源命令；跨库梯子 + 地板表述；§8 新增 CE1/CE2/step_refinement 局限 |
| `docs/audit-report.md` | C4 计数更正 + 溯源注记 |
| `EVIDENCE.md` | 逐行更正（§4）；GCI/MMS 诚实定位节；未证明清单 +3；里程碑撤回 |
| `README.md` | 跨库梯子 + 载荷水平；GCI/MMS 诚实定位节 |
| `COMPLETION-SUMMARY.md` | GCI/MMS 结论撤回；复现命令更新；GCI 公式改修复后 |
| `docs/upgrade-report.md` | 顶部撤回横幅；GCI 公式改修复后；MMS 撤回 |
| `docs/correction-recheck-report.md` | 顶部撤回横幅 + 表后注记 |
| `docs/AGH-VV-UPGRADE-BRIEF.md` | 追加第五轮注记（历史任务书只许追加） |
| `runs/verify_gci_formula_post.txt`、`runs/ce1_e21gpa.txt`、`runs/ce2_load_on_fixed.txt`、`runs/cases_round5.json` | 本轮实测原始输出 |

冻结内核 `verisolv/verisolv/fem.py`、`solver.py`、`repair.py`、`cases.py`（案例定义）**未修改**。
