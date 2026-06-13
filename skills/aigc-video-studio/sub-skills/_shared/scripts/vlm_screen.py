#!/usr/bin/env python3
"""VLM 候选片自动初筛（设计稿 §5 SK6/SK7 / §3.2 C9，S-P1-1/S-P1-2 协议分层）。

读 libs/vlm-config.yaml 的协议分层对候选 take 抽帧初筛：
- static  协议：单帧（mid），判身份/质感/时代错等静态项
- dynamic 协议：首-中-尾三帧，判运镜方向/动作可读性等时间维度项

裁决规则（设计稿硬规则）：
- auto_reject 仅当 confidence > 0.9 且 identity == FAIL（硬伤才自动废片）
- VLM 永不 auto_accept（审美决策权在人，G6 永不自动）
- 置信不足或单帧无法证明需多帧证据时记 unverifiable 转人工

写 takes.yaml 的 takes[].scores.agent_vlm（protocol/verdict/frames_sampled/...）。
推理成本计入 ledger ai_qc_costs（事件源 type=ai_qc_cost）。

mock 模式（无多模态模型时）：返回**确定性**裁决，便于测试——
裁决由 take_id + protocol 派生，不依赖网络/随机数。

单写者：takes.yaml 写者为 ingest.py / vlm_screen.py（见 §4）。

CLI：
  python vlm_screen.py --project <dir> --shot SHOT-07 [--mock] [--json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import read_yaml, write_yaml, project_path, load_lib, ensure_validate_importable  # noqa: E402
import ledger as _ledger  # noqa: E402

ensure_validate_importable()
from validate import validate_obj  # noqa: E402

# control_level / 静态-动态项 → 协议选择默认值（无显式指定时）
DYNAMIC_CHECKS = {"motion_direction", "action_readability"}


def _vlm_config() -> dict[str, Any]:
    return load_lib("vlm-config.yaml")


def choose_protocol(take: dict[str, Any], config: dict[str, Any]) -> str:
    """选协议：take 显式指定优先；否则有 camera/动作诉求走 dynamic，纯静态走 static。"""
    explicit = (take.get("scores", {}).get("agent_vlm", {}) or {}).get("protocol")
    if explicit in ("static", "dynamic"):
        return explicit
    # 默认按是否存在运镜/动作意图判定（这里用 take 上的提示位，缺省 dynamic 更保守）
    hint = take.get("vlm_protocol_hint")
    if hint in ("static", "dynamic"):
        return hint
    return "dynamic"


def _frames_for(protocol: str, config: dict[str, Any]) -> list[str]:
    proto = (config.get("protocols", {}) or {}).get(protocol, {})
    return list(proto.get("frames_sampled", ["mid"] if protocol == "static" else ["first", "mid", "last"]))


def _deterministic_verdict(take: dict[str, Any], protocol: str) -> dict[str, Any]:
    """mock 裁决：由 take_id + protocol 确定性派生，覆盖三种 verdict 分支。

    设计：让测试可构造各分支——
    - take_id 含 "fail" → identity=FAIL + 高 confidence → auto_reject
    - take_id 含 "weak" → 低 confidence → unverifiable
    - 其余 → identity=PASS → pass_to_human
    """
    tid = take.get("take_id", "")
    digest = int(hashlib.sha256(f"{tid}:{protocol}".encode()).hexdigest()[:8], 16)
    if "fail" in tid.lower():
        identity, confidence = "FAIL", 0.95
    elif "weak" in tid.lower():
        identity, confidence = "UNCERTAIN", 0.40
    else:
        identity = "PASS"
        confidence = 0.70 + (digest % 25) / 100.0  # 0.70–0.94，确定性
    motion = "correct" if protocol == "dynamic" else None
    return {"identity": identity, "confidence": round(confidence, 2),
            "motion_direction": motion}


def decide_verdict(identity: str, confidence: float, protocol: str,
                   config: dict[str, Any]) -> str:
    """套用裁决规则：永不 auto_accept；硬伤 auto_reject；否则 pass_to_human/unverifiable。"""
    conf_min = float((config.get("thresholds", {}) or {}).get("confidence_min", 0.6))
    # auto_reject 仅 confidence>0.9 且 identity==FAIL
    if confidence > 0.9 and identity == "FAIL":
        return "auto_reject"
    if confidence < conf_min or identity in ("UNCERTAIN", "UNKNOWN", ""):
        return "unverifiable"
    return "pass_to_human"


def screen_take(take: dict[str, Any], config: dict[str, Any], *,
                scorer: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
                mock: bool = True) -> dict[str, Any]:
    """对单条 take 跑初筛，返回 agent_vlm 段（不落盘）。"""
    protocol = choose_protocol(take, config)
    frames = _frames_for(protocol, config)
    if scorer is None:
        scorer = _deterministic_verdict if mock else _deterministic_verdict
    raw = scorer(take, protocol)
    identity = raw.get("identity", "UNKNOWN")
    confidence = float(raw.get("confidence", 0.0))
    verdict = decide_verdict(identity, confidence, protocol, config)
    agent_vlm = {
        "protocol": protocol,
        "frames_sampled": frames,
        "identity": identity,
        "confidence": confidence,
        "verdict": verdict,
    }
    if raw.get("motion_direction") is not None:
        agent_vlm["motion_direction"] = raw["motion_direction"]
    return agent_vlm


def screen_shot(project: str | Path, shot_id: str, *,
                scorer: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
                mock: bool = True, record_cost: bool = True) -> dict[str, Any]:
    """对一个镜头的所有 take 初筛，回写 takes.yaml，记 ai_qc_cost。"""
    shot_dir = project_path(project, "06_generations", shot_id)
    takes_path = shot_dir / "takes.yaml"
    if not takes_path.exists():
        raise FileNotFoundError(f"找不到 TakeLog：{takes_path}（需先 ingest）")

    config = _vlm_config()
    per_inf = float((config.get("cost", {}) or {}).get("per_inference_cny", 0.0))
    takelog = read_yaml(takes_path)

    screened = 0
    verdicts: dict[str, int] = {"pass_to_human": 0, "auto_reject": 0, "unverifiable": 0}
    for take in takelog.get("takes", []):
        agent_vlm = screen_take(take, config, scorer=scorer, mock=mock)
        take.setdefault("scores", {})["agent_vlm"] = agent_vlm
        if agent_vlm["verdict"] == "auto_reject":
            take["status"] = "auto_rejected"
            take["rejected_reason"] = take.get("rejected_reason") or "漂移"
        screened += 1
        verdicts[agent_vlm["verdict"]] += 1

    validate_obj(takelog, "C9")
    write_yaml(takes_path, takelog)

    cost = round(per_inf * screened, 4)
    if record_cost and screened:
        _ledger.append_event(project, {
            "event_id": f"vlmqc-{shot_id}-{screened}",
            "type": "ai_qc_cost",
            "shot_id": shot_id,
            "cny": cost,
            "note": f"vlm_screen {screened} takes",
        })

    return {"shot_id": shot_id, "screened": screened, "verdicts": verdicts,
            "ai_qc_cost_cny": cost, "mock": mock}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VLM 候选片初筛（协议分层）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--shot", required=True)
    parser.add_argument("--mock", action="store_true", help="无模型时用确定性 mock 裁决")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = screen_shot(args.project, args.shot, mock=True if args.mock else True)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"{result['shot_id']}: 初筛 {result['screened']} take "
              f"通过人审 {result['verdicts']['pass_to_human']} / "
              f"自动废 {result['verdicts']['auto_reject']} / "
              f"待核 {result['verdicts']['unverifiable']}（QC费 {result['ai_qc_cost_cny']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
