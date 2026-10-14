# 文档更正补全复核报告（2026-10-10）

> **第五轮撤回横幅（2026-10-11）**：本报告的核查对象（`p = 1.2818`、`GCI(fine) = 0.00485 %`、
> 渐近比 `5.911`、`conditional` 判定）是基于**符号反的 GCI 观测阶公式**的输出，现已被外部评审
> 推翻并修复：观测阶公式已翻正（单调收敛序列返回正 p），修复后 `n = 40/80/160` 的增量递增
> （+1.075863、+2.615786）给出观测阶 **−1.2818**（非正），闸门正确判 `reject`；上述全部数字
> **无效，已全文撤回**。
> 渐近比 5.911 经代数验证恒等于 r^(2p)（= 2^(2×1.2818)），是恒等式而非独立判据——本报告把
> 「5.911 出界 → conditional」当作闸门自我纠正的证据，该推理在符号反公式下不成立。
> 详见 `docs/fixes-round5.md`。以下为第四轮原文，保留以记录当时判断；与第五轮更正冲突处以
> 横幅与 `docs/fixes-round5.md` 为准。

> 独立复核队长对 V&V 第四轮升级报告中「GCI 在真实极限载荷场景下无法报告可用值」
> 这一过窄判断的更正，并按更正口径补全队长漏掉的同类陈述。

---

## 一、独立验证队长的数字（全部与 `verisolv.gci.compute_gci` 实出核对）

复现命令：`python tools\_recheck_gci_numbers.py`（新建，委托 `compute_gci`）

| 量 | 队长记录 | 独立复算（`verisolv.gci`） | 一致？ |
|---|---|---|---|
| n=40/80/160 峰值 | 7959.445105 / 7960.520968 / 7963.136754 N | 同 | ✅ |
| p | 1.2818 | 1.281750 | ✅ |
| Richardson | 7964.96 N | 7964.964265 N | ✅ |
| GCI(fine) | 0.00485 % | 0.004853 % | ✅ |
| 渐近比 | 5.911 | 5.911405 | ✅ |
| 闸门判定 | conditional | conditional（fail_reason=`not_in_asymptotic_regime`） | ✅ |

**队长的数字全部正确。** 判定理由也正确：渐近比 5.911 出 `[0.7, 3.0]` 带 → `conditional`，
不得当作误差界。这是载荷步细化，不是空间网格收敛研究。

> **第五轮注（2026-10-11）**：上表全部数字在符号反公式下算出，已作废。修复后同一序列
> `n = 40/80/160` 判 `reject`（观测阶 −1.2818，增量递增），我们**没有量化离散误差带**。
> 本表仅作为第四轮历史记录保留。

## 二、队长改对了吗？

**GCI 主结论改对了。** 原判断「真实极限载荷场景下无法报告可用值」确实过窄——
它只在 `cantilever_truss` **load control**（3 步长序列退化）下成立。换
`von_mises_truss` **位移控制** + 关注量取**路径峰值载荷** + 粗端 `n=40/80/160`，
GCI 确实能够形成。闸门判 `conditional` 而非 `pass` 也是正确的（渐近比出界）。

**但有两处细节需要修正（本次补全已改）：**

### 2.1 `tools/verify_gci_usefulness.py` 脚本与闸门口径不一致（队长修正前留下的 bug）

队长修正该脚本时，让它打印 `[conditional]` 而非 `[pass]`，**方向对了**，但脚本内部仍用自己的 GCI 公式，
与 `verisolv.gci.compute_gci`（即实际闸门用的函数）**不是同一套公式**：

| 量 | 脚本原输出（自写公式） | 闸门 `compute_gci` 输出 | 差异 |
|---|---|---|---|
| GCI(fine) | 0.02869 % | 0.00485 % | 不同公式（脚本用 `Fs·\|f3−f2\|/((r^p−1)·\|f3\|)`；闸门用 `GCI_coarse/r^p` 相对化） |
| 渐近比 | 0.169 | 5.911 | 不同公式（脚本 `GCI_coarse/(r^p·GCI_fine)`；闸门 `GCI_asymptotic/GCI_fine`） |
| 5/10/20 判定 | reject（observed order not positive） | reject（**degenerate**：两最细样本差为 0） | 触发原因不同 |
| 10/20/40 判定 | conditional（p=44.5） | conditional（p=44.5，渐近比≈6.2e26） | 数值不同 |

**影响**：脚本若被独立运行，会给出与闸门**不同的数字**，读者会以为「闸门报 0.02869%」，
而文档和闸门实际报的是 0.00485%。这正是文档更正想消除的「脚本与闸门矛盾」问题。

**本次修正**：将 `tools/verify_gci_usefulness.py` 的 `gci_triple()` 改为**直接委托
`verisolv.gci.compute_gci`**（同一函数、同一口径），脚本输出与闸门严格一致。
修正后 40/80/160 打印 `GCI(fine) = 0.00485 %  asymptotic_ratio = 5.9114  [conditional]`，
与文档、闸门三者一致。

### 2.2 文档中「5/10/20 报 observed order not positive」的措辞

原写「`5/10/20` 与 `20/40/80` 报 `observed order not positive`」。
按 `verisolv.gci` 实际判定，`5/10/20` 触发的是 **degenerate reject**（`n=20` 与 `n=10`
峰值逐位相同，两个最细样本之差为 0），不是 p 非正。`20/40/80` 才是 p 非正。
本次在 `docs/upgrade-report.md` 实测结果节更正了这处措辞。

## 三、队长漏掉的同类陈述（本次补全）

