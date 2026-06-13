---
name: edit-finish
description: 产出 EDL 与剪映/Premiere 操作指导：拼接顺序/转场/统一调色/字幕/纠错遮挡。
---

# SK9 · edit-finish（剪辑成片）

> 产出 EDL 与剪辑操作指导。注：粗剪不计入 MVP 验收门槛（设计稿 §9）。详见设计稿 §5 SK9。

## 输入 / 输出

- 输入：选定 takes + shotlist + qc-report + style-bible。
- 输出：`08_edit/edl.md` + 操作任务卡。

## Gate

**G8 整体一致性 + 终审**。

## 职责

产出 EDL 与剪映/Premiere 操作指导：拼接顺序、转场、统一调色、超分/插帧建议、字幕、纠错遮挡。

## 提示词要点

- EDL 按剪映术语组织；QC 问题逐条映射处置。
- 调色从 `style-bible` 导出统一参数。
- **半自动剪辑**（P2）：先产"EDL → 剪映可导入清单 + 调色参数表"，全自动 XML 为远期。

## 脚本

`edl_render.py`（从选片结果生成 EDL 骨架：时间码 + 选定 take；读 audio-manifest
ambience_groups 生成"环境音桥接轨"，A.3）。
