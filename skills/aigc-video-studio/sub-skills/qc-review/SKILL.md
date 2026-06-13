---
name: qc-review
description: 镜头级/序列级/成片级三类检查；产出 QCReport（C10）；VLM 初筛为一等公民（协议分层）。
---

# SK7 · qc-review（质检评审）

> 三层质检 + VLM 自动初筛（一等公民），但 G6 选片永不自动。详见设计稿 §5 SK7。

## 输入 / 输出

- 输入：takes + shotlist + 角色卡。
- 输出：`08_edit/qc-report.md`（C10）：问题定位到镜头 + 时间码，每条分级
  blocker/major/minor + AI 置信度 + 最低成本处置建议。

## 职责（三类检查）

- **A 镜头级**：选片前 VLM 自动初筛（协议分层）。
- **B 序列级**：跨镜一致性 / 方向轴线 / 时代错配。
- **C 成片级**：终审清单。

## 提示词要点

- 检查清单硬编码自白皮书踩坑表（角色漂移/穿模/透视异常/时代错配/AI 逻辑错误/音画不同步）。
- 接入 `failure-patterns.yaml`：按模型/平台匹配已知失败模式，命中即给修复路径。
- 处置路径优先级：**剪辑规避 > 局部重跑 > 整镜重做**。

## VLM 配置化（协议分层）

VLM 初筛参数（协议 static/dynamic、采样点、提示词、置信阈值、成本单价）全部外部化到
`libs/vlm-config.yaml`：静态项（身份/质感/时代错）走 static 单帧，动态项（运镜方向/动作
可读）走 dynamic 首-中-尾三帧；Judge 按 `judge-rubric.md` 样本校准。

> VLM 初筛是**一等公民**，用于自动淘汰废片、把选片人工时间降 50%+；但 **G6 选片永不
> 自动**——VLM 只初筛不决策审美；置信不足记 `unverifiable` 转人工。

## 脚本

- `qc_template.py`（按 shotlist 生成逐镜检查表骨架，C10）。
- `vlm_screen.py`（共享 SK6，读 vlm-config 协议分层初筛）。
- `cross_episode_drift.py`（剧集：跨集同角色一致性比对，复用 vlm_screen mock 裁决，
  输出漂移报告 + Markdown，B.3）。
