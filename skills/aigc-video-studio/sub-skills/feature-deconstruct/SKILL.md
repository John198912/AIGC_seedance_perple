---
name: feature-deconstruct
description: 逆向特征工程（SK12）：解构优秀作品 → 提取可迁移结构（C13）→ 反推为跨阶段创作指令（C14）。结构层承重、①②④顾问永不门控。
---

# SK12 · feature-deconstruct（逆向特征工程 · M1 模块内 MVP）

> 把推荐系统的「特征工程」反向用于创作：**解构优秀作品 → 提取可迁移结构 → 反推为跨阶段创作指令**。
> 详见《AIGC 逆向特征工程模块设计方案 v5.0 FINAL》第一/二/五部分与第九部分 M1 行。

## 价值定位（终版）

核心价值 = **结构层逆向 + 反向映射 + 共享字典**。受众①/场景②/行为④降为「顾问增强、永不门控」。
既有 C1–C11 不动，本模块只追加 C12–C14 与新 lib。

## 范围（M1，本次实现）

- 确定性、不触网、无 LLM/subagent；不改 budget_guard；不做 C15/G0/对抗校验/轴发现/版本化/贝叶斯（M2–M4）。
- 冻结次序：先冻字典轴集合 → 冻 C14 消费侧 → C13。

## 触发 / 输入 / 输出

- 触发：已有 N≥3 部同类优秀作品需提取可迁移结构。
- 输入：参考作品登记 **C12 ReferenceWork**（含 visual + structural 人工标注，仅文本/链接、媒体不入仓）。
- 输出：
  - **C13 FeatureTagSet**（每作品一份，中间件）；
  - **C14 CreativeDNA**（N≥3 共性交集 + 反向映射指令组，SK1–SK4 消费）。

## 共享库（_shared/libs/）

- `feature-dictionary.yaml`：受控本体，轴 + 取值范围；每轴 `domain/gating/signal_kind/information/maps_to/values`，semver，v0 seed。
- `axis-constraints.yaml`：稀疏冲突规则（`conflict/weak_conflict/requires`）。
- `source-credibility-rubric.yaml`：来源类型 → 定性档（high/med/low）。
- `ranking-weights.yaml`：算法信号定性档 + verified_at + source + confidence（定性，禁小数）。

## 数据模型（_shared/schemas/）

- **C12 ReferenceWork**：`{ref_id, title, source, media_manifest_ref?, annotations{visual,structural}, ip_note}`。
- **C13 FeatureTagSet**：`features[] = {feature_axis, value, domain, provenance(observed|sourced|inferred), confidence_tier(high|med|low), advisory, source_refs[], rationale?}`。结构层 content 承重；①②④打 advisory。
- **C14 CreativeDNA**：`transferable_patterns[] = {feature_axis, value, provenance, confidence_tier, maps_to[], directive, ip_layer:structural, specificity_ok}` + `coherence{conflicts,resolved}` + `forbidden[]`。
- validate.py 已注册 C12→reference_work / C13→featuretagset / C14→creativedna。

## 脚本（scripts/）

- `feature_dict.py`：加载/校验 feature-dictionary 与 axis-constraints；`get_axis` / `is_gating` / `check_coherence(选定轴值组)->冲突列表`。
- `deconstruct.py`：C12 → C13。结构层标 `observed`（承重、可门控）；①②④标 `advisory`（gating:false、`inferred`）。可复用 reference_analyzer 视觉 6 维归一。CLI：`--refs/--out/--json`。
- `reverse_map.py`：N≥3 份 C13 结构层共性交集 → 按字典 `maps_to` 生成 `directive` → coherence 校验（查 axis-constraints）→ 机械具体性地板（directive 必须含阶段+具体字段/槽位/数值 token，只含形容词→`specificity_ok=false` 判废）→ `inferred` 永不门控 → C14。单参考贡献模式数硬上限 ≤3。CLI 同风格。

## 工程纪律（写进实现）

