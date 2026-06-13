# platform-jimeng · 踩坑（quirks）

> verified_at: 2026-06-01（活文档）。

## 国内合规与水印（强制）

- **AIGC 标注义务**：国内平台发布须按规定标注 AI 生成，SK10 发布包自动生成标识。
- **平台水印**：导出可能带平台水印，终渲前确认水印规则；商用素材注意去水印授权。
- **内容合规**：敏感词/题材按国内规则更严，SK5 编译时跑 `compliance-map.yaml` 语义替换。

## 与火山方舟 API 的差异

- **入口**：即梦 UI vs 火山方舟 API，同源模型但参数表达不同。
- **画幅枚举**：UI 与 API 可用画幅档可能不一致，以 `capabilities.yaml` 的 `channels.volcano` 与本文档实测为准。
- **凭证**：火山方舟 API 凭证仅走环境变量 `VOLCANO_AK`，绝不入仓。
