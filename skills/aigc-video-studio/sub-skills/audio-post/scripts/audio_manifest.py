#!/usr/bin/env python3
"""音频策略与执行（设计稿 §5 SK8，Phase 4 可用实现）。

读「选定 takes + screenplay 情绪曲线 + GenSpec.audio_mode」，产出：
- 07_audio/audio-plan.md：音频策略文档（决策树：native 原生同期音利用 /
  post_mix BGM 走 Suno + 配音决策），含逐段策略与情绪节拍对齐说明。
- 07_audio/audio-manifest.yaml：素材清单 + 时间轴对齐表（start_s/end_s）+
  voice_bind 映射（角色卡有 voice_ref 时）+ ambience_group 同场景环境音桥接 +
  版权来源登记（强制）。

设计纪律：
- 原生音优先：audio_mode=native 时优先 Seedance 原生同期音/环境音，audio_cue 分段精细化。
- 版权登记强制：每条音频素材登记来源（native/suno/elevenlabs/library），无来源记 unregistered 告警。
- ambience_group 相同的相邻镜头标“环境音桥接”，根治跨镜音频割裂。
- voice_bind：CharacterCard.voice_ref 存在则角色配音按声纹绑定（跨镜一致），否则逐场指定。
- 确定性：时间轴/策略由输入派生，可复现，不触网。

CLI：
  python audio_manifest.py --project <dir> [--out 07_audio/audio-manifest.yaml]
                           [--plan 07_audio/audio-plan.md] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
from _common import read_yaml, write_yaml, project_path  # noqa: E402


def _voice_binds(project: str | Path) -> dict[str, str]:
    """扫角色卡 voice_ref，产出 角色id → 声纹资产 映射（跨镜一致）。"""
    chars_dir = project_path(project, "03_characters")
    binds: dict[str, str] = {}
    if chars_dir.exists():
        for card in sorted(chars_dir.glob("*/card.yaml")):
            data = read_yaml(card)
            if data.get("voice_ref"):
                binds[data["id"]] = data["voice_ref"]
    return binds


def _emotion_by_scene(project: str | Path) -> dict[str, float]:
    """从剧本情绪曲线取 scene_id → emotion_value（供 BGM 情绪节拍对齐）。"""
    sp_path = project_path(project, "02_screenplay", "screenplay.yaml")
    if not sp_path.exists():
        return {}
    sp = read_yaml(sp_path)
    out: dict[str, float] = {}
    for pt in sp.get("emotion_curve", []) or []:
        if pt.get("scene_id") is not None:
            out[pt["scene_id"]] = float(pt.get("value", 0))
    # 退回 scenes[].emotion_value
    if not out:
        for sc in sp.get("scenes", []) or []:
            if sc.get("scene_id") is not None:
                out[sc["scene_id"]] = float(sc.get("emotion_value", 0))
    return out


def _audio_mode(project: str | Path, shot_id: str, default: str = "native") -> str:
    """读该镜 GenSpec.audio_mode（缺省 native）。"""
    gs_path = project_path(project, "05_prompts", "genspecs", f"{shot_id}.yaml")
    if gs_path.exists():
        return read_yaml(gs_path).get("audio_mode", default)
    return default


def _selected_take(project: str | Path, shot_id: str) -> str | None:
    tp = project_path(project, "06_generations", shot_id, "takes.yaml")
    if tp.exists():
        return read_yaml(tp).get("selected_take")
    return None


def _strategy_for_mode(mode: str, has_voice: bool) -> dict[str, Any]:
    """音频决策树：按 audio_mode 给出该段的音源与工具路由。"""
    if mode == "native":
        return {
            "source": "native",
            "tool": "seedance_native",
            "note": "利用 Seedance 原生同期音/环境音，audio_cue 分段精细化（利用双声道）",
        }
    if mode == "post_mix":
        return {
            "source": "suno_bgm",
            "tool": "suno",
            "note": "BGM 走 Suno（提示词模板：BPM/调性/段落对齐情绪节拍）",
        }
    if mode == "voice_bind":
        return {
            "source": "voice_bind" if has_voice else "elevenlabs",
            "tool": "elevenlabs+heygen" if not has_voice else "voice_ref",
            "note": "对白优先 Seedance 原生口型，失效再走 ElevenLabs + HeyGen；"
                    "有 voice_ref 则按角色声纹绑定",
        }
    return {"source": "native", "tool": "seedance_native", "note": "默认原生音"}


def build_manifest(project: str | Path) -> dict[str, Any]:
    shotlist = read_yaml(project_path(project, "04_storyboard", "shotlist.yaml"))
    shots = sorted(shotlist.get("shots", []), key=lambda s: s.get("order", 0))
    voice_binds = _voice_binds(project)

    timeline: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    cursor = 0.0
    prev_group = None
    for shot in shots:
        dur = float(shot.get("duration_s", 0))
        sid = shot["shot_id"]
        mode = _audio_mode(project, sid)
        chars = shot.get("characters", []) or []
        has_voice = any(c in voice_binds for c in chars)
        strat = _strategy_for_mode(mode, has_voice)
        bridge = (shot.get("ambience_group") is not None
                  and shot.get("ambience_group") == prev_group)

        entry = {
            "shot_id": sid,
            "start_s": round(cursor, 2),
            "end_s": round(cursor + dur, 2),
            "audio_cue": shot.get("audio_cue", ""),
            "audio_mode": mode,
            "ambience_group": shot.get("ambience_group"),
            "bridge_prev": bridge,
            "source": strat["source"],
            "tool": strat["tool"],
            "selected_take": _selected_take(project, sid),
        }
        timeline.append(entry)

        # 版权来源登记（强制）：每条素材登记来源
        assets.append({
            "shot_id": sid,
            "source": strat["source"],
            "tool": strat["tool"],
            "license": "native_inherited" if strat["source"] == "native" else "to_register",
            "registered": strat["source"] == "native",  # 原生音随片继承授权
        })
        cursor += dur
        prev_group = shot.get("ambience_group")

    unregistered = [a["shot_id"] for a in assets if not a["registered"]]
    ambience_groups = _build_ambience_groups(timeline)
    return {
        "total_duration_s": round(cursor, 2),
        "timeline": timeline,
        "assets": assets,
        "voice_bind": voice_binds,
        "ambience_groups": ambience_groups,
        "copyright_warnings": unregistered,
    }


def _build_ambience_groups(timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同 ambience_group 的镜头共享一条环境音轨（A.3，根治跨镜音频割裂）。

    为每个含 ≥2 镜的组生成共享环境音资产：覆盖区间 = 组内最早入点→最晚出点，
    成员镜头从该共享床混入，供 EDL「环境音桥接」轨道引用。
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for e in timeline:
        g = e.get("ambience_group")
        if g:
            groups.setdefault(g, []).append(e)
    out: list[dict[str, Any]] = []
    for g, members in groups.items():
        if len(members) < 2:
            continue  # 单镜无需跨镜共享床
        out.append({
            "ambience_group": g,
            "shots": [m["shot_id"] for m in members],
            "bed_start_s": min(m["start_s"] for m in members),
            "bed_end_s": max(m["end_s"] for m in members),
            "shared_asset": f"ambience/{g}.wav",
            "note": "组内镜头共享同一环境音床，EDL 加“环境音桥接”轨道交叉淡入淡出",
        })
    return out


def render_plan_md(project: str | Path, manifest: dict[str, Any]) -> str:
    """渲染 audio-plan.md（音频策略文档）。"""
    emo = _emotion_by_scene(project)
    lines = ["# 音频策略（audio-plan）", "",
             "> SK8 音画合成。决策树：native 原生同期音优先 → post_mix BGM(Suno)/配音补充。",
             "> 注：音画合成不计入 MVP 验收门槛（设计稿 §9），G7 默认自动。", "",
             f"总时长：{manifest['total_duration_s']}s", "",
             "## 逐镜音频策略",
             "",
             "| 镜头 | 入点-出点 | audio_mode | 音源 | 工具 | 环境音桥接 |",
             "|---|---|---|---|---|---|"]
    for e in manifest["timeline"]:
        bridge = "是（接前镜）" if e["bridge_prev"] else "—"
        lines.append(f"| {e['shot_id']} | {e['start_s']}-{e['end_s']}s "
                     f"| {e['audio_mode']} | {e['source']} | {e['tool']} | {bridge} |")

    lines += ["", "## 决策树说明",
              "- **native**：利用 Seedance 原生同期音/环境音，`audio_cue` 分段精细化（双声道）。",
              "- **post_mix**：BGM 走 Suno，提示词模板按 BPM/调性/段落对齐情绪节拍。",
              "- **voice_bind**：对白优先原生口型，失效走 ElevenLabs + HeyGen；"
              "有 `voice_ref` 按角色声纹绑定（跨镜一致）。", ""]

    if manifest["voice_bind"]:
        lines += ["## 声纹绑定（voice_bind）", ""]
        for cid, ref in manifest["voice_bind"].items():
            lines.append(f"- `{cid}` → `{ref}`（跨镜一致）")
        lines.append("")

    # ambience 桥接 + 共享环境音床
    bridges = [e["shot_id"] for e in manifest["timeline"] if e["bridge_prev"]]
    lines += ["## 环境音桥接（ambience_group）", ""]
    if bridges:
        lines.append(f"以下镜头与前镜同 `ambience_group`，EDL 加“环境音桥接”轨道，"
                     f"根治跨镜音频割裂：{', '.join(bridges)}")
    else:
        lines.append("无相邻同场景镜头，无需桥接。")
    lines.append("")
    groups = manifest.get("ambience_groups", [])
    if groups:
        lines += ["**共享环境音床**（组内镜头共用一条环境音轨）：", "",
                  "| 场景组 | 覆盖区间 | 共享资产 | 成员镜头 |", "|---|---|---|---|"]
        for g in groups:
            lines.append(f"| {g['ambience_group']} | {g['bed_start_s']}-{g['bed_end_s']}s "
                         f"| `{g['shared_asset']}` | {', '.join(g['shots'])} |")
        lines.append("")

    # 情绪节拍对齐（若有剧本情绪曲线）
    if emo:
        lines += ["## 情绪节拍对齐", "",
                  "BGM/音效强度跟随剧本情绪曲线（0–10）：", ""]
        for sid, val in emo.items():
            lines.append(f"- `{sid}`：情绪值 {val}")
        lines.append("")

    # 版权登记（强制）
    lines += ["## 版权来源登记（强制）", "",
              "| 镜头 | 音源 | 授权状态 |", "|---|---|---|"]
    for a in manifest["assets"]:
        status = "已继承（随片）" if a["registered"] else "待登记 ⚠"
        lines.append(f"| {a['shot_id']} | {a['source']} | {status} |")
    if manifest["copyright_warnings"]:
        lines += ["", f"> ⚠ 以下镜头音源需补登版权来源：{', '.join(manifest['copyright_warnings'])}"]
    lines.append("")
    return "\n".join(lines) + "\n"


def generate(project: str | Path, *, out: str | Path | None = None,
             plan: str | Path | None = None) -> dict[str, Any]:
    manifest = build_manifest(project)
    out_path = Path(out) if out else project_path(project, "07_audio", "audio-manifest.yaml")
    write_yaml(out_path, manifest)

    plan_path = Path(plan) if plan else project_path(project, "07_audio", "audio-plan.md")
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(render_plan_md(project, manifest), encoding="utf-8")

    return {
        "manifest_out": str(out_path),
        "plan_out": str(plan_path),
        "segment_count": len(manifest["timeline"]),
        "total_duration_s": manifest["total_duration_s"],
        "voice_bind": manifest["voice_bind"],
        "ambience_groups": manifest["ambience_groups"],
        "copyright_warnings": manifest["copyright_warnings"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="音频策略 + 清单 + 时间轴 + voice_bind（SK8）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--out", help="清单输出路径（缺省 07_audio/audio-manifest.yaml）")
    parser.add_argument("--plan", help="策略文档路径（缺省 07_audio/audio-plan.md）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = generate(args.project, out=args.out, plan=args.plan)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"音频策略 {result['segment_count']} 段 / {result['total_duration_s']}s")
        print(f"  策略文档 -> {result['plan_out']}")
        if result["voice_bind"]:
            print(f"  声纹绑定：{result['voice_bind']}")
        if result["copyright_warnings"]:
            print(f"  ⚠ 待登记版权：{result['copyright_warnings']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
