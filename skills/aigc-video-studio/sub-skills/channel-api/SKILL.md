---
name: channel-api
description: 纯 reference 技能：fal.ai/火山方舟端点/认证（仅环境变量）/配额限流429/引用标签语法/seed 复现。
---

# SK11d · channel-api（API 通道手册）

> **纯 reference 技能**：v2.2 新增，不产契约，被 SK6/`api_adapter.py` 引用；从"平台"维度升为"通道"维度，专管 API draft 生成。详见设计稿 §5 SK11d。

## 性质

API 通道手册：管 fal.ai / 火山方舟两条 API 通道的端点、认证、配额、引用语法、seed 复现。能力数字进 `_shared/libs/capabilities.yaml` 的 `channels.*` 并挂 `verified_at`。

## references/

- `endpoints.md`：fal.ai / 火山方舟端点与入参结构。
- `auth.md`：认证——**仅环境变量** `fal_key_env`/`volcano_ak_env`（如 `FAL_KEY`/`VOLCANO_AK`），**绝不入仓、绝不写 project.yaml、绝不打印明文**。
- `quota.md`：配额 / 限流 / 429 重试退避 / 余额告警 / 降级为 UI 卡。
- `reference-tags.md`：`@Image1`/`@Video1`/`@Audio1` 引用语法（旧版 `[Image1]`，按 `verified_at` 核验）。
- `seed.md`：seed 复现说明（同 seed+同参→可复现，TakeLog 记 seed）。

## 安全纪律（强制）

凭证一律走环境变量，绝不入仓、绝不入 `project.yaml`。`api_adapter.py` / `verify_capabilities.py` 仅以 `os.environ.get` 检测凭证**是否存在**，绝不读取或打印其值。

## 维护策略

端点 / 配额变动快——挂 `verified_at`；`verify_capabilities.py` 心跳检查可用性与余额。

## 脚本

- `api_adapter.py`（共享，retry/fallback/降级，凭证仅读 env）。
- `verify_capabilities.py`（共享，健康心跳 + 月度重验告警）。
