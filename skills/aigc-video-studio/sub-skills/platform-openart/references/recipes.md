# platform-openart · 高频配方（recipes）

> verified_at: 2026-06-01（活文档）。

## 配方 1 · 角色训练 SOP（角色一致性基座）

1. 备 4+ 张同主体图：正面 / 侧面 / 半身，覆盖多光照与表情，背景尽量干净。
2. `Characters → Create Character` 上传 → 命名（与 `CharacterCard.id` 对齐，如 `@锈牛仔`）。
3. 训练完成后跑小样测试：换 3 个场景生成，肉眼校验五官/服饰/配饰一致。
4. 一致性达标后登记进角色卡 `reference_assets`，供 SK5 编译时 `@` 引用。

> 与 reference_label_map 配合：语义名 `@锈牛仔` → API 占位符 `@Image1`（见 channel-api/reference-tags.md）。

## 配方 2 · Story 分场编排

`Story` 按场建条目 → 每场注入角色 `@` 引用 + 场景关键词 → 逐场生成 → 跨场沿用同一角色锚点保身份一致。

## 配方 3 · 单镜图生视频

`Models/Seedance 2.0`：首帧图 + 四层提示词 → 480p/720p draft 抽卡 → 中选后 1080p 终渲。
