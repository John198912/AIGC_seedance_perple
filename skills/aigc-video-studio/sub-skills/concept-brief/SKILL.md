---
name: concept-brief
description: 把主题/灵感扩展为 ProjectBrief（C2）：logline/世界观/风格基调/画幅/时长/平台/单片或剧集判定。
---

# SK1 · concept-brief（创意策划）

> 创意入口：把一句话灵感扩展为可执行的项目蓝图。详见设计稿 §5 SK1。

## 触发 / 输入 / 输出

- 触发：用户提出新项目创意（允许一句话）。
- 输入：用户创意描述；可选参考图/片。
- 输出：`01_brief/brief.md`（C2）+ `03_style/style-bible.md` 初稿 + `project.yaml` 初始化。

## Gate

**G1 创意确认**。

## 职责

把主题/灵感扩展为 ProjectBrief：logline、世界观、风格基调、参考片、画幅、时长、平台、
单片/剧集判定。

## 提示词要点

1. **访谈式补全**：缺要素一次性问全（题材 / 情绪 / 时长 / 平台 / 对标）。
2. **强制产出 2–3 个差异化方向**（每个含 logline + 风格关键词 + 预估成本档）。
3. 风格圣经从 `style-presets.md` 实例化。
4. **合规前置**：涉真人脸/敏感题材即提示替代方案（非人类主角等）。
5. **IP 合规前置**：若涉已有 IP/角色致敬，标注发布端风险。

## 脚本

- 纯推理部分复用 `validate.py` 校验 C2。
- `scripts/concept_advisory.py`：对标驱动顾问路径（M3，见下）。

## 对标驱动顾问路径（M3）

把逆向特征工程（SK12）产出的 **C14 CreativeDNA / reverse-map** 转成 concept-brief 的
**对标驱动顾问建议**，仅覆盖受众①(target_audience)、场景②(viewing_scene)、行为④
(engagement hints) 三类**顾问增强**轴。

**硬规则**（承接 SK12 M2 三级来源 / 决策点4）：

- ①②④ 为**顾问增强、永不门控、创作者可覆盖**——绝不进硬约束、`gating` 恒为 `false`。
- 每条建议的最终 `provenance` 过 `provenance.final_tier` 兜底（只由外部锚点决定：
  ≥2 独立锚点→sourced；第一方实绩→observed；否则封顶 inferred）。
- inferred 项标 `advisory:true`；**行为域④即便有锚点也维持 advisory**（forced inferred 精神）。

**脚本** `concept_advisory.py`：

- `build_advisory(dna, reverse_map=None)` → `{advisory_suggestions[], count, note}`，
  每条 `{axis,value,domain,provenance,advisory:true,overridable:true,gating:false,rationale}`。
- `merge_into_brief(brief, advisory)` → 把建议挂到 brief 的**新建 `advisory_block`** 字段，
  原 brief 的 logline/世界观/风格等**一律不动**。
- CLI：`--dna`、可选 `--reverse-map`、`--brief`、`--json`。确定性、不触网、无 LLM。
