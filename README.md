# AIGC 短视频创作 Agent Harness Skills 系统

> 基于 Seedance 2.0 的精品 AIGC 短视频创作工作流系统，实现自《AIGC 短视频创作 Agent Harness Skills 工作流系统方案 v2.2（功能级设计稿）》。

本系统把"导演—演员"创作方法论固化为一套 **agent harness skills**：以**混合执行面（UI + API）**为生成通道、以**任务卡（TaskCard）**为人机接口、以**文件契约**为状态载体、以 **Git** 为版本历史。系统承担编排、编译、登记与可复现的重活，让创作者把全部精力放在审美与叙事决策上。

---

## 项目概述

- **方法论层**：导演—演员范式 · 去 AI 味基座 · 四层提示词结构 · 批量抽卡 · 动态编剧法。
- **技能层**：`aigc-video-studio` 技能包 = 1 个入口技能（SK0）+ 11 个功能技能（SK1–SK11d）+ 共享库。
- **契约层**：10 个文件契约 C1–C10（project / brief / screenplay / character / shotlist / genspec / taskcard / ledger / takelog / qcreport），落为 JSON Schema，所有脚本读写前强制校验。
- **执行层（混合）**：UI（人工，OpenArt / Higgsfield / 即梦）承接强交互/审美环节；API（自动，fal.ai / 火山方舟）承接确定性批量。
- **资产层**：`projects/<slug>/` 文件树，文件即状态，Git 托管文本契约，媒体走 `.gitignore` + `media-manifest.yaml` 治理。

### 关键设计纪律

1. **平台能力数字只进 `capabilities.yaml` 并挂 `verified_at`**，正文不写死易变数字，月度重验。
2. **API 凭证绝不入仓**：仅从环境变量读取（`FAL_KEY` / `VOLCANO_AK`）。
3. **Git 只管文本 + `media-manifest.yaml`**，媒体进 `.gitignore`，由 `backup.py` 同步外部存储。
4. **双 pass 渲染生命周期**：GenSpec 的 `render_passes[]` = draft（API、720p、多 take 抽卡）→ final（UI、1080p、仅中选 take 终渲）。
5. **单写者矩阵 + 事件源账本**：账务/状态变更一律追写 `ledger/events.jsonl`，`summary.yaml` 由事件重算派生。

---

## 目录结构

```
.
├── README.md
├── requirements.txt              # 核心依赖：pyyaml、jsonschema
├── requirements-optional.txt     # 可选依赖：httpx 等 API/VLM 依赖
├── .gitignore                    # Python + 媒体治理 + 凭证安全
├── pyproject.toml                # pytest 配置
├── skills/
│   └── aigc-video-studio/
│       ├── SKILL.md              # SK0 入口/编排技能（占位）
│       ├── references/           # methodology / state-machine / profiles
│       ├── scripts/              # init_project / advance_stage / budget_guard …
│       └── sub-skills/
│           ├── concept-brief/            # SK1
│           ├── screenplay-writer/        # SK2
│           ├── character-foundry/        # SK3
│           ├── storyboard-director/      # SK4
│           ├── prompt-compiler/          # SK5（compile_genspec / prompt_qc）
│           ├── gen-runner/               # SK6（make_taskcards）
│           ├── qc-review/                # SK7
│           ├── audio-post/               # SK8
│           ├── edit-finish/              # SK9
│           ├── publish-kit/              # SK10
│           ├── platform-openart/         # SK11a 平台手册
│           ├── platform-higgsfield/      # SK11b 平台手册
│           ├── platform-jimeng/          # SK11c 即梦手册
│           ├── channel-api/              # SK11d API 通道手册
│           └── _shared/
│               ├── schemas/              # C1–C10 JSON Schema
│               ├── libs/                 # capabilities / camera-preset-map / …
│               └── scripts/              # validate / ingest / ledger / api_adapter
└── tests/                        # pytest 单元测试
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
# 可选（API 直连 / VLM）：
pip install -r requirements-optional.txt
```

### 2. 运行测试

```bash
python -m pytest -q
```

### 3. 初始化一个项目

```bash
python skills/aigc-video-studio/scripts/init_project.py \
    --slug my-first-film --title "我的第一部短片"
```

该命令会建立 `projects/my-first-film/` 文件骨架、写入 `project.yaml`（契约 C1）、`git init`，并生成 `.gitignore` / `.gitattributes` / `media-manifest.yaml`（媒体治理三件套）。

### 脚本通用约定（设计稿 §8）

- 每个脚本提供 CLI：`python <脚本> --project projects/<slug> [args]`，stdout 人类可读，`--json` 输出机读结果。
- 所有契约文件写后必经 `validate.py` 校验，失败不进入下游。
- ingest / 记账 / API 回调脚本幂等（重复执行/回调不重复登记）。

---

## MVP 闭环说明

本阶段（Phase 1）搭建工程地基。MVP 验收范围收敛至**"剧本 → 定角 → 编译 → 生成 → 选片"硬闭环**（音画合成 / 粗剪不计入 MVP 验收门槛）。

闭环咽喉脚本（P0，本阶段全部实现并经 pytest 验证）：

| 脚本 | 职责 |
|---|---|
| `_shared/scripts/validate.py` | C1–C10 schema 校验，所有脚本复用 |
| `scripts/init_project.py` | 建目录骨架 + project.yaml + git init + 媒体治理三件套 |
| `_shared/scripts/ingest.py` | 扫 inbox → 规范命名 → 写 TakeLog（含 pass）→ 记账 → 未匹配入 `_unmatched/`，幂等去重 |
| `_shared/scripts/ledger.py` | 事件源账本：追写 `events.jsonl`，`summary.yaml` 由事件重算，幂等 `event_id` |
| `gen-runner/scripts/make_taskcards.py` | 遍历 GenSpec.render_passes 按 (shot×pass) 出 UI 卡 + API 卡 + 批次清单 |
| `prompt-compiler/scripts/compile_genspec.py` | 四层编译 + 槽位预算分配（≤12）+ reference_label_map + schema 校验 |
| `prompt-compiler/scripts/prompt_qc.py` | 两级 QC：八要素硬阻断 + craft/deai 语义评分占位接口 |
| `_shared/scripts/api_adapter.py` | fal.ai/火山方舟直连（仅读环境变量凭证）+ retry/429退避/fallback；支持 dry_run/mock 模式 |

**双 pass 生命周期**：一个镜头天然含两个生命周期 —— draft pass（API、中低档位、多 take 抽卡）→ final pass（默认 UI、高档位、仅中选 take 终渲）。`make_taskcards` 按 (shot × pass) 实例化：draft → API 卡 `TC-xxx.api.json`，final → UI 卡 `TC-xxx.md`。

---

## 设计稿溯源

唯一事实源：`spec/design-spec-v2.2.md`（功能级设计稿）。本仓库各文件的注释与文档均标注对应的设计稿章节（§）与优化项编号（S-P0-x / S-P1-x / S-P2-x）。
