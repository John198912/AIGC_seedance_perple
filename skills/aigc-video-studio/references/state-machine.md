# 状态机与 Gate 规则全文

> SK0 状态推进（`advance_stage.py`）的规则全文。详见设计稿 §7.1。

## 一、状态机定义（project.yaml.stage）

```
S0_IDEA → S1_BRIEF →(G1)→ S2_SCRIPT →(G2)→ S3_CHARACTER →(G3✱)→
S4_STORYBOARD →(G4)→ S5_PROMPTS（内含 S4.5 Previs 轻量编译模式）→(G5?)→
S6_GENERATION →(G6✱ 逐批选片)→ S7_AUDIO_POST →(G7?)→ S8_EDIT →(G8)→
S9_PUBLISH →(G9)→ DONE
```

线性顺序（`advance_stage.STAGE_ORDER`）：
S0_IDEA · S1_BRIEF · S2_SCRIPT · S3_CHARACTER · S4_STORYBOARD · S5_PROMPTS ·
S6_GENERATION · S7_AUDIO_POST · S8_EDIT · S9_PUBLISH · DONE。

## 二、推进前置条件（advance 校验）

推进到某 stage 前，**当前 stage 的产物**必须齐备（存在性 glob 检查）：

| 当前 stage 应齐备的产物 |
|---|
| S1_BRIEF → `01_brief/brief.md` |
| S2_SCRIPT → `02_screenplay/screenplay.md` |
| S3_CHARACTER → `03_characters/*/card.yaml` |
| S4_STORYBOARD → `04_storyboard/shotlist.yaml` |
| S5_PROMPTS → `05_prompts/genspecs/*.yaml` |
| S6_GENERATION → `06_generations/*/takes.yaml` |
| S7_AUDIO_POST → `07_audio/audio-plan.md` |
| S8_EDIT → `08_edit/edl.md` |
| S9_PUBLISH → `09_publish/**/*` |

产物缺失或 Gate 未过即不推进，返回修复指引（`--force` 可人工跳过但仍落快照与事件）。

## 三、Gate 规则

- ✱ **强制人工 Gate（永不自动）**：
  - **G3 角色定稿**：离开 S3 进 S4 的前置（`STAGE_REQUIRED_GATE["S4_STORYBOARD"]`）。
  - **G6 选片**：离开 S6 进 S7 的前置（`STAGE_REQUIRED_GATE["S7_AUDIO_POST"]`），核心审美决策。
- **? 可配置自动**：
  - **G5 提示词抽查**：premium 抽 20%，`prompt_qc.py` 自动评分通过后可降低人工抽查比例。
  - **G7 音画合成确认**（默认自动）：SK8 产出 audio-plan 后默认自动过；premium 档可开
    人工确认（听原生音/配音与画面是否同步、情绪节拍是否对齐）。
- 任意 Gate 可申请回退；局部重跑仅将个别镜头送回 S5/S6，不动全局 stage。

## 四、S4.5 Previs 轻量编译模式

S4.5 Previs **不是独立 stage、也不是独立技能**，而是 **SK5 的一个轻量编译模式**：
仅编译关键帧 + 走 480p API draft 出 1 take/镜 → 粗剪验证节奏 → 把 G4 从"看静图"
升为"看动态粗剪"确认。Previs 成本上限不超项目总预算 5%。

## 五、降级链（Previs / 缺 API 时）

```
480p API draft → （不可用时）仅关键镜 720p API → （仍不可用）文字分镜 + 静态首帧
```

## 六、版本快照与账本

- 每次推进落 `project.yaml.versions[]` 快照（v / stage_from / stage_to / at / forced）。
- 状态变更追写 `ledger/events.jsonl`（`type=stage_advance`，不计费）。
- 推进后自动 git commit（git 不可用则跳过、不阻断）。
