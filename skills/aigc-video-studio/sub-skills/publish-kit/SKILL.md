---
name: publish-kit
description: 多画幅适配、封面首帧选取、各平台元数据包、冷启动建议、AIGC 声明合规与 IP 风险核验。
---

# SK10 · publish-kit（发布分发）

> 把 master 成片打包为各目标平台的可发布物料。注：发布不计入 MVP 验收门槛（设计稿 §9）。详见设计稿 §5 SK10。

## 输入 / 输出

- 输入：master 成片 + `target_platform`（如 douyin/bilibili/youtube/xiaohongshu）。
- 输出：`09_publish/<platform>/` 发布包（成片画幅变体 + 封面候选 + 元数据 + 合规声明）。

## Gate

**G9 发布确认**（人工终确认，发布动作不可逆，须导演签字）。

## 职责

多画幅适配、封面首帧选取、各平台元数据包、冷启动建议、AIGC 声明合规。

## 提示词要点

1. **平台规则表**（画幅/时长偏好、AIGC 标注义务）维护在 `references/platform-rules.md` 并挂 `verified_at`，活文档，发现与实际不符即提示更新。
2. **多画幅适配**（半自动 P2）：`render_variants.py` 按 21:9 → 16:9 → 9:16 → 1:1 主轴裁切，安全框保护主体不出画；竖屏优先保中心人物。
3. **封面半自动**（P2）：`cover_extractor.py` 从 `shotlist` 标注的记忆点镜头抽首帧候选，导演择一。
4. **IP 合规拆分**（S-P1-9）：致敬/改编类发布**前**核验版权风险，命中即在发布包标注风险并阻断自动发布。
5. **AIGC 声明强制**：按目标平台标注义务自动生成 AIGC 标识与水印说明。
6. **冷启动建议**：依平台调性给标题/标签/首图/发布时段建议（仅建议，不代发）。

## 脚本

- `render_variants.py`（21:9→16:9→9:16→1:1 裁切；`--project` 调 `build_package` 产出 `09_publish/<platform>/` 发布包：多画幅 + 封面 + 元数据 + `aigc-declaration.md` 强制声明）。
- `cover_extractor.py`（从记忆点镜头提封面候选，被 `build_package` 复用）。
