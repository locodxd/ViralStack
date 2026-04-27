import asyncio
from pathlib import Path

import pytest

from config.settings import settings
from config import settings as settings_module
from pipeline import compositor, platform_publishers, script_gen, subtitles, tiktok_publish, video_gen


class _Word:
    def __init__(self, word: str, start: float, end: float):
        self.word = word
        self.start = start
        self.end = end


def test_align_visuals_trims_to_55s_cadence():
    visuals = [f"scene {i}" for i in range(19)]
    aligned = script_gen._align_visuals_to_script(
        visuals,
        "Sentence one. Sentence two.",
        60,
        "terror",
    )

    assert len(aligned) == 11
    assert aligned[0] == "scene 0"
    assert aligned[-1] == "scene 18"


def test_normalize_image_sequence_matches_target_duration():
    image_paths = [f"scene_{i}.png" for i in range(19)]
    normalized = compositor._normalize_image_sequence(image_paths, 59.6)

    assert len(normalized) == 11
    assert normalized[0] == "scene_0.png"
    assert normalized[-1] == "scene_18.png"


def test_subtitle_groups_merge_tiny_tail():
    words = [
        _Word("Encontre", 0.0, 0.4),
        _Word("algo", 0.4, 0.8),
        _Word("raro", 0.8, 1.2),
        _Word("anoche", 1.2, 1.7),
        _Word("afuera", 1.7, 2.0),
    ]

    groups = subtitles._build_word_groups(words)

    assert len(groups) == 1
    assert " ".join(w.word for w in groups[0]) == "Encontre algo raro anoche afuera"


def test_subtitle_formatter_balances_large_caption_into_two_lines():
    words = [
        _Word("Esto", 0.0, 0.3),
        _Word("no", 0.3, 0.6),
        _Word("deberia", 0.6, 0.9),
        _Word("estar", 0.9, 1.2),
        _Word("aqui", 1.2, 1.5),
    ]

    assert subtitles._format_cue_text(words) == "Esto no deberia\nestar aqui"


def test_tiktok_failed_list_is_not_treated_as_success():
    with pytest.raises(RuntimeError):
        tiktok_publish._extract_video_url([{"path": "bad.mp4"}], "terror")

    assert tiktok_publish._extract_video_url([], "terror") == "https://tiktok.com/@terror"


def test_hook_is_forced_to_the_start_of_script():
    hook = "Encontre una voz respirando dentro del baby monitor."
    script = "La app me aviso movimiento a las 3:14. Revise la cuna y estaba vacia."

    merged = script_gen._ensure_hook_leads_script(hook, script)

    assert merged.startswith(hook)


def test_generic_hook_is_rejected_for_terror():
    reasons = script_gen._hook_validation_reasons(
        "Alguna vez sentiste miedo de noche?",
        "Alguna vez sentiste miedo de noche? Mire al pasillo y algo se movio.",
        "terror",
    )

    assert any("hook starts generically" in reason for reason in reasons)


def test_subtitle_style_scales_up_for_vertical_video():
    style = compositor._build_subtitle_style()
    expected_font_size = max(
        settings.subtitle_font_size,
        round(settings.video_height * settings.subtitle_font_scale),
    )

    assert f"FontSize={expected_font_size}" in style
    assert "MarginL=" in style
    assert "MarginR=" in style


def test_imagen_quota_error_disables_future_attempts(monkeypatch):
    monkeypatch.setattr(video_gen, "_imagen_daily_count", 0)
    monkeypatch.setattr(video_gen, "_imagen_daily_reset", 0.0)

    video_gen._disable_imagen_for_today(RuntimeError("429 RESOURCE_EXHAUSTED"))

    assert video_gen._check_imagen_quota() is False


def test_generate_video_reuses_historical_scene_when_first_frame_fails(monkeypatch, tmp_path):
    db_path = tmp_path / "storage" / "viralstack.db"
    history_dir = tmp_path / "storage" / "output" / "historias" / "7"
    history_dir.mkdir(parents=True, exist_ok=True)
    historical_scene = history_dir / "scene_000.png"
    historical_scene.write_bytes(b"history")

    monkeypatch.setattr(settings, "db_path", str(db_path))
    monkeypatch.setattr(video_gen.discord_alerts, "send_info", lambda *args, **kwargs: None)

    async def _always_fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(video_gen, "_generate_single_image", _always_fail)

    result = asyncio.run(video_gen.generate_video(["Escena imposible"], "historias", 8))

    assert len(result) == 1
    assert Path(result[0]).read_bytes() == b"history"


def test_generate_video_creates_emergency_frame_when_no_reuse_exists(monkeypatch, tmp_path):
    db_path = tmp_path / "storage" / "viralstack.db"
    monkeypatch.setattr(settings, "db_path", str(db_path))
    monkeypatch.setattr(video_gen.discord_alerts, "send_info", lambda *args, **kwargs: None)

    async def _always_fail(*args, **kwargs):
        raise RuntimeError("boom")

    def _fake_emergency_frame(output_dir, account, index):
        path = output_dir / f"scene_{index:03d}_emergency.png"
        path.write_bytes(b"emergency")
        return str(path)

    monkeypatch.setattr(video_gen, "_generate_single_image", _always_fail)
    monkeypatch.setattr(video_gen, "_create_emergency_frame", _fake_emergency_frame)

    result = asyncio.run(video_gen.generate_video(["Nada sale"], "dinero", 1))

    assert len(result) == 1
    assert Path(result[0]).read_bytes() == b"emergency"


def test_platform_registry_includes_instagram_disabled_by_default():
    registry = settings_module.load_platform_registry()
    platforms = settings_module.load_platform_config()

    assert "instagram" in registry
    assert registry["instagram"]["publisher"] == "webhook"
    assert platforms["terror"]["instagram"] is False


def test_platform_file_toggles_override_account_defaults(monkeypatch):
    monkeypatch.setitem(settings_module.ACCOUNTS, "tech", {
        "platforms": {"instagram": True},
    })

    normalized = settings_module._normalize_platform_config({
        "tech": {"instagram": False},
    })

    assert normalized["tech"]["instagram"] is False


def test_convention_paths_work_for_custom_account_ids():
    assert Path(settings.get_youtube_token_path("tech")).name == "youtube_tech_token.json"
    assert Path(settings.get_gmail_token_path("tech")).name == "gmail_tech_token.json"
    assert Path(settings.get_cookies_path("tech")).name == "tech_cookies.txt"


def test_custom_account_script_limits_are_configurable(monkeypatch):
    monkeypatch.setitem(script_gen.ACCOUNTS, "tech", {
        "min_words": 70,
        "max_words": 210,
        "duration_min_seconds": 25,
        "duration_max_seconds": 75,
        "hook_min_words": 4,
        "hook_max_words": 12,
    })

    assert script_gen._word_limits_for("tech") == (70, 210)
    assert script_gen._duration_limits_for("tech") == (25, 75)
    assert script_gen._hook_word_limits_for("tech") == (4, 12)


def test_instagram_without_webhook_is_skipped():
    result = asyncio.run(platform_publishers.publish_to_platform(
        "instagram",
        "missing.mp4",
        "Titulo",
        "terror",
        hashtags=["#test"],
    ))

    assert result.skipped is True
    assert result.status == "skipped"
    assert result.ok is False
