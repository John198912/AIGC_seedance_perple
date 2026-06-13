---
name: character-foundry
description: 角色简报→定角图→特征卡（C4）→平台角色资产注册→入库锁定。identity_strategy 取代伪参数 weight。
---

# SK3 · character-foundry（角色定角）

> 角色一致性的源头。产出 C4 特征卡与双语 identity_strategy。详见设计稿 §5 SK3。

## 触发 / 输入 / 输出

- 触发：G2 通过、进入 S3_CHARACTER。
- 输入：`screenplay.md` 中的 `character_briefs`。
- 输出：`03_characters/<id>/`（C4 `card.yaml` + `turnaround/` + `refs/` + `platform.yaml`）。

## Gate

**G3 角色定稿（强制，永不自动）**。

## 职责

角色简报 → 定角图 → 特征卡 → 平台角色资产注册（双平台）→ 入库锁定。

## 工作流

1. 生成定角图任务卡：OpenArt 图像模型，提示词含 character sheet 骨架
   （**多视图为可选社区实践，非强制**）。
2. 人回收 → agent 检查自洽性。
3. 扩充参考集任务卡：Higgsfield Shots 一图出多景别。
4. 平台注册任务卡：OpenArt Characters 训练（命名 `@ProjectChar`）+ Higgsfield Character
   anchoring（上传约 20–30 张，角色上限以 `capabilities.yaml` 为准；超限降级为纯图像参考）。
5. **填 identity_strategy**：`ref_order` / `prompt_lock_zh+en` / `negative_zh+en`，
   **不再写数值 weight**（双语供 UI/API 两通道复用）。
6. 可选填 `voice_ref`（角色需声纹绑定时，供 SK8 音频绑定）。
7. G3 通过后 `locked: true` + git commit。

## 提示词要点

- 定角图模板：简洁服装、避免复杂图案（一致性友好）；非人类/风格化造型优先（合规 + 抗漂移）。
- **第零层去 AI 味基座注入**（真实质感词）。
- `behavior_traits` 必填（SK5 行为逻辑素材源）。

## 脚本

`register_check.py`（校验参考集 ≤9 张且命名规范、platform.yaml 与 card.yaml 一致、
identity_strategy 四字段完整；`compliance.human_face` 告警；剧集 `variants[]` 校验：
variant_id 唯一 + ref_set ≤9 + 缺 state/appearance_delta 告警，返回 variant_count，B.2）。
