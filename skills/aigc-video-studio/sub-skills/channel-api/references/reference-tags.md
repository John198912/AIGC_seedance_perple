# 引用标签语法（reference-tags）

> verified_at: 2026-06-01（活文档；语法变动快，按 verified_at 核验）。详见设计稿 §6.4。

## 当前语法

| 模态 | 占位符 | 上限 |
|---|---|---|
| 图像 | `@Image1` … `@Image9` | 9 |
| 视频 | `@Video1` … `@Video3` | 3 |
| 音频 | `@Audio1` … `@Audio3` | 3 |

跨模态总文件 ≤ 12（fal.ai 官方 "Total files ≤ 12"）。

## 旧版语法

旧版用方括号 `[Image1]`；当前为 `@` 前缀。SK6 出卡前按 `verified_at` 核验目标通道当前语法。

## reference_label_map（语义名 → 占位符）

SK5 编译时生成映射，写入 `.api.json`：

```
@锈牛仔     → @Image1
@废土荒漠    → @Image2
@沙暴环境音   → @Audio1
```

提示词正文用语义名书写，发 API 前由 `api_adapter.py` 按 map 替换为占位符；溢出 12 上限的参考由 SK5 槽位预算分配器按优先级（身份>构图>风格>环境）丢弃并记 `slots_dropped[]`。
