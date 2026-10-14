# 升级报告：V&V 第四轮（GCI + MMS + 术语纠正）

> **第五轮更正横幅（2026-10-11）**：本轮的 GCI 与 MMS 量化层已被外部评审推翻：
> GCI 观测阶公式符号反（比值方向与 docstring 约定相反），由外部评审发现、已修复；
> 修复后真实序列 `n = 40/80/160` 判 `reject`（增量递增、不在渐近区），**此前报告的所有
> GCI 数字（`p = 1.2818`、`GCI(fine) = 0.00485 %`、`GCI(coarse) = 0.01180 %`、
> `GCI(asymptotic) = 0.02869 %`、渐近比 `5.911`）均为无效误报，已全文撤回**。
> MMS 不是有效 MMS（制造源项从未注入求解器；SymPy 推导两处错误；无空间网格可细化），
> 已撤回其有效性声称，`tools/mms_verification.py` 保留仅作步长细化稳定性观察。
> 详见 `docs/fixes-round5.md` 与 `docs/mms.md`。下文为第四轮原文，保留以记录当时判断；
> 与第五轮更正冲突处以上述横幅和 `docs/fixes-round5.md` 为准。

> 本报告如实记录做了什么、没做什么、为什么。对照任务书第 10 节的验收项逐条说明。

**完成日期**：2026-10-10（预算 2 天，实际用了约 1 天 14 小时）

---

## 9. 交付物清单（实际完成状态）

| 交付物 | 状态 | 说明 |
|---|---|---|
| `docs/vv-framework.md` | ✅ 完成 | 术语映射表：5 条 V&V 概念映射、step-refinement ≠ grid-convergence 辨析、4 组真实文献引用、claim level 四档定义 |
| `verisolv/gci.py` | ✅ 完成（新文件，~280 行） | `GCIResult` dataclass、`check_refinement_ratio()`、`compute_gci()`、`evaluate_quantity_over_steps()`；三值状态 pass/conditional/reject |
| `verisolv/verify.py` | ✅ 完成（新增，不动旧闸门） | 新增 `check_gci()` 闸门（severity=MINOR，绝不影响 verdict）、`claim_level()` 函数、`verify(gci=...)` 参数；既有 4 道闸门函数体未修改 |
| `tools/check_gci.py` | ✅ 完成 | 3 组测试：已知收敛阶算例 5 个（p=0.5/1/1.5/2/3）全部精确到 1e-6；失败处理 5 种全部正确；真实求解器 end-to-end |
| `tools/mms_verification.py` | ✅ 完成 | SymPy 源项推导 + 求解器 4 步长 MMS 测试；报告观测阶或如实报告饱和 |
| `docs/mms.md` | ✅ 完成 | MMS 原理、SymPy 结果、实测数据、4 条「不证明什么」 |
| `EVIDENCE.md` | ✅ 完成 | 按任务书第 5 节结构：CI 验证了什么（含第三列）、仅引用未经认证、深度地图、尚未证明的东西、下一步里程碑 |
| `.agh/skills/pre-claim-self-check/SKILL.md` | ✅ 完成 | 7 问自检 + 输出模板，覆盖任务书第 6 节全部 7 个问题 |
| `docs/upgrade-report.md` | ✅ 完成 | 本报告 |

---

## 验收核对（对照任务书第 10 节）

