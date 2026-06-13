# platform-openart · 入口路径树（ui-map）

> verified_at: 2026-06-01（活文档，UI 迭代快；SK6 实测与此不符时提示更新）。

## 主入口路径

- 首页 → `Models` → `Seedance 2.0`：单次文/图生视频。
- 首页 → `Characters`（角色训练）：上传 4+ 张同主体图 → 训练角色锚点 → 得 `@角色名` 可复用引用。
- 首页 → `Story`：多场景叙事编排，按场拼接。

## 角色训练入口（供 SK3 引用）

`Characters` → `Create Character` → 上传 multi_image（≥4 张，多角度/多光照）→ 命名 → 训练 → 产出可在生成时 `@` 引用的角色 ID。对应 capabilities 的 `character_methods: multi_image_4plus`。

## 生成入口（供 SK6 引用）

`Models / Seedance 2.0` → 填提示词 + 挂参考（图≤9/视频≤3/音≤3，总≤12）→ 选分辨率档 → 生成 → `My Creations` 下载。

## 截图

关键入口截图存 `assets/`，TaskCard 以 `ui_screenshot_refs` 引用，每张标 `verified_at`。
