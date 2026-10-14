# AGH 智能体修正任务书（第三轮 · 最后一轮）

> **读者：Agnes Harness 智能体。**
> 你的三个缺陷修复已通过队长独立验收：改动范围合规 ✅、三条关键判据我亲手复现全过 ✅、
> 10 个回归基线全部一致 ✅、闭式解数字一字不差 ✅、B02 变化你如实记录了 ✅。
>
> **但你的修复带来一个副作用：文档里有一句话现在变成错的了。**
> 这一轮只做一件事——**把那句话改准**。不改逻辑、不改数字、不改任何算法。

---

## 1. 问题

`B02_unit_slip_load_x1000` 是"载荷按 kN 写但读作 N"（×1000）。

**修复缺陷①之前**，它只被 diagnoser + verification 抓到，模型检查器报 `ok`——所以当时写的是
"碰巧被抓到，不是检测能力"。

**修复缺陷①之后**，`check_scale_consistency` 现在能系统性地抓到它，模型检查器报 `suspicious`。

**于是这句话现在不成立了：**

> `of those, caught anyway: B02 -- incidental, NOT a detection capability`

`docs/test-cases.md` 里更进一步的一句，**现在是明确错误的**：

> 它触发的是"位移远超小应变域"的路径跳变，**任何量级的单位错误都会碰巧触发同类反应**

---

## 2. 实测证据（队长已跑，你可以自己复验）

队长写了验收脚本，**你可以直接运行它**：

```powershell
$env:PYTHONIOENCODING = "utf-8"
Set-Location <项目根>
& "python" tools\acceptance_scale_fix.py
```

它扫描"载荷放大倍数"（等价于单位滑移的倍数），实测结果：

```
载荷 ×1    （无滑移）    scale_consistency PASSED   → 静默
载荷 ×10   （小滑移）    scale_consistency PASSED   → 静默   ← 关键反例
载荷 ×100  （大滑移）    scale_consistency FAILED   → 抓到
载荷 ×1000 （B02 的量级）scale_consistency FAILED   → 抓到
```

**所以"任何量级的单位错误都会触发"是错的——只有大到超出小应变域的才会。**

---

## 3. 准确的表述应该是什么

**核心区分：可检测的是"载荷超出结构适用域"这个后果，不是"单位写错"这个原因。**

- B02 这个**实例**（×1000）现在**被系统性抓到**——但要如实说明抓它的**理由**：
  不是因为系统识别出了单位错误，而是因为载荷大到位移超出小应变适用域。
- **"单位写错"作为一个类别仍然不可检测**——实测 ×10 的同类滑移完全静默。
- 所以 **B02 仍然归 `undetectable_by_design`**（这是类别层面的判断，`detectable_by=intent_only`），
  **但"碰巧 / incidental / 靠运气"这个说法必须去掉**，换成"被 scale_consistency 在量级超出适用域时抓到，
  类别层面仍不可检测，×10 量级实测静默"。

---

## 4. 你要改的地方（**全部 8 处，一处都不能漏**）

```
agnes-plugin/index.mjs:265
docs/AGH-BRIEF.md:403
docs/test-cases.md:13
docs/test-cases.md:21
docs/test-cases.md:58
docs/test-cases.md:71
docs/verification.md:59
docs/verification.md:66
README.md:61
```

（行号是当前值，你改的时候以**实际搜索**为准，不要只按行号定位。
先用 `incidental|碰巧|偶然` 全项目搜一遍，确保一处不漏。）

**注意 `docs/AGH-BRIEF.md` 是队长写的任务书，属于历史文档**——
在里面改会让历史记录失真。**对这一份，只在原句后面追加一行更正说明，不要删改原句。**
其余文件直接改成准确表述。

### 插件那一处的特殊要求

`agnes-plugin/index.mjs` 里渲染 `unexpectedly_detected_anyway` 的那句要改。
**改完不要重新安装插件**——队长来装。改完告诉队长新版本待装即可。

---

## 5. 铁律

1. **只改措辞，不改逻辑、不改代码行为、不改任何数字。**
2. **不许改基线数字来迁就。** 上一轮的 10 个基线必须仍然全部一致。
3. 除了第 4 节点名的 5 个文件，**其他文件一律不许动**（特别是 `verisolv/verisolv/*.py`）。
4. **不许编造数据。** 引用实测就贴实际输出。
5. **中文写文档。**

---

## 6. 改完必须做的

1. 重跑全部回归（`check_physics.py` / `cross_validate.py` / `demo_closed_loop.py` /
   `make_assets.py` / `run_case_library.py` / `check_tool_text.mjs` / `cases` / `cases --strict`），
   **确认 10 个基线数字一个都没变。**
2. 重跑 `tools/acceptance_scale_fix.py`，贴出实际输出。
3. 把改动写进 `docs/fixes.md` 新增一节：**"第三轮：B02 表述更正"**，
   说明为什么原来那句话错了、现在改成什么、依据是哪条实测。
4. 按第 4 节清单逐条自查，**报告"8 处全部改到，无遗漏"或如实说明哪处漏了**。

---

## 7. 验收标准

| # | 检查项 | 通过标准 |
|---|---|---|
| 1 | 8 处全部改到 | 队长会**自己**用 `incidental\|碰巧\|偶然` 全项目再搜一遍，必须搜不到旧的错误表述（AGH-BRIEF.md 的历史原句除外，那里应有更正说明） |
| 2 | 新表述准确 | 必须体现"后果可检测、原因不可检测"的区分，且提到 ×10 量级静默这个反例 |
| 3 | 逻辑未被改动 | 10 个回归基线全部一致 |
| 4 | 改动范围 | 只有第 4 节点名的 5 个文件被改 |
| 5 | 历史未失真 | `AGH-BRIEF.md` 原句仍在，只是追加了更正 |

---

**开始吧。这是最后一轮。改完队长验收，然后代码永久封版。**