| # | 检查项 | 结果 |
|---|---|---|
| 1 | 术语已纠正 | ✅ `vv-framework.md` 第 2 节明确 step-refinement ≠ grid-convergence；`EVIDENCE.md` 每行有「不证明什么」；`gci.py` docstring 写「error estimates under the asymptotic hypothesis, not error bounds, and not a grid-convergence study」 |
| 2 | 引用真实 | ✅ 4 组引用：ASME V&V 10/20（真实标准）、Roache 1994/1998/2006（真实文献，*Int. J. Numer. Methods Fluids* 20:727）、Salari & Knupp 2010、Oberkampf & Trucco 2010（*AIAA J.* 48(6):987） |
| 3 | GCI 实现正确 | ✅ `tools/check_gci.py` 用 5 个已知 p 值算例验证：p=2.0→measured 2.0000，p=1.0→1.0000，p=0.5→0.5000，p=1.5→1.5000，p=3.0→3.0000，全部精确到 1e-6，状态 pass/conditional |
| 4 | GCI 失败处理 | ✅ 5 种失败模式全部正确：非几何步长→reject；非单调→reject+oscillation_range；p=0.2 出带→conditional；退化→reject（误差低于可测阈值）；振荡→reject+range(8,10) |
| 5 | 回归基线 | ✅ `python -m verisolv cases --strict` → **passed**：total=20，detected=9/9，undetectable=2，positive_controls=9，controls_clean=9，repair_behaviour_correct=20/20，missed=[]，闭式解 6.106e-16/4.579e-16/2.345e-16 全部不变 |
| 6 | 改动范围 | ✅ `fem.py`、`solver.py`、`cases.py` 算法函数未修改；`verify.py` 只新增了 `check_gci` 和 `claim_level`；`repair.py` 新增了 `claim_level_value` 字段（默认 "smoke"）；`__init__.py` 新增了导出 |
| 7 | 无过头声明 | ✅ 全文搜索「上界」「保证」「证明」「网格收敛」——`gci.py` 明确写「not error bounds, and not a grid-convergence study」；`EVIDENCE.md` 明确写 GCI 不是上界；`vv-framework.md` 明确写 step-refinement 不是网格收敛 |
| 8 | 报告诚实 | ✅ 见下方「我没能完成的」 |

---

## 我没能完成的

| 事项 | 原因 | 影响 |
|---|---|---|
| ~~GCI 在真实极限载荷场景下报告可用值~~ **（已由队长复核更正，见下；第五轮再次更正）** | 原判断：`cantilever_truss` load control 下 3 步长序列都是 `load_factor=1.0`（退化），GCI 正确拒绝但无法展示正数 GCI。**该判断只对 load control 成立。** | **第四轮更正（2026-10-10）**：换用位移控制 + 路径峰值载荷 + 粗端三重序列 `n = 40/80/160`，报 GCI 可形成。**第五轮更正（2026-10-11，外部评审）**：该 GCI 公式符号反，`p = 1.2818`、`GCI(fine) = 0.00485 %` 为无效误报；修复后增量递增 → p = −1.2818 → 闸门正确判 `reject`。**我们在此问题上没有量化离散误差带。** 见 `docs/fixes-round5.md`。 |
| MMS 测量到非零收敛阶 | **第五轮撤回**：无空间网格可细化，MMS 核心不适用；第一版 MMS 工具不是有效 MMS（源项从未注入求解器；SymPy 推导两处错误：应变应为 a+a²/2、节点力应为 ±N；theory_p=1 与饱和实测矛盾） | 步长细化稳定性观察（1.4e-11）可保留，但不得标为 MMS；收敛阶未测（`docs/mms.md`） |
| SymPy 推导非线性二次制造场 | 只用线性轴向制造场；Green-Lagrange 二次项的符号推导未做 | 当前 MMS 只验证算子的线性部分；完整 MMS 需要二次制造场 |
| NAFEMS 基准题 | 时间不够（需要 1–2 天） | 本轮不覆盖，属于明确声明的局限 |
| 完整的 UQ（蒙特卡洛、敏感性分析） | 本轮只覆盖离散误差这一个量化来源 | 如 `EVIDENCE.md`「尚未证明的东西」第 5 条所述，这是如实声明 |
| 独立库（PyNite/OpenSees）非线性交叉验证 | 时间不够 | 线性交叉验证已有（`tools/cross_validate.py`），非线性扩展未做 |

---

## GCI 实现的核心公式（供队长复核）

```
# f1=coarsest, f2=medium, f3=finest（coarsest-to-finest 顺序）
# 修复前（符号反，已废弃）：p = ln((f3 - f2) / (f2 - f1)) / ln(r)
# 修复后（第五轮，2026-10-11）：单调收敛序列返回正 p；增量递增返回负 p → reject
p       = ln((f2 - f1) / (f3 - f2)) / ln(r)
f_exact = f3 + (f3 - f2) / (r^p - 1)
GCI_coarse  = 1.25 * |(f2 - f1) / (r^p - 1)|
GCI_fine    = GCI_coarse / r^p
consistency_ratio = GCI_32 * r^p / GCI_21   # 相对形式（Celik et al. 2008）；观测阶下 ≡ |f1|/|f2|，非独立判据
# 旧版绝对形式 asymptotic_ratio = GCI_asymptotic / GCI_fine 经代数验证为恒等式
# （符号反公式下 ≡ r^(2p)，修复后 ≡ 1），不携带 p 之外的信息，不再是闸门；
# 仍报出以便透明，但明确标注为非独立判据（详见 verisolv/gci.py 模块头）。
```

