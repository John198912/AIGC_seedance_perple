---
name: aigc-video-studio
description: AIGC 短视频/短剧创作入口与编排技能（SK0）。意图路由、状态机推进、Gate 管理、子技能调度、预算护栏、流水线并行调度、UI/API 通道决策、API 健康心跳。
---

# SK0 · aigc-video-studio（入口 / 编排）

> 唯一面向用户的入口技能。负责"想清楚 + 写清楚 + 管起来 + 按 pass 路由到正确通道"，
> 全程绝不替导演做审美判断。详见设计稿 §5 SK0 / §7 / §4 单写者矩阵。

## 触发

用户提出任何 AIGC 短视频/短剧创作意图，或要求继续推进既有项目。

## 职责

1. **意图路由**：依当前 `project.yaml.stage` 与用户意图，把请求路由到对应子技能。
2. **状态机推进与 Gate 管理**：校验当前 stage 产物齐备 + 关卡 Gate 已 passed 才推进；
   G3（角色定稿）/ G6（选片）为强制人工 Gate，永不自动。
3. **按 stage 自动加载子技能**（路由表见下）。
4. **预算护栏**：每批次发出前核算成本，单镜按 `min(project, genspec)` 上限拦截，
   总预算超 `alert_threshold` 告警，`ai_qc_cost_cap` 拦截 VLM/Judge 推理超支。
5. **回退与版本快照**：推进后落 `versions[]` 快照 + 自动 git commit；任意 Gate 可申请回退。
6. **流水线并行调度**：在人工/选片等待窗口并行推进可独立的下游任务（编译下一批 / 处理已选镜音频）。
7. **通道决策**：依 `project.execution_default` 与镜头 `control_level`/`lens_type`
   决定 UI/API 分流（draft→API 抽卡、final→UI 终渲）。
8. **API 健康心跳**：按 `api_config.health_heartbeat_min` 心跳 fal/火山余额与可用性；
   余额低于 `balance_alert_cny` 或配额耗尽时按 `fallback_on_quota_exhausted: ui_only` 降级并告警。

## 输入 / 输出

- 输入：用户自然语言 + `project.yaml` + 各阶段产物状态。
- 输出：子技能调度决策；Gate 申请话术（呈现"产出物摘要 + 决策点 + 选项"）；阶段总结；流水线调度表。

## 提示词要点

- **状态 → 技能路由表**（见下）；新项目先走 SK1，既有项目按 stage 续接。
- **Gate 申请标准话术**：呈现产出物摘要 + 决策点 + 选项，**绝不替导演做审美判断**。
- **"动态编剧法"应对规则**：判定改动影响半径并报告代价后执行——
  仅本镜头 → 局部重跑 S5/S6；影响角色 → 回退 G3；影响叙事 → 回退 G2。

## 状态 → 子技能路由表

| stage | 子技能 | Gate |
|---|---|---|
| S0_IDEA / S1_BRIEF | `concept-brief`(SK1) | G1 创意确认 |
| S2_SCRIPT | `screenplay-writer`(SK2) | G2 剧本确认 |
| S3_CHARACTER | `character-foundry`(SK3) | **G3 角色定稿（强制）** |
| S4_STORYBOARD | `storyboard-director`(SK4) | G4 分镜节奏确认 |
| S5_PROMPTS（含 S4.5 Previs 轻量编译） | `prompt-compiler`(SK5) | G5 提示词抽查（可选） |
| S6_GENERATION | `gen-runner`(SK6) + `qc-review`(SK7) | **G6 选片（强制）** |
| S7_AUDIO_POST | `audio-post`(SK8) | G7 音画确认（默认自动） |
| S8_EDIT | `edit-finish`(SK9) | G8 终审 |
| S9_PUBLISH | `publish-kit`(SK10) | G9 发布确认 |
| 任意（平台操作） | `platform-openart/higgsfield/jimeng`(SK11a/b/c) · `channel-api`(SK11d) | — |

## 脚本

| 脚本 | 职责 | 优先级 |
|---|---|---|
| `scripts/init_project.py` | 目录骨架 + git init + 生成 .gitignore/.gitattributes/media-manifest（支持 `--format short_film/series/quick_test`，B.1） | P0 |
| `scripts/advance_stage.py` | 校验产物齐备 + Gate passed 才推进 + 落版本快照 + 自动 commit（project.yaml 状态段唯一写者） | P1 |
| `scripts/budget_guard.py` | 每批次发出前核算 + 单镜 min(cap) 拦截 + 告警 + ai_qc_cap + 追写 events.jsonl；按 channel-cost-map 估算渠道成本 + 选最便宜可用渠道（A.5） | P1 |
| `scripts/pipeline_scheduler.py` | 流水线并行调度表（只读，不改状态） | P1 |
| `scripts/verify_capabilities.py` | 能力表 verified_at 过期校验 + API 健康心跳（凭证仅读 env 存在性） | P1 |
| `scripts/episode_manager.py` | 剧集模式：创建/列出剧集（每集独立 shotlist+工作区）+ 剧级 dashboard 汇总（仅 series，B.1） | P1 |
| `scripts/reuse_shots.py` | 复用镜头库索引（空镜/转场/素材）注册与按标签查询（B.4）；V2.2+ 深化为带标签资产索引 `asset-index.yaml`（空镜/转场/角色变体，tags+source+hash+reuse_scope，D-6） | P2 |
| `scripts/lessons_writeback.py` | 结案把命中率/失败模式经验回写 cross-project-lessons.yaml（活文档，B.6） | P2 |
| `scripts/feedback_intake.py` | V2.2+ 观众反馈闭环（D-7）：读 C11 原始反馈 → 聚合情感/类别 → 回写经验库（幂等，仅经验文本不入契约能力数字） | P2 |
| `scripts/backup.py` | 关键资产 sha256 备份清单（灾备） | P2 |
| `sub-skills/_shared/scripts/cost_report.py` | V2.2+ 隐性成本统计（Q-12）：在事件源账本上投影重试/废 take/AI-QC/上传带宽/人工工时折算，产隐性成本报告 | P2 |

## 设计纪律

- **凭证一律走环境变量**（`fal_key_env`/`volcano_ak_env`），绝不入仓、绝不写 `project.yaml`。
- **能力数字只读 `capabilities.yaml`** 并校验 `verified_at`，不在脚本硬编码。
- **单写者矩阵**（§4）：`project.yaml` 状态段 → advance_stage；`events.jsonl` → budget_guard/ingest；
  `takes.yaml` → ingest/vlm_screen；`capabilities.yaml` → verify_capabilities。

## references/

- `references/methodology.md` — 白皮书方法论精编 + 「作者实际控制面」澄清节。
- `references/state-machine.md` — 状态机 S0–DONE + Gate 规则 + S4.5 Previs + G7 + 降级链。
- `references/profiles.md` — premium/series/rapid/exploration 四档配置。
- `references/collaboration.md` — V2.2+ 团队协作约定（D-4）：Git 分支式协作、无内置权限、
  PR 评审关注点、契约/账本/经验库冲突处理、与学习回路衔接。
