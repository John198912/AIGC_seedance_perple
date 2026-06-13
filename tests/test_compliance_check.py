"""compliance_check 单测：语义替换、compliance_applied 记录、残留扫描。"""
from __future__ import annotations

import compliance_check


def _genspec(text):
    return {
        "shot_id": "SHOT-07", "version": 1, "model": "seedance-2.0",
        "prompt": {
            "layer0_deai": "胶片颗粒", "layer1_setting": text,
            "layer2_style": "废土", "layer3_shot": "推轨",
        },
        "render_passes": [{"pass": "draft", "channel": "api", "resolution": "720p"}],
        "prompt_qc": {"structural_blockers": []},
    }


def test_replacement_applied():
    g = _genspec("一只丧尸在开枪")
    res = compliance_check.check_genspec(g)
    # 敏感词被替换
    assert "丧尸" not in res["genspec"]["prompt"]["layer1_setting"]
    assert "开枪" not in res["genspec"]["prompt"]["layer1_setting"]
    assert "丧尸" in res["compliance_applied"]
    assert "开枪" in res["compliance_applied"]
    # 替换后无残留
    assert res["ok"] is True
    assert res["residual"] == []


def test_forbidden_residual_detected():
    g = _genspec("画面里有真人明星出镜")
    res = compliance_check.check_genspec(g)
    # forbidden 项无替换 → 残留报出
    assert res["ok"] is False
    assert any("真人明星" in r or "真人" in r for r in res["residual"])


def test_clean_prompt_passes():
    g = _genspec("锈牛仔在沙尘中前行")
    res = compliance_check.check_genspec(g)
    assert res["ok"] is True
    assert res["compliance_applied"] == []


def test_apply_replacements_unit():
    repls = [{"sensitive": "血液", "replace_with": "深色液体飞溅"}]
    out, applied = compliance_check.apply_replacements("地上有血液", repls)
    assert out == "地上有深色液体飞溅"
    assert applied == ["血液"]