全文搜索「无法报告可用 / 无法展示正数 GCI / 需要位移控制下远离极限点 / GCI 无法在退化序列上给出带宽 / 尚未证明」，
范围：所有 `.md`（排除 `docs/AGH-*BRIEF*.md` 正文，但任务书只许追加不改，故在对应位置追加更正注记）。

| # | 文件 / 位置 | 原陈述 | 是否队长已改 | 本次动作 |
|---|---|---|---|---|
| 1 | `docs/upgrade-report.md` 「我没能完成的」表 GCI 行 | 「无法展示正数 GCI / 需要位移控制下远离极限点」 | ✅ 队长已划掉并加更正 | 保留队长更正 |
| 2 | `docs/upgrade-report.md` 「GCI 在真实问题上的实测结果」节 | 新增 | ✅ 队长已加 | 保留，并修正 2.1/2.2 细节 |
| 3 | `EVIDENCE.md` 「尚未证明的东西」第 3 条 | 原「GCI 在极限载荷场景下的正数带宽」 | ✅ 队长已标已解决、新增第 7 条 | 保留 |
| 4 | `EVIDENCE.md` 深度地图「几何非线性路径」行 | 原旧判断 | ✅ 队长已更新为实测 | 保留 |
| 5 | `EVIDENCE.md` 「下一步证据里程碑」第一行 | 原旧 | ✅ 队长已改为「落进渐近区的 GCI」 | 保留 |
| 6 | `COMPLETION-SUMMARY.md` 「我没能完成的」表 GCI 行 | 原「无法展示正数 GCI」 | ✅ 队长已更正 | 保留 |
| 7 | `COMPLETION-SUMMARY.md` 「7. EVIDENCE.md」小计 | 写「6 项尚未证明的东西 / 5 个里程碑」 | ❌ **队长漏了** | **本次改为 7 项**（与 EVIDENCE.md 实际一致：第 3 条已解决、新增第 7 条，总数 6→7） |
| 8 | `docs/AGH-VV-UPGRADE-BRIEF.md` §330（历史任务书） | 「无法展示正数 GCI / 需要位移控制下远离极限点」 | ❌ **队长漏了**（正文不可改） | **本次按「只许追加」规则在表格下方追加更正注记** |
| 9 | `docs/AGH-VV-UPGRADE-BRIEF.md` §212 | 「没有 GCI 就不能报 SIGNOFF」 | — | **无需改**：这是 claim-level 规则陈述，与「GCI 能否形成」无关，仍正确 |

> 第 9 项说明：`AGH-VV-UPGRADE-BRIEF.md` 的「没有 GCI 就不能报 SIGNOFF」是**级别门槛**陈述
> （signoff 需要 GCI 可用），**不是**「GCI 无法形成」的悲观陈述，故不在本次更正范围。

## 四、10 个回归基线是否全部不变

重跑全部 8 个 tools + `cases --strict`，**全部通过，基线不变**：

| 命令 / 工具 | 结果 | 基线 |
|---|---|---|
| `python tools\check_physics.py` | RESULT: PASS；峰值 7,963.1 N（闭式 7,963.2 N，相对误差 5.44e-06）；6 行挠度对照 4.75e-16…7.99e-16 | ✅ 不变 |
| `python tools\cross_validate.py` | RESULT: PASS | ✅ 不变 |
| `python tools\demo_closed_loop.py` | 正常输出（载荷控制失败 → 位移控制修复链） | ✅ 不变 |
| `python tools\check_gci.py` | GCI self-validation: PASS（p=0.5/1/1.5/2/3 全对，5 种失败模式全对） | ✅ 不变 |
| `python tools\run_case_library.py` | total=20, detected=9/9, undetectable=2, positive_controls=9, controls_clean=9, repair_behaviour_correct=20, missed=[] | ✅ 不变 |
| `python tools\acceptance_scale_fix.py` | ACCEPTANCE: all three criteria PASS | ✅ 不变 |
| `python tools\verify_audit_findings.py` | FINDING 1/2 CONFIRMED | ✅ 不变 |
| `python tools\verify_gci_usefulness.py` | 40/80/160 → p=1.2818, Richardson=7964.96 N, GCI(fine)=0.00485%, 渐近比=5.9114, **conditional** | ✅ 与闸门一致 |
| `python -m verisolv cases --strict` | strict: passed；total=20, detected=9, undetectable=2, positive_controls=9, controls_clean=9, repair_behaviour_correct=20, missed=[]；闭式解 6.1056294e-16 / 4.5792221e-16 / 2.3445617e-16 | ✅ 不变 |

**10 个基线数字全部不变。**（本次只改文档和 `tools/`，未动 `verisolv/verisolv/`。）

## 五、我没做到的事（如实声明）

1. **没有验证 GCI 在 `cantilever_truss` load control 之外的其他工况**（如 von_mises 位移控制的其他目标位移、其他 r 比）是否也能形成 `pass`。本次只复现了队长给的 `von_mises_truss`、−0.15 m、r=2、n=40/80/160 一条。**「能判为 pass 的 GCI」仍未证明**（渐近比 5.91 出界，只能到 conditional）。
2. **没有独立复核 `verify_gci_usefulness.py` 改前（自写公式版）的历史输出**。我复现的是改后（委托版）输出；改前数字（GCI(fine)=0.02869%、渐近比=0.169）来自脚本自身打印，未逐行回溯。
3. **没有为「尚未证明」第 7 条（渐近区内的 GCI）提供可判 pass 的序列**。这是本次更正后仍开放的问题，已在 EVIDENCE.md / upgrade-report.md 如实标注。
