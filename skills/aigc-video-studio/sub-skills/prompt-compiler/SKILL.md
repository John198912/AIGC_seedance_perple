---
name: prompt-compiler
description: 镜头表→GenSpec（C6）：第零层去AI味+四层结构编译+槽位预算分配+render_passes+reference_label_map+Prompt QC。
---

# SK5 · prompt-compiler（提示词编译）

> 把镜头表编译为可执行 GenSpec（C6）。提示词工程的咽喉。详见设计稿 §5 SK5 / §6。

## 触发 / 输入 / 输出

- 触发：G4 通过、进入 S5_PROMPTS。
- 输入：`shotlist.yaml` + 角色卡 + `style-bible` + `platform_strategy`。
- 输出：`05_prompts/genspecs/SHOT-xx.yaml` 全量（C6）。

## Gate

G5 提示词抽查（可选，premium 抽 20%；`prompt_qc.py` 自动评分通过后可降低人工抽查比例）。

## 编译管线（提示词内固化为步骤）

0. **第零层·去 AI 味基座**：从 `deai-keywords.yaml` 注入强制正向词（超写实/胶片颗粒/真人
   实景质感）+ 强制反向词（杜绝 CG 感/塑料皮肤/磨皮）。
1. **设定层**：从 `CharacterCard.feature_card` 注入（禁止徒手重写）+ 场景 + audio_cue。
2. **风格层**：从 `style-bible` 注入。
3. **分镜层**：景别/运镜/坐标化构图/动作（行为逻辑增强，§6.2）。
4. **合规过滤**：跑 `compliance-map.yaml`，记 `compliance_applied`。
5. **一致性表达**：按 `identity_strategy`（ref_order/prompt_lock/negative）组装，
   **不再写数值权重**；参考文件总数 ≤12（图9/视频3/音3，以 `capabilities.yaml` 为准）。
6. **平台方言**（§6.4）。
7. **模型路由**：按 `lens_type` 查 `model-router-rules.yaml`（默认 Seedance 2.0，已删 Sora）。
8. **render_passes 编译**：不写单标量 channel，按 control_level + execution_default 生成
   `render_passes[]`（draft:api/720p/rolling；final:ui/1080p/source_take:selected；
   locked 镜可只保 final 一 pass、free 镜可只保 draft）。
9. **槽位预算分配器**：参考位总数 ≤ 平台上限，按优先级（身份>构图>风格>环境）分配，
   溢出记 `slots_dropped[]` 并告警。
10. **reference_label_map**：语义名（@锈牛仔）→ API 占位符（@Image1），写入 .api.json。
11. **语言策略**：volcano/jimeng → 中文；falai/higgsfield/openart → 英文。
12. **音频模式**：评估原生音可行性，标 `audio_mode`。
13. **Prompt QC 两级**：`structural_blockers`（八要素缺项=硬阻断，确定性无噪声）
    + `craft_score`(≥75) + `deai_score`(≥70) + `rubric_anchor_drift`(>15 告警)，
    按 `judge-rubric.md` 校准（语义评分仅排序/标红，不阻断）。

## Previs 轻量编译（S4.5）

非独立技能，而是本技能的轻量模式：仅编译关键帧 + 走 480p API draft 出动态分镜，供 G4 动态确认。

## 脚本

- `compile_genspec.py`（模板渲染 + C6 校验 + 槽位预算 + reference_label_map 生成；行为逻辑分层注入 §6.2 R1–R5（戏种模板取角色 behavior_traits 填动机，A.1）+ 坐标化构图块（A.2）+ continuity 尾帧延续段（A.4）+ `compile_variants` A/B 变体并行（exploration 档，B.5）；`--project` 自动加载角色卡）。
- `compliance_check.py`（敏感词语义替换 + forbidden 残留扫描）。
- `prompt_qc.py`（两级处理：结构硬阻断 + 语义评分，读 judge-rubric）。

## V2.2+ 扩展（D-2 参考片风格迁移，半自动）

- `reference_analyzer.py`（**半自动·需人工确认**）：输入参考片元数据/人工标注
  （色调/胶片颗粒/光照/构图法/运镜/节奏），做确定性 mock 视觉分析（非真实模型），
  抽出风格描述符 → 产 `03_style/style-transfer-suggestion.md` + 可并入 style-bible 的
  结构化片段。描述符默认 `confirmed:false`，须导演逐项确认后方可注入，不自动改 style-bible。
