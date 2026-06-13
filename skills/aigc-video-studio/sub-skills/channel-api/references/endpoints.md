# API 通道端点（endpoints）

> verified_at: 2026-06-01（活文档；端点变动快，以 `_shared/libs/capabilities.yaml` 的 `channels.*` 为机读事实源）。

## fal.ai 通道

- 端点：`fal-ai/bytedance/seedance-2.0/fast/reference-to-video`
- 分辨率枚举：`[480p, 720p, 1080p]`（详情页口径；营销页仅 480p/720p）
- 引用语法：`@ImageN`（见 `reference-tags.md`）
- 入参结构（要点）：`prompt`（四层提示词文本）+ `references[]`（图/视频/音，总≤12）+ `resolution` + `seed`（可选）
- available_since: 2026-04-09
- source: https://fal.ai/seedance-2.0

## 火山方舟（volcano）通道

- 类型：API，火山方舟个人可接入
- 与即梦 UI 同源模型，参数表达差异见 `platform-jimeng/references/quirks.md`
- available_since: 2026-04-14
- source: https://seed.bytedance.com/zh/seedance2_0

## 入参与 GenSpec 映射

`api_adapter.py` 把 `GenSpec.render_passes[]` 的 draft pass 翻成端点入参：`prompt` ← 四层编译文本，`references[]` ← `reference_label_map` 解析后的占位符，`resolution` ← pass 档位（draft 多为 720p）。
