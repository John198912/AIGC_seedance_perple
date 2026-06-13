---
name: storyboard-director
description: 剧本→镜头表（C5）；按 control_level 产出分镜首帧图任务卡；可选 Previs 粗剪。
---

# SK4 · storyboard-director（分镜导演）

> 把剧本拆为镜头级真相源（C5），标注控制粒度与坐标化构图。详见设计稿 §5 SK4。

## 触发 / 输入 / 输出

- 触发：G3 通过、进入 S4_STORYBOARD。
- 输入：`screenplay.md` + 角色库 + `style-bible.md` + profile。
- 输出：`04_storyboard/shotlist.yaml`（C5）+ `boards/` 首帧图任务卡 + （可选）`04b_previs/`。

## Gate

**G4 分镜节奏确认**（可升级为 Previs 动态确认）。

## 职责

剧本 → 镜头表（C5）；按 `control_level` 产出分镜首帧图任务卡；可选 Previs 粗剪。

## 提示词要点

1. **拆镜规则**：每镜 ≤15s、节奏化时长分布（快段 2–4s/镜）。
2. 每镜 `action_logic` 写成"动作 + 动机/因果"。
3. **标 control_level**：locked（叙事关键帧/动作衔接）/ guided（默认）/ free（氛围空镜）。
4. **variant 决策树**：要角色一致+有首帧→i2v_omni；纯空镜→t2v；漫画快剪→multigrid；
   有对标参考片→recreate。
5. **第三分镜路径**：复杂多人表演可路由 Kling 3.0 Omni Multi-Shot Storyboard
   （能力数字落地前按 `verified_at` 核验官方文档）。
6. `camera_move` 取自 `shot-language.md`，SK5 据 `camera-preset-map.yaml` 翻译。
7. **坐标化构图**：`composition` 用画面分割/三分/对角线模板写法。
8. 输出"分镜节奏总览"供 Gate 审。

## 脚本

`shotlist_stats.py`（景别/时长分布统计、总时长校验、连贯性 lint）。