1. **机械具体性地板**：用规则而非 LLM 自评；每条 directive 引用具体阶段 + schema 字段/镜头槽位/数值参数。
2. **幸存者偏差校正**：只做集合内相对比较，禁用绝对完播阈值。
3. **provenance 硬规则**：`inferred` 项进入 C14 仅作 `advisory`，永不门控（无外部锚点不升档，锚点逻辑 M2 落地）。
4. **IP 护栏**：N≥3 取交集而非 1:1 迁移；单参考模式数 ≤3；`forbidden[]` 禁迁具体角色/台词/分镜构图/BGM 旋律；结构/视觉相似性查表做不到，依赖 G0 人工闸（M2）。

## M2 · 受控推断 + 对抗校验 + G0 闸 + 词汇级 IP 预筛（设计稿第六/七部分）

> M2 全部确定性、不触网；真实 subagent/LLM 联网接线属**运行时**，脚本用 mock 取代（仿 vlm_screen）。
> 加法式：不改 advance_stage 的 G3/G6/G9 流程、不改 C1–C11/budget_guard。

### 三级来源标记（`provenance.py`）

可观测性 observed > sourced > inferred。编造 = 把 inferred 谎报为 observed/sourced。
**硬规则（决策点4）**：最终 confidence **只由外部锚点决定**——
- `observed`：视频本体 / 第一方实绩（origin:first_party）；
- `sourced`：`source_refs` 含 **≥2 独立来源**（不同 source domain）；
- `inferred`：无/不足外部源 → **封顶 inferred 地板、禁止升档**。
- `is_valid_anchor`：自产基率 / 标注 `origin: llm` 的来源**不算锚点**。
- `final_tier(feature)`：兜底判档；`apply_floor` 把档写回并对 inferred 标 advisory（永不门控）。

### 4 路研究编排（`research_orchestrator.py`，运行时接线）

运行时由 4 路 subagent（受众/场景/内容/行为）联网研究 → 汇集为特征。脚本为**确定性 mock**。
防幻觉契约：每条产出必须带 `source_refs`；**零来源 → `provenance: inferred` + `unverifiable: true`，
绝不伪造 observed/sourced**；**行为域④强制走 inferred**（不可由解构直接观测）。
真实接线：把 `_mock_inputs_from_refs` 替换为 4 路 subagent 调用结果，其余编排骨架不变。

### 对抗校验（`adversarial_check.py`）

subagent-A 提 inferred 特征 + rationale → subagent-B 红队（内部一致性 / 基率检验）→ 收敛。
**轮数封 1–2**；**无外部锚点时多轮只做内部一致性剪枝、绝不升档**（过 `provenance.final_tier` 兜底）；
输出保留 `objections` 与 `inference_method`。

### 词汇级 IP 预筛（`ip_prescreen.py` + lib `ip-keywords.yaml`）

只拦**词汇级**信号（照搬角色名/台词/slogan/专有名词），命中报 `lexical_hit[]`。
**诚实边界**：结构/视觉相似性查表做不到 → 固定输出 `structural_check: "defer_to_G0_human"`。

### G0 版权审查闸（`g0_gate.py`）

产出结构化审查记录（checklist：迁移的结构 / 不碰的表达 / 法域[中国《著作权法》|日本法] /
单参考贡献模式数 ≤3 校验 / lexical_hit 汇总），决议 `gate:G0, decision:pass|block,
reviewer:human_required`（G0 永不自动放行）。**追写一条 `g0_review` 事件到 `ledger/events.jsonl`**
（复用 ledger.py，与 G3/G6/G9 同构）。
**state-machine 集成点**（运行时，不在 M2 改）：在 reverse_map 产出 C14 后、SK1–SK4 消费前插 G0；
建议挂在 advance_stage 进入消费阶段前的人工闸，本期仅文档化，**不改 advance_stage**。

## 后续（不在 M2）

- M3：`deconstruct_cost_cap` 改造 budget_guard + verify_capabilities 扩展。
- M4：C15 后台导出 + 分层控混淆 + 轴发现 + 版本化字典 + 贝叶斯判据 + 日落。
