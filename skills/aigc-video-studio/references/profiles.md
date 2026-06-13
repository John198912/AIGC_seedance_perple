# Profile 档位配置（四档）

> SK0 据 `project.yaml.profile` 选择默认策略。详见设计稿 §7.3。

| 配置项 | premium 精品单片 | series 剧集量产 | rapid 快速验证 | exploration 探索 |
|---|---|---|---|---|
| 默认 variant | i2v_omni 全能参考 | multigrid + 资产复用 | t2v / OpenArt Story | guided + 多变体并行 |
| 快档 takes/镜 | 4–6（贝叶斯停止） | 3–4 | 1–2 | 2–3 变体 ×2 |
| Gate 策略 | 全开 + G5 抽查（prompt_qc 通过可减） | G3/G6 强制，余自动 | 仅 G1/G6 | G1/G2/G6 + 频繁回流 |
| 首帧策略（按 control_level） | locked 做首帧、guided 选做、free 不做 | 关键镜做 | 不做 | guided 为主 |
| 终渲档 | 1080p（原生） | 1080p | 720p | 720p |
| render_passes | draft:api/720p + final:ui/1080p | draft:api 优先（量产） | draft:api/Story（可只一 pass） | draft:api（便宜快迭代） |
| 平台组合 | dual | dual（角色资产跨集复用） | openart_only / jimeng_only | api_first |

## premium（精品单片）

最高保真。draft 走 API 抽卡（贝叶斯停止），final 走 UI Cinema Studio 1080p 终渲。
按 control_level 分级首帧策略，取代旧版"每镜必做首帧"。

## series（剧集量产）

S2 起每集循环 S2→S8；`03_characters/`、`03_style/` 为全剧共享资产；
CharacterCard 增 `variants[]`（不同集/状态变体）；每集结尾跑跨集**漂移检查**
（VLM 比对角色一致）；建立**复用镜头库**（空镜/转场可跨集复用）；批次支持并行调度；
每集独立 shotlist 与账本，汇总到剧级 dashboard。

## rapid（快速验证）

最低成本走查。只保 G1/G6 两道 Gate，不做首帧，720p 终渲，draft 可只一 pass。

## exploration（探索，动态编剧法正式化）

用于剧本/分镜未定型时的快速试错：多提示词变体并行（接 control_level=guided 探索镜头）、
频繁回流 S2/S4、用 `metrics.py` 数据校准经验。把"动态编剧法"从理念落为可配置档位。
