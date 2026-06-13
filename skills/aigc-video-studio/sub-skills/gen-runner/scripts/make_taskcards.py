#!/usr/bin/env python3
"""任务卡生成（设计稿 §5 SK6 / §3.2 C7，S-P0-1 按 (shot×pass) 实例化）。

遍历 GenSpec.render_passes[]，对每个 (shot, pass) 出一张任务卡：
  pass=draft 且 channel=api  -> 机读 API 卡 TC-xxx.api.json（C7）
  pass=final 且 channel=ui   -> 人类可读 UI 卡 TC-xxx.md
并产出批次清单 _batch.md。

同一镜头的 draft/final 是两张独立卡，分别记账。

CLI：
  python make_taskcards.py --genspecs <dir|file...> --out <batch_dir> [--start-tc 1] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
from _common import read_yaml, write_json, ensure_validate_importable  # noqa: E402

ensure_validate_importable()
from validate import validate_obj  # noqa: E402


def _tc_id(n: int) -> str:
    return f"TC-{n:03d}"


def build_api_card(genspec: dict[str, Any], rpass: dict[str, Any], tc_id: str) -> dict[str, Any]:
    """draft pass -> API 卡（机读，C7）。"""
    shot = genspec["shot_id"]
    label_map = genspec.get("reference_label_map", {})
    rolling = rpass.get("rolling", {})
    planned = rolling.get("takes_planned", 4)

    references = []
    for sem, placeholder in label_map.items():
        references.append({"slot": placeholder, "file": _slot_file(genspec, sem),
                           "role": "身份/构图"})

    # A.4 尾帧延续：上镜尾帧作为本镜首帧参考，注入参考槽 + 微动量提前量
    cont = genspec.get("continuity")
    if cont and cont.get("last_frame_file"):
        references.append({"slot": "@PrevTail", "file": cont["last_frame_file"],
                           "role": "尾帧延续"})

    card = {
        "task_id": tc_id,
        "shot_id": shot,
        "pass": "draft",
        "channel": "api",
        "platform": "falai",
        "model": genspec.get("model", "seedance-2.0"),
        "endpoint": "fal-ai/bytedance/seedance-2.0/fast/reference-to-video",
        "params": {
            "resolution": rpass.get("resolution", "720p"),
            "aspect": "16:9",
        },
        "reference_label_map": label_map,
        "references": references,
        "prompt_compiled_en": genspec["prompt"].get("compiled_en", ""),
        "prompt_compiled_zh": genspec["prompt"].get("compiled_zh", ""),
        "seed_list": _derive_seeds(tc_id, planned),
        "rolling": {
            "takes_planned": planned,
            "max_takes": rolling.get("max_takes", 8),
            "bayesian": True,
        },
        "retry": {"max_retries": 3, "backoff": "exp", "on_429": "queue_repoll"},
        "fallback": ["volcano:seedance-2.0"],
        "recycle_naming": f"{shot}-tNN_seed<seed>.mp4",
    }
    if cont:
        card["continuity"] = cont
    validate_obj(card, "C7")
    return card


def _slot_file(genspec: dict[str, Any], sem: str) -> str:
    """按语义名找回对应参考文件路径（尽力匹配）。"""
    stem = sem.lstrip("@")
    for s in genspec.get("reference_slots", []):
        if Path(s["file"]).stem == stem or stem in s["file"]:
            return s["file"]
    return genspec.get("reference_slots", [{}])[0].get("file", "") if genspec.get("reference_slots") else ""


def _derive_seeds(tc_id: str, n: int) -> list[int]:
    import hashlib
    base = int(hashlib.sha256(tc_id.encode()).hexdigest()[:8], 16) % 100000
    return [base + i for i in range(n)]


def build_ui_card_md(genspec: dict[str, Any], rpass: dict[str, Any], tc_id: str) -> str:
    """final pass -> UI 卡（人类可读 markdown）。"""
    shot = genspec["shot_id"]
    preset = rpass.get("camera_preset", "（按 camera-preset-map 选择）")
    res = rpass.get("resolution", "1080p")
    platform = rpass.get("platform", "higgsfield")
    entry = rpass.get("entry", "cinema_studio")
    compiled = genspec["prompt"].get("compiled_zh", "")

    refs_rows = ""
    for i, s in enumerate(genspec.get("reference_slots", []), 1):
        refs_rows += f"| {i} | {s['file']} | {s['slot']} | {s.get('role', '')} |\n"

    cont = genspec.get("continuity")
    cont_block = ""
    if cont:
        lead = cont.get("micro_motion_lead_s")
        cont_block = (
            f"\n## 0. 尾帧延续（上镜衔接）\n"
            f"- 上一镜：{cont.get('prev_shot', '（未指定）')}\n"
            f"- 尾帧参考：`{cont.get('last_frame_file', '（无）')}`（作本镜起始构图基准）\n"
            f"- 微动量提前量：{lead if lead is not None else 0}s（衔接处预留运动惯性，避免硬接顿挫）\n")

    return f"""# {tc_id} · {shot} 终渲（{platform} / {entry}）  【通道: UI · pass=final】
