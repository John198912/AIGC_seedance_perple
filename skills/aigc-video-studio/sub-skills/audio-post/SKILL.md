---
name: audio-post
description: 音频策略与执行：原生音优先评估→BGM/配音/音效补充任务卡→音画对齐说明；支持 voice_bind 声纹绑定。
---

# SK8 · audio-post（音画合成）

> 音频策略与执行。注：音画合成不计入 MVP 验收门槛（设计稿 §9）。详见设计稿 §5 SK8。

## 输入 / 输出

- 输入：选定 takes + screenplay 情绪曲线 + `GenSpec.audio_mode`。
- 输出：`07_audio/audio-plan.md` + 外部音频工具任务卡 + 素材登记（含版权来源）。

## Gate

**G7 音画合成确认**（默认自动；premium 档可开人工确认）。

## 职责

音频策略与执行：原生音优先评估 → BGM/配音/音效补充任务卡 → 音画对齐说明。

## 提示词要点

1. **决策树（按 audio_mode）**：native 时利用 Seedance 原生同期音/环境音，audio_cue 分段
   精细化（利用双声道）；post_mix 时 BGM 走 Suno（提示词模板 BPM/调性/段落对齐情绪节拍）。
2. 需对白优先 Seedance 原生口型，失效再走 ElevenLabs + HeyGen。
3. **版权登记强制**。
4. **ambience_group**：同场景共享环境音，EDL 加"环境音桥接"轨道，根治跨镜音频割裂。
5. **voice_bind**：若角色卡填了 `voice_ref`，各镜配音按角色声纹绑定（跨镜一致）；
   无 voice_ref 则退回逐场指定。

## 脚本

`audio_manifest.py`（素材清单 + 时间轴对齐表 + voice_bind 映射 + ambience 桥接：
同 `ambience_group` 镜头生成共享环境音床 bed_start_s/bed_end_s，A.3）。
