---
name: platform-openart
description: 纯 reference 技能：OpenArt 入口路径树/能力表/角色训练 SOP/高频配方/踩坑/UI 截图。
---

# SK11a · platform-openart（平台操作手册）

> **纯 reference 技能**：不产契约，被 SK3（角色训练）/SK5（编译）/SK6（出卡执行）引用。详见设计稿 §5 SK11a。

## 性质

被引用的活文档手册。OpenArt 承担图像模型 + 角色训练 + Story 场景。能力数字一律进 `references/`（或共享 `_shared/libs/capabilities.yaml` 的 `platforms.openart`）并挂 `verified_at`，月度重验。

## references/

- `ui-map.md`：入口路径树（从首页到角色训练/Story/生成的点击路径）。
- `recipes.md`：高频配方——OpenArt 角色训练 SOP（多图 4+ 锚定一致性）、Story 分场。
- `quirks.md`：踩坑（积分价目/计划限制/导出格式坑）。
- `assets/`：关键入口 UI 截图，供 `TaskCard.ui_screenshot_refs` 引用，标 `verified_at`。
- 能力表：`_shared/libs/capabilities.yaml` 的 `platforms.openart`（character_methods=[text, single_image, multi_image_4plus]）。

## 维护策略

UI 迭代快——手册头部标 `verified_at`；SK6 执行时发现步骤与实际 UI 不符即提示更新（活文档）。`capabilities.yaml` 月度重验，由 `verify_capabilities.py` 辅助。

## 脚本

`capability_query.py`（共享，给定 variant+params 返回是否支持及降级方案）。