**平台**: {platform} → {entry}    **模型**: {genspec.get('model', 'seedance-2.0')}
**依赖**: draft 已选定 take（source_take={rpass.get('source_take', 'selected')}）
{cont_block}
## 1. 上传（按 identity_strategy.ref_order 顺序）
| # | 本地文件 | 平台槽位 | 用途 |
|---|---|---|---|
{refs_rows}
## 2. 提示词（整段复制粘贴，中文）
> {compiled}

## 3. 参数设置
分辨率 {res} · 画幅 16:9 · 运镜预设 {preset}
（一致性靠提示词锁定 + 上传顺序，无数值权重可调）

## 4. 执行
以 draft 中选 take 为起点终渲 1–2 次 → 比稿选定

## 5. 回收
下载文件按 `{shot}-tNN[_seed<seed>].mp4` 命名投入 inbox/（seed 段 UI 卡可选），完成后告知 "{tc_id} done"

## 6. 验收自查
{_acceptance_md(genspec)}
"""


def _acceptance_md(genspec: dict[str, Any]) -> str:
    items = genspec.get("acceptance") or ["角色无漂移", "运镜方向正确", "无 AI 塑料感"]
    return "\n".join(f"- [ ] {a}" for a in items)


def make_taskcards(genspecs: list[dict[str, Any]], out_dir: str | Path,
                   start_tc: int = 1) -> dict[str, Any]:
    """对一批 GenSpec 按 (shot×pass) 出卡 + 批次清单。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    tc_n = start_tc
    manifest_rows: list[dict[str, Any]] = []

    for genspec in genspecs:
        for rpass in genspec.get("render_passes", []):
            tc_id = _tc_id(tc_n)
            tc_n += 1
            if rpass["pass"] == "draft" and rpass["channel"] == "api":
                card = build_api_card(genspec, rpass, tc_id)
                fname = f"{tc_id}.api.json"
                write_json(out / fname, card)
                manifest_rows.append({"tc": tc_id, "shot": genspec["shot_id"],
                                      "pass": "draft", "channel": "api", "file": fname})
            elif rpass["pass"] == "final" and rpass["channel"] == "ui":
                md = build_ui_card_md(genspec, rpass, tc_id)
                fname = f"{tc_id}.md"
                (out / fname).write_text(md, encoding="utf-8")
                manifest_rows.append({"tc": tc_id, "shot": genspec["shot_id"],
                                      "pass": "final", "channel": "ui", "file": fname})
            else:
                # 其他组合（如 final/api 经 verified_at 确认）：出 API 卡
                card = build_api_card(genspec, rpass, tc_id)
                card["pass"] = rpass["pass"]
                validate_obj(card, "C7")
                fname = f"{tc_id}.api.json"
                write_json(out / fname, card)
                manifest_rows.append({"tc": tc_id, "shot": genspec["shot_id"],
                                      "pass": rpass["pass"], "channel": rpass["channel"],
                                      "file": fname})

    _write_batch_manifest(out, manifest_rows)
    return {"out_dir": str(out), "cards": manifest_rows, "count": len(manifest_rows)}


def _write_batch_manifest(out: Path, rows: list[dict[str, Any]]) -> None:
    lines = ["# 批次清单（_batch.md）", "",
             "| TC | 镜头 | pass | 通道 | 文件 |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['tc']} | {r['shot']} | {r['pass']} | {r['channel']} | {r['file']} |")
    lines += ["", "## 执行顺序", "1. 先执行 API draft 卡（抽卡）→ 选片",
              "2. 再执行 UI final 卡（终渲中选 take）"]
    (out / "_batch.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_genspecs(paths: list[str]) -> list[dict[str, Any]]:
    specs = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            for f in sorted(path.glob("*.yaml")):
                specs.append(read_yaml(f))
        else:
            specs.append(read_yaml(path))
    return specs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="任务卡生成（SK6）")
    parser.add_argument("--genspecs", nargs="+", required=True,
                        help="GenSpec 文件或目录（可多个）")
    parser.add_argument("--out", required=True, help="批次输出目录 batch-NN/")
    parser.add_argument("--start-tc", type=int, default=1)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    specs = _load_genspecs(args.genspecs)
    result = make_taskcards(specs, args.out, start_tc=args.start_tc)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"生成 {result['count']} 张任务卡 -> {result['out_dir']}")
        for c in result["cards"]:
            print(f"  {c['tc']} {c['shot']} [{c['pass']}/{c['channel']}] {c['file']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
