---
name: platform-higgsfield
description: 纯 reference 技能：Higgsfield Cinema Studio/70+ 运镜预设/Shots/Angles/Transitions/Grid/封号风险。
---

# SK11b · platform-higgsfield（平台操作手册）

> **纯 reference 技能**：不产契约，被 SK4（分镜运镜）/SK5/SK6 引用。详见设计稿 §5 SK11b。

## 性质

导演型工作室手册：Cinema Studio timeline、70+ 运镜预设、Shots 九宫格、Angles、Transitions、Grid 比稿。能力数字进 `_shared/libs/capabilities.yaml` 的 `platforms.higgsfield` 并挂 `verified_at`。

## references/

- `ui-map.md`：入口路径树（Cinema Studio / Shots / Angles / Transitions / Grid 入口）。
- `recipes.md`：高频配方——Shots 九宫格出多机位、Cinema Studio timeline 拼接、Grid 比稿选优。
- `quirks.md`：踩坑——**历史封号/节流/涨价/年付不退风险**（避免年付，本地为唯一事实源）。
- `assets/`：关键入口 UI 截图（如 `cinema-studio-entry.png`），标 `verified_at`，供 `ui_screenshot_refs` 引用。
- 能力表：`platforms.higgsfield`（camera_presets_count=70、character_anchor_refs="20-30"、risk_note）。

## 维护策略

UI/价目迭代快——头部标 `verified_at`，活文档。运镜预设名映射维护在 `_shared/libs/camera-preset-map.yaml`，SK4 运镜词→预设按此查表。

## 脚本

`capability_query.py`（共享）。
