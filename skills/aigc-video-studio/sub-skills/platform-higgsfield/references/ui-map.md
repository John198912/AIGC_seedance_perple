# platform-higgsfield · 入口路径树（ui-map）

> verified_at: 2026-06-01（活文档，UI 迭代快；SK6 实测与此不符时提示更新）。

## 主入口

- `Cinema Studio`：timeline 式多镜编排工作室，主创作面。
- `Shots`：九宫格一次出多机位候选。
- `Angles`：机位/角度库。
- `Transitions`：转场库（供 EDL 转场参考）。
- `Grid`：比稿网格，并排多 take 比选。
- `Camera Controls`：70+ 运镜预设（对应 camera_presets_count=70）。

## 运镜预设入口（供 SK4 引用）

`Camera Controls` → 选预设（推/拉/摇/移/环绕等）→ 应用到镜头。运镜词→预设名映射维护在 `_shared/libs/camera-preset-map.yaml`。

## 角色锚定

支持 20-30 张角色锚定参考（character_anchor_refs="20-30"），多于 OpenArt，适合高一致性需求。

## 截图

`assets/cinema-studio-entry.png` 等关键入口截图，TaskCard 以 `ui_screenshot_refs` 引用，标 `verified_at`。
