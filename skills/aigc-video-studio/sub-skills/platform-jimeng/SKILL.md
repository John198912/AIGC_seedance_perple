---
name: platform-jimeng
description: 纯 reference 技能：即梦（火山引擎）中文原生交互/沉浸式短片配方/国内合规与水印/与火山方舟 API 差异。
---

# SK11c · platform-jimeng（即梦操作手册）

> **纯 reference 技能**：v2.2 从 higgsfield 手册拆出为独立手册。被 SK5/SK6 引用。详见设计稿 §5 SK11c。

## 性质

即梦（火山引擎）沉浸式短片 · 中文原生 UI 手册。与 `channel-api` 的火山方舟 API 是**同源不同入口**：即梦走 UI 卡，火山方舟走 API 卡，二者 UI/通道差异在本手册标清。

## references/

- `ui-map.md`：即梦中文原生交互入口路径树。
- `recipes.md`：沉浸式短片配方（中文提示词直注、原生同期音利用）。
- `quirks.md`：国内合规与水印/AIGC 标注义务；与火山方舟 API 的 UI/通道差异。
- 能力表：`_shared/libs/capabilities.yaml` 的 `platforms.jimeng`（role=即梦沉浸式短片·中文原生）。

## 语言策略

即梦 / 火山系 → **中文提示词**（语言策略由 SK5 第 11 步落地：volcano/jimeng→zh，falai/higgsfield/openart→en）。

## 维护策略

UI/合规规则迭代快——头部标 `verified_at`，活文档；SK6 发现不符即提示更新。

## 脚本

`capability_query.py`（共享）。
