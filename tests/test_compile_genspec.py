"""GenSpec 编译单测：四层、render_passes、槽位裁剪、reference_label_map。"""
from __future__ import annotations

import compile_genspec


def test_compile_basic(shotlist_shot):
    g = compile_genspec.compile_genspec(shotlist_shot)
    assert g["shot_id"] == "SHOT-07"
    # 四层齐备
    for k in ("layer0_deai", "layer1_setting", "layer2_style", "layer3_shot"):
        assert g["prompt"][k]
    # guided → 双 pass
    passes = [p["pass"] for p in g["render_passes"]]
    assert passes == ["draft", "final"]


def test_render_pass_by_control_level(shotlist_shot):
    free = dict(shotlist_shot, control_level="free")
    locked = dict(shotlist_shot, control_level="locked")
    assert [p["pass"] for p in compile_genspec.compile_genspec(free)["render_passes"]] == ["draft"]
    assert [p["pass"] for p in compile_genspec.compile_genspec(locked)["render_passes"]] == ["final"]


def test_label_map_maps_identity_to_character(shotlist_shot):
    g = compile_genspec.compile_genspec(shotlist_shot)
    lm = g["reference_label_map"]
    # 角色身份槽位映射到角色语义名 → @ImageN
    assert "@robo-cowboy" in lm
    assert lm["@robo-cowboy"].startswith("@Image")


def test_slot_budget_trims_overflow():
    # 构造超过 image 上限(9) 的候选槽位，验证裁剪与 dropped 记录
    extra = [{"file": f"x/extra{i}.png", "slot": "image", "role": "style"}
             for i in range(15)]
    shot = {
        "shot_id": "SHOT-99", "scene": "测试", "characters": ["c1"],
        "shot_size": "中景", "composition": "三分", "camera_move": "推",
        "action_logic": "走", "audio_cue": "风声",
        "first_frame": "f.png", "control_level": "guided",
        "extra_reference_slots": extra,
    }
    g = compile_genspec.compile_genspec(shot)
    image_kept = [s for s in g["reference_slots"]
                  if s["slot"] in ("image", "start_frame", "end_frame")]
    assert len(image_kept) <= 9
    assert len(g["slots_dropped"]) > 0


def test_allocate_priority_keeps_identity_first():
    cands = [
        {"file": "s.png", "slot": "image", "role": "style"},
        {"file": "id.png", "slot": "image", "role": "identity"},
    ]
    kept, _ = compile_genspec.allocate_slots(cands)
    assert kept[0]["role"] == "identity"
