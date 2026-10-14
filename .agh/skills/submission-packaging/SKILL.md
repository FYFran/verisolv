---
name: submission-packaging
description: Build the competition submission ZIP correctly and safely, and check it before it leaves the machine. Use before any packaging, export, or hand-off of project materials.
---

# Packaging the submission

## Why this needs a checklist

The archive leaves your control permanently. Two failures are common, one of them
serious:

- **A secret ships.** An API key, a token, a `.env` file, a path with a username
  in it. This is not a scoring problem, it is a disclosure problem.
- **The wrong file ships.** A stale build, a recording in progress, a placeholder
  that never got replaced, a figure generated from an older revision.

Both are cheap to prevent and expensive to discover afterwards.

## Naming

```
组别-参赛编号-队伍名称-队长姓名.zip
<组别>-<参赛编号>-<队伍名称>-<队长姓名>.zip
```

Hard limits, enforced server-side: single `.zip`, at most **200 MB**
(209,715,200 bytes exactly), filename at most 255 characters.

## Before building the archive

1. **Scan for secrets.** Grep the whole tree for key-shaped strings
   (`sk-`, `Bearer `, `api_key`, `token`, `password`, `secret`), and check that
   no `.env`, `*.key`, `credentials*` file is staged. The `.gitignore` should
   already exclude these — verify it does, rather than trusting it.
2. **Check for machine-specific paths.** A build log, a config dump or a trace
   containing `C:\Users\<name>\` leaks a username and often a directory layout.
3. **Check for placeholders.** `TODO`, `FIXME`, `XXX`, `{{`, `lorem`, an empty
   figure. A placeholder in a submission reads as an unfinished project.
4. **Confirm the figures were regenerated from the current code.** A number that
   appears in the video, the document and the code must be the same number.
   Re-run the generator rather than reusing an old image.
5. **Confirm the numbers match across all three places.** When they drift, the
   project fails on exactly the dimension it claims to be strongest in.

## What goes where

The competition asks for eight items. Some go inside the archive, some are typed
into the submission form and never enter the archive at all:

| Item | Where it goes |
| --- | --- |
| 基本信息 (name, direction, summary, problem) | Platform form |
| 技术信息 (AGH role, model name/version/stage, interfaces) | Platform form |
| 可运行作品 (repo link, reproducible instructions) | **Inside the archive** |
| 演示视频 | **Link only** — never uploaded |
| 运行证据 (AGH record, tool chain, model evidence, verification) | **Inside the archive** |
| 测试样例 (normal / boundary / failure) | **Inside the archive** |
| 成员声明 | Platform form, signed |
| 公开内容 (public post: platform, link, screenshot, date) | **Inside the archive** |

Video is submitted as **a link**, not a file. Judges must not be asked to log in.

## The three test-case classes

The rules require three kinds, and they must be genuinely different:

- **正常 (normal)** — a well-posed case that succeeds and verifies.
- **边界 (boundary)** — a load exactly at a limit point, a vanishing load, a
  parameter at the edge of its valid range, a safety factor exactly at its
  threshold.
- **失败 (failure)** — a case that fails, with the root cause known and the
  expected diagnosis stated.

The case library produces all three from one source, so they cannot drift apart.

## After building

Open the archive and list its contents. Do not trust the build script's summary
of what it did — read what actually landed. Then verify the extraction runs, not
just that the files are present.
