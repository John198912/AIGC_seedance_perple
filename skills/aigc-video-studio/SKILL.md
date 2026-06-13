---
name: aigc-video-studio
description: AIGC 短视频创作入口/编排技能（SK0）。意图路由、状态机推进、Gate 管理、子技能调度、成本护栏、流水线并行调度。
---

# SK0 · aigc-video-studio（入口/编排）

> 占位骨架（Phase 1）。完整提示词在后续阶段填充，详见设计稿 §5 SK0。

## 触发

用户提出任何 AIGC 短视频/短剧创作意图，或继续推进既有项目。

## 职责

1. 意图路由
2. 状态机推进与 Gate 管理
3. 按 stage 自动加载子技能
4. 预算护栏（含单镜成本上限）
5. 回退与版本快照（+ git commit）
6. 流水线并行调度：在人工/选片等待窗口并行推进可独立的下游任务
7. 通道决策：依 `project.execution_default` 与镜头 `control_level`/`lens_type` 决定 UI/API 分流

## 脚本

| 脚本 | 职责 | 优先级 |
|---|---|---|
| `scripts/init_project.py` | 目录骨架 + git init + 生成 .gitignore/.gitattributes/media-manifest | P0 |
| `scripts/advance_stage.py` | 状态推进 + Gate 校验 + 版本快照 + 自动 commit | P1 |
| `scripts/budget_guard.py` | 账本检查 + 预算告警 + 单镜成本上限 | P1 |
| `scripts/pipeline_scheduler.py` | 流水线并行调度表 | P1 |
| `scripts/backup.py` | 关键资产定期备份（灾备） | P2 |
| `scripts/verify_capabilities.py` | 平台能力/价格变更校验 + API 健康心跳 | P1 |

## 子技能

`concept-brief`(SK1) · `screenplay-writer`(SK2) · `character-foundry`(SK3) · `storyboard-director`(SK4) · `prompt-compiler`(SK5) · `gen-runner`(SK6) · `qc-review`(SK7) · `audio-post`(SK8) · `edit-finish`(SK9) · `publish-kit`(SK10) · `platform-openart/higgsfield/jimeng`(SK11a/b/c) · `channel-api`(SK11d)

## 状态机

```
S0_IDEA → S1_BRIEF →(G1)→ S2_SCRIPT →(G2)→ S3_CHARACTER →(G3✱)→
S4_STORYBOARD →(G4)→ S5_PROMPTS（内含 S4.5 Previs 轻量编译模式）→(G5?)→
S6_GENERATION →(G6✱ 逐批选片)→ S7_AUDIO_POST →(G7?)→ S8_EDIT →(G8)→
S9_PUBLISH →(G9)→ DONE
```

✱ 强制人工 Gate（G3 角色定稿 / G6 选片永不自动）。详见 `references/state-machine.md`。
