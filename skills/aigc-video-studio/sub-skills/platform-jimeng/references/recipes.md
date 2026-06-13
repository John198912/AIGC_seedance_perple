# platform-jimeng · 高频配方（recipes）

> verified_at: 2026-06-01（活文档）。

## 配方 1 · 沉浸式短片（中文提示词）

`沉浸式短片` → 中文四层提示词直注（去 AI 味基座用废土/纪实等中文质感词）→ 挂角色参考 → 生成。中文原生理解强，无需英译。

## 配方 2 · 原生同期音利用

即梦/Seedance 原生支持同期音/环境音（native_audio=true）。SK8 `audio_mode=native` 时优先用原生音，`audio_cue` 分段精细化，减少后期配音。

## 配方 3 · 与火山方舟 API draft 协同

探索期用火山方舟 API 卡（720p draft）快抽卡；中选 take 转即梦 UI 卡 1080p 终渲，兼顾速度与画质。注意两入口画幅枚举/水印差异（见 quirks）。