失败处理（修复后）：
- 增量递增（|f3−f2| > |f2−f1|）→ p 非正 → reject（发散特征，非单调收敛）
- 非单调（f2 在 f1, f3 之间）→ reject + 振荡范围（min, max）
- `p < 0.5` 或 `p > 4` → conditional（可能未进入渐近区）
- 退化（|f3−f2| < 1e-12 × scale）→ reject（误差低于可测阈值，是好消息，但不报 GCI）
- 非几何步长（r 不固定）→ reject，不做外推
- f2=f1 或 f3=f2 → reject（观测阶无定义）

## GCI 在真实问题上的实测结果（2026-10-10 队长独立复核，第五轮更正后已废弃）

> **第五轮更正（2026-10-11）**：本节所有 GCI 数字（`p = 1.2818`、`GCI(fine) = 0.00485 %`、
> 渐近比 `5.911`、`conditional` 判定）均基于**符号反的观测阶公式**，是**无效误报**。
> `n = 40/80/160` 的增量递增（+1.075863、+2.615786），观测阶为 **−1.2818**（非正），
> 修复后的闸门正确判 `reject`（发散特征，Richardson/GCI 不适用）。渐近比 5.911 经代数验证
> 恒等于 r^(2p)（= 2^(2×1.2818)），是恒等式而非独立判据。**我们在此问题上没有任何
> 量化离散误差带。** 修复后的实测输出与独立判据见 `docs/fixes-round5.md` 与
> `tools/verify_gci_formula.py`。以下为第四轮原文，保留以记录当时判断（已被推翻）。

**起因**：本报告原文声称「GCI 在真实极限载荷场景下无法报告可用值」。队长不认为这是可接受的结论——**如果闸门在任何真实问题上都不触发，它就是装饰品**，而那正是文献对 GCI 的主要批评。于是独立扫了整个分辨率范围。

**方法**：`von_mises_truss`，位移控制到顶点下挠 −0.15 m，关注量取**路径峰值载荷**，等比细化 r = 2。复现命令：

```powershell
python tools\verify_gci_usefulness.py
```

**扫描结果**（峰值载荷，N）：

```
n_steps      峰值载荷        变化
      5     7385.934470
     10     7936.776222    +550.841751
     20     7936.776222      +0.000000     ← 与 n=10 逐位相同
     40     7959.445105     +22.668884
     80     7960.520968      +1.075863
    160     7963.136754      +2.615786
    320     7963.136754      +0.000000     ← 与 n=160 一致到打印精度（最后一位 ulp 差 1，见下）
```

**只有 `n = 40/80/160` 这一组三重序列给出可用的 GCI（`conditional`，非 `pass`）：**

| 量 | 值（`verisolv.gci.compute_gci` 实出，已独立复算核对） |
|---|---|
| 观测收敛阶 p | **1.2818**（实测 1.281750） |
| 理查森外推 | **7964.96 N**（实测 7964.964265 N） |
| GCI (fine) | **0.00485 %**（实测 0.004853 %） |
| GCI (coarse) | **0.01180 %**（实测 0.011799 %） |
| GCI (asymptotic) | **0.02869 %**（实测 0.028687 %） |
| 渐近比 | **5.911**（实测 5.911405，应趋近 1；`verisolv.gci` 的口径为 `GCI_asymptotic / GCI_fine`） |
| **闸门判定** | **`conditional`** |
| 判定理由 | `asymptotic ratio = 5.911 is outside [0.7, 3.0]; the samples may not be in the asymptotic regime` |

**其他三重组合的闸门判定（全部来自 `verisolv.gci`，与上表同一口径）：**

| 三重 | 闸门判定 | 原因 |
|---|---|---|
| `5/10/20` | `reject`（degenerate） | `n=20` 与 `n=10` 峰值逐位相同，两个最细样本之差为 0，误差低于可测阈值 |
| `10/20/40` | `conditional` | 观测 p = 44.5 出 `[0.5, 4]` 带（离群） |
| `20/40/80` | `reject`（non-positive p） | p = −4.4（序列走向反了） |
| 含 320 的组合 | `reject`（degenerate） | 320 与 160 逐位相同（饱和） |

