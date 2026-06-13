#!/usr/bin/env python3
"""隐性成本统计报告（设计稿 §9 路线图 Q-12，在事件源账本之上做投影）。

把账本里"看不见的钱"显式拉出来：除去成片直接生成费（take_cost），
还有重试/失败 take、AI-QC 推理、上传/带宽、人工工时折算等隐性支出。

口径（全部由 ledger 事件派生，可复现、不触网）：
- 直接生成费 direct_gen_cny      ← take_cost 事件累加（summary.by_shot 求和）
- AI-QC 费   ai_qc_cny           ← summary.ai_qc_costs
- 隐性分项   hidden_costs{cat}   ← hidden_cost 事件按 category 聚合
    约定常见 category：retry（重试）/ wasted_take（废 take）/ upload（上传）/
    bandwidth（带宽）/ subscription（订阅）/ learning（学习）/ misc。
- 人工工时   human_minutes       ← human_minutes 事件累加；按 --rate 折算为 CNY。

人工工时折算率为外部输入（不写入可执行契约的"能力数字"，仅本报告口径参数），
缺省 60 cny/h，可经 --hourly-rate 覆盖。

CLI：
  python cost_report.py --project <dir> [--hourly-rate 60] [--md <path>] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import write_yaml, project_path  # noqa: E402
import ledger as _ledger  # noqa: E402

DEFAULT_HOURLY_RATE_CNY = 60.0

# 隐性分项中文名（展示用；未知 category 原样透传）
HIDDEN_LABELS = {
    "retry": "重试开销",
    "wasted_take": "废弃 take",
    "upload": "上传开销",
    "bandwidth": "带宽流量",
    "subscription": "平台订阅",
    "learning": "学习成本",
    "misc": "其他杂项",
}


def build_report(project: str | Path, *,
                 hourly_rate_cny: float = DEFAULT_HOURLY_RATE_CNY) -> dict[str, Any]:
    """由账本 summary 投影出隐性成本报告（确定性，可复现）。"""
    summary = _ledger.get_summary(project)

    direct_gen_cny = round(sum(float(v.get("cny", 0.0))
                               for v in (summary.get("by_shot", {}) or {}).values()), 4)
    ai_qc_cny = round(float(summary.get("ai_qc_costs", 0.0)), 4)
    hidden_costs = {k: round(float(v), 4)
                    for k, v in (summary.get("hidden_costs", {}) or {}).items()}
    hidden_total = round(sum(hidden_costs.values()), 4)

    human_minutes = round(float(summary.get("human_minutes", 0.0)), 4)
    human_cny = round(human_minutes / 60.0 * hourly_rate_cny, 4)

    # 隐性成本合计 = 隐性分项 + AI-QC + 人工工时折算（不含直接生成费）
    hidden_grand_total = round(hidden_total + ai_qc_cny + human_cny, 4)
    total_with_hidden = round(direct_gen_cny + hidden_grand_total, 4)
    hidden_ratio = (round(hidden_grand_total / total_with_hidden, 4)
                    if total_with_hidden else 0.0)

    return {
        "hourly_rate_cny": hourly_rate_cny,
        "direct_gen_cny": direct_gen_cny,
        "ai_qc_cny": ai_qc_cny,
        "hidden_costs": hidden_costs,
        "hidden_costs_subtotal": hidden_total,
        "human_minutes": human_minutes,
        "human_cny": human_cny,
        "hidden_grand_total_cny": hidden_grand_total,
        "total_with_hidden_cny": total_with_hidden,
        "hidden_ratio": hidden_ratio,
    }


def render_md(report: dict[str, Any]) -> str:
    lines = ["# 隐性成本报告（Hidden Cost Report）", "",
             "> Q-12：除成片直接生成费外，把重试/废 take/AI-QC/上传带宽/人工工时等",
             "> 隐性支出显式拉出，避免只算生成费而低估真实成本。", "",
             f"- 人工工时折算率：{report['hourly_rate_cny']} cny/h",
             f"- 直接生成费：**{report['direct_gen_cny']}** cny",
             f"- 隐性成本合计：**{report['hidden_grand_total_cny']}** cny"
             f"（占总成本 {report['hidden_ratio']:.0%}）",
             f"- 含隐性总成本：**{report['total_with_hidden_cny']}** cny", "",
             "## 隐性分项", "",
             "| 项目 | 金额(cny) |", "|---|---|"]
    for cat, amt in sorted(report["hidden_costs"].items(),
                           key=lambda kv: kv[1], reverse=True):
        lines.append(f"| {HIDDEN_LABELS.get(cat, cat)} | {amt} |")
    lines += [f"| AI-QC 推理费 | {report['ai_qc_cny']} |",
              f"| 人工工时折算（{report['human_minutes']} 分钟） | {report['human_cny']} |",
              "", "## 说明", "",
              "- 直接生成费来自 take_cost 事件（按镜累加）。",
              "- 隐性分项来自 hidden_cost 事件的 category 聚合。",
              "- 人工工时折算率为报告口径参数，不写入可执行契约的能力数字。",
              ""]
    return "\n".join(lines) + "\n"


def generate(project: str | Path, *,
             hourly_rate_cny: float = DEFAULT_HOURLY_RATE_CNY,
             out: str | Path | None = None,
             md: str | Path | None = None) -> dict[str, Any]:
    report = build_report(project, hourly_rate_cny=hourly_rate_cny)

    out_path = Path(out) if out else project_path(project, "ledger", "hidden-cost-report.yaml")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(out_path, report)

    md_path = Path(md) if md else project_path(project, "ledger", "hidden-cost-report.md")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_md(report), encoding="utf-8")

    return {"out": str(out_path), "md_out": str(md_path),
            "hidden_grand_total_cny": report["hidden_grand_total_cny"],
            "total_with_hidden_cny": report["total_with_hidden_cny"],
            "hidden_ratio": report["hidden_ratio"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="隐性成本统计报告（Q-12）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--hourly-rate", type=float, default=DEFAULT_HOURLY_RATE_CNY,
                        help="人工工时折算率 cny/h（缺省 60）")
    parser.add_argument("--out", help="机读输出（缺省 ledger/hidden-cost-report.yaml）")
    parser.add_argument("--md", help="人读报告（缺省 ledger/hidden-cost-report.md）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = generate(args.project, hourly_rate_cny=args.hourly_rate,
                      out=args.out, md=args.md)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"隐性成本合计 {result['hidden_grand_total_cny']} cny "
              f"（占总成本 {result['hidden_ratio']:.0%}）-> {result['out']}")
        print(f"  人读报告 -> {result['md_out']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
