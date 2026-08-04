from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.pandora_voice.config import PandoraVoiceConfig


def test_models_json_loads_pinned_turkish_v3() -> None:
    path = Path(__file__).parents[1] / "config" / "pandora_voice_models.json"
    config = PandoraVoiceConfig.from_models_json(path)
    assert config.engine == "chatterbox_multilingual_v3"
    assert config.language == "tr"
    assert config.model_revision == "e2d6902dd4c1301892935d0a0277325551e8060e"
    assert config.package_version == "0.1.7"


def test_config_rejects_floating_revision_and_public_bind() -> None:
    with pytest.raises(ValueError, match="immutable"):
        replace(PandoraVoiceConfig(), model_revision="main").validate()
    with pytest.raises(ValueError, match="loopback"):
        replace(PandoraVoiceConfig(), worker_host="0.0.0.0").validate()


def test_config_requires_single_active_synthesis() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        replace(PandoraVoiceConfig(), max_concurrent_synthesis=2).validate()


def test_models_json_requires_runtime_object(tmp_path: Path) -> None:
    path = tmp_path / "models.json"
    path.write_text(json.dumps({"voice_name": "Pandora"}), encoding="utf-8")
    with pytest.raises(ValueError, match="production_runtime"):
        PandoraVoiceConfig.from_models_json(path)