**三条结论（都是实测，非推断）：**

1. **GCI 闸门不是装饰品。** 它在真实问题上能够形成，并给出正的观测阶与百分比误差估计。
2. **它正确地拒绝了自己的结果。** 渐近比 5.911 落在 `[0.7, 3.0]` 之外，因此判定为 `conditional` 而非 `pass`——**闸门没有把一个不可信的 GCI 当成可信的报出来。** 这正是文献批评 GCI「给出虚假严谨感」的地方。
3. **该序列的其他三重组合都被正确拒绝或降档**：`5/10/20` 与含 320 的组合报 `reject (degenerate)`；`20/40/80` 报 `reject`（p 非正）；`10/20/40` 报 `conditional`（p = 44.5 离群）。

**因此可以对外说的一句准确的话：**

> 极限载荷约 7963 N。载荷步细化的理查森外推给出 7964.96 N，离散误差估计 0.005%–0.029%；但渐近比 5.91 落在 [0.7, 3.0] 之外，说明样本可能未进入渐近区，**故该估计仅可作 `conditional` 级声明，不得当作误差界使用。**

**必须同时说清的边界**（已写入 `verisolv/gci.py` 的 `evidence.note`）：
**这是载荷步细化，不是空间网格收敛研究**；GCI 是在渐近假设下的**误差估计**，**不是误差上界**。

**仍未证明的是**：一个能判为 `pass` 的 GCI（渐近比落进 `[0.7, 3.0]` 的三重序列）。

**本次补全复核的修正记录（2026-10-10，第四轮；第五轮再次更正如下）：**
- `tools/verify_gci_usefulness.py` 原用自写 GCI 公式，与 `verisolv.gci` 口径不一致（脚本 GCI(fine)=0.02869%、渐近比=0.169；闸门 GCI(fine)=0.00485%、渐近比=5.911）。**已改为委托给 `verisolv.gci.compute_gci`**，两者数值从此严格一致（第四轮）。**第五轮更正：委托的公式本身符号反，0.00485% 为无效误报；脚本已更新为修复后的闸门口径，真实序列判 `reject`。**
- 本节原写「`5/10/20` 与 `20/40/80` 报 `observed order not positive`」——按 `verisolv.gci` 实际判定更正为上表口径：`5/10/20` 报的是 **`reject (degenerate)`**（退化检查先于 p 检查触发），`20/40/80` 才是 p 非正的 reject（第四轮）。
- `docs/AGH-VV-UPGRADE-BRIEF.md`（历史任务书，只许追加）第 330 行同类悲观陈述处追加了更正注记（第四轮）。
- **第五轮（2026-10-11）**：GCI 观测阶公式符号反由外部评审发现，已修复（`verisolv/gci.py`）；
  `tools/check_gci.py` 合成样本次序已与 docstring 约定一致（粗→细），不再靠两个错误抵消；
  新增独立判据 `tools/verify_gci_formula.py`（构造上已知阶序列，不共享被测公式）；
  渐近比（绝对形式）经代数验证为恒等式（符号反下 ≡ r^(2p)，修复后 ≡ 1），已改为文献的
  相对形式一致性比（观测阶下退化为 |f1|/|f2|，仅为同量级 sanity check，非独立判据），
  并在 `verisolv/gci.py` 模块头如实记录。

---

## 复现命令（第五轮更新）

```powershell
# GCI 自验证（次序已与 docstring 约定一致；修复前该脚本因次序抵消而通过，是循环自证）
python tools\check_gci.py

# GCI 公式独立判据（构造上已知阶，不共享被测公式；修复前失败、修复后通过）
python tools\verify_gci_formula.py

# MMS（第五轮撤回，仅作步长细化稳定性观察；输出含 retracted 字段与警告）
python tools\mms_verification.py --model cantilever_truss
# 或
python -m verisolv mms --model cantilever_truss

# 回归基线（10 个数字必须全部不变）
python -m verisolv cases --strict

# GCI 闸门（修复后：真实序列判 reject，无可用误差带）
python -m verisolv verify --model cantilever_truss --control load --n-steps 20 --max-iter 60
```
