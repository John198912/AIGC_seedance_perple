# 状态机与 Gate 规则全文

> 占位骨架（Phase 1）。详见设计稿 §7.1。

```
S0_IDEA → S1_BRIEF →(G1)→ S2_SCRIPT →(G2)→ S3_CHARACTER →(G3✱)→
S4_STORYBOARD →(G4)→ S5_PROMPTS（内含 S4.5 Previs 轻量编译模式）→(G5?)→
S6_GENERATION →(G6✱ 逐批选片)→ S7_AUDIO_POST →(G7?)→ S8_EDIT →(G8)→
S9_PUBLISH →(G9)→ DONE
```

- ✱ 强制人工 Gate：G3 角色定稿 / G6 选片永不自动。
- ? 可配置自动：G5 提示词抽查 / G7 音画合成确认。
- S4.5 Previs：SK5 的轻量编译模式（非独立 stage/技能）。
- 降级链：480p API draft →（不可用）仅关键镜 720p API →（仍不可用）文字分镜 + 静态首帧。
