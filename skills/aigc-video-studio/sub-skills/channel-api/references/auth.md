# API 认证（auth）

> verified_at: 2026-06-01。**安全纪律：认证凭证仅走环境变量，绝不入仓、绝不入 project.yaml、绝不打印明文。**

## 凭证来源（唯一）

| 通道 | 环境变量 | project.yaml 字段 |
|---|---|---|
| fal.ai | `FAL_KEY` | `fal_key_env: FAL_KEY`（只存**变量名**，不存值） |
| 火山方舟 | `VOLCANO_AK` | `volcano_ak_env: VOLCANO_AK`（只存变量名，不存值） |

`project.yaml` 里 `*_env` 字段存的是**环境变量名**，不是密钥本身。

## 程序读取约束

- `api_adapter.py` / `verify_capabilities.py` 仅以 `os.environ.get(name)` 检测凭证**是否存在**。
- **绝不读取其值用于日志/落盘/回显**，缺失时报"凭证未配置"并降级为 UI 卡，不暴露任何明文。
- 任何 take/卡/账务记录都不得写入密钥。

## 缺失处理

环境变量未设置 → API 卡无法执行 → `api_adapter` 降级提示转 UI 卡人工执行，不阻断闭环。
