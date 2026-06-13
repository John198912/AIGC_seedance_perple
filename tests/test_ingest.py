"""回收单测：命名解析、幂等、_unmatched 旁路、TakeLog 写出。"""
from __future__ import annotations

import ingest
import ledger


def test_parse_name_variants():
    assert ingest.parse_name("shot07-t03")["shot_id"] == "SHOT-07"
    assert ingest.parse_name("SHOT-07-t3_seed123") == {
        "shot_id": "SHOT-07", "take_num": "t03", "seed": 123}
    assert ingest.parse_name("not-a-take") is None


def _seed_inbox(project_dir, names):
    inbox = project_dir / "06_generations" / "SHOT-07" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    for name, content in names.items():
        (inbox / name).write_bytes(content.encode())
    return inbox


def test_ingest_renames_and_writes_takelog(project_dir):
    _seed_inbox(project_dir, {"shot07-t01_seed100.mp4": "A", "shot07-t02_seed101.mp4": "B"})
    res = ingest.ingest_shot(project_dir, "SHOT-07", cost_cny=12.0)
    assert len(res["ingested"]) == 2
    from _common import read_yaml
    tl = read_yaml(project_dir / "06_generations" / "SHOT-07" / "takes.yaml")
    assert len(tl["takes"]) == 2
    assert all(t["pass"] == "draft" for t in tl["takes"])


def test_ingest_idempotent(project_dir):
    _seed_inbox(project_dir, {"shot07-t01_seed100.mp4": "SAME"})
    ingest.ingest_shot(project_dir, "SHOT-07", cost_cny=12.0)
    # 同内容再次投放 → 跳过，账本不重复
    _seed_inbox(project_dir, {"shot07-t01_seed100.mp4": "SAME"})
    res2 = ingest.ingest_shot(project_dir, "SHOT-07", cost_cny=12.0)
    assert res2["skipped"] == ["shot07-t01_seed100.mp4"]
    s = ledger.get_summary(project_dir)
    assert s["event_count"] == 1


def test_unmatched_goes_to_sidecar(project_dir):
    _seed_inbox(project_dir, {"random-file.mp4": "X"})
    res = ingest.ingest_shot(project_dir, "SHOT-07")
    assert res["unmatched"] == ["random-file.mp4"]
    unm = project_dir / "06_generations" / "SHOT-07" / "_unmatched" / "random-file.mp4"
    assert unm.exists()
