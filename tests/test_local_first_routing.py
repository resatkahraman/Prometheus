from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent.engine import AgentEngine
from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.orchestration.circuit_breaker import CircuitBreaker
from app.orchestration.quota import QuotaManager
from app.orchestration.routes import RouteCatalog
from app.orchestration.scoring import ProviderScorer
from app.storage.operations import OperationsStore
from app.supervisor.models import SupervisorTask
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class AvailableRegistry:
    def get_optional(self, _name):
        return object()


@pytest.mark.asyncio
async def test_explicit_local_first_preference_wins_small_coding_task(
    tmp_path: Path,
):
    settings = Settings(
        _env_file=None,
        local_model_enabled=True,
        gemini_api_key="x",
        github_token="x",
        groq_api_key="x",
    )
    store = OperationsStore(tmp_path / "operations.db")
    await store.initialize()
    scorer = ProviderScorer(
        catalog=RouteCatalog(
            settings=settings,
            registry=AvailableRegistry(),
        ),
        quota=QuotaManager(settings=settings, store=store),
        circuit_breaker=CircuitBreaker(
            failure_threshold=3,
            cooldown_seconds=30,
        ),
        store=store,
    )

    scores = await scorer.score_all(
        task_type="coding",
        input_chars=4_000,
        preferred_routes=[
            "local_qwen",
            "github",
            "groq_strong",
            "gemini",
        ],
    )

    assert scores[0].route.key == "local_qwen"
    assert any(
        "Doğrulamalı yerel ilk deneme" in reason
        for reason in scores[0].reasons
    )


@pytest.mark.asyncio
async def test_local_route_rejects_oversized_context(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        local_model_enabled=True,
        local_model_max_input_chars=8_000,
    )
    store = OperationsStore(tmp_path / "operations.db")
    await store.initialize()
    scorer = ProviderScorer(
        catalog=RouteCatalog(
            settings=settings,
            registry=AvailableRegistry(),
        ),
        quota=QuotaManager(settings=settings, store=store),
        circuit_breaker=CircuitBreaker(
            failure_threshold=3,
            cooldown_seconds=30,
        ),
        store=store,
    )

    scores = await scorer.score_all(
        task_type="coding",
        input_chars=8_001,
        preferred_routes=["local_qwen"],
    )
    local = next(item for item in scores if item.route.key == "local_qwen")

    assert local.eligible is False


def _task(*, title: str, attempts: int = 0) -> SupervisorTask:
    return SupervisorTask(
        id="TASK-001",
        title=title,
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["Davranış testten geçsin."],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayır",
        verification="python -m pytest -q",
        user_approval="gerekli",
        exact_files=["app/simple.py"],
        local_model_attempts=attempts,
    )


def test_supervisor_local_gate_is_unlimited_by_default_and_risk_aware(
    tmp_path: Path,
):
    settings = Settings(
        _env_file=None,
        local_model_enabled=True,
        local_model_max_input_chars=30000,
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
    )
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=object(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )

    assert service._local_first_decision(
        task=_task(title="Basit hesaplama işlevini düzelt"),
        target_path="app/simple.py",
        prompt_chars=2_000,
        context_chars=1_000,
    )[0] is True
    assert service._local_first_decision(
        task=_task(title="Basit hesaplama işlevini düzelt"),
        target_path="app/simple.py",
        prompt_chars=17_000,
        context_chars=8_000,
    )[0] is True
    assert service._local_first_decision(
        task=_task(title="Basit işlev", attempts=12),
        target_path="app/simple.py",
        prompt_chars=2_000,
        context_chars=1_000,
    )[0] is True
    assert service._local_first_decision(
        task=_task(title="Authentication token güvenliğini değiştir"),
        target_path="app/auth.py",
        prompt_chars=2_000,
        context_chars=1_000,
    )[0] is False

    capped_settings = Settings(
        _env_file=None,
        local_model_enabled=True,
        local_model_max_attempts_per_task=2,
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
    )
    capped_tools = build_default_tool_registry(settings=capped_settings)
    capped_service = SupervisorService(
        settings=capped_settings,
        agent=object(),
        agents=build_default_agent_registry(capped_tools.names()),
        tools=capped_tools,
    )
    assert capped_service._local_first_decision(
        task=_task(title="Basit işlev", attempts=2),
        target_path="app/simple.py",
        prompt_chars=2_000,
        context_chars=1_000,
    )[0] is False


def test_route_unavailable_error_is_a_distinct_hard_stop():
    assert SupervisorService._is_route_unavailable_error(
        RuntimeError("Auto modunda uygun model rotası bulunamadı.")
    )
    assert not SupervisorService._is_route_unavailable_error(
        TimeoutError("provider timed out")
    )


def test_generic_visual_acceptance_text_does_not_bypass_local_calculator(
    tmp_path: Path,
):
    settings = Settings(
        _env_file=None,
        local_model_enabled=True,
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
    )
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=object(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    calculator = _task(title="Calculator için tek dosya statik web uygulaması")
    calculator.verification = "node -e \"require('fs').accessSync('calculator.html')\""
    calculator.exact_files = ["calculator.html"]
    calculator.acceptance_criteria = ["Animasyonlar ve 3D görseller çalışmalı."]

    assert service._local_first_decision(
        task=calculator,
        target_path="calculator.html",
        prompt_chars=2_000,
        context_chars=1_000,
    )[0] is True

    calculator.title = "3D WebGL gezegen animasyonu"
    assert service._local_first_decision(
        task=calculator,
        target_path="planet.html",
        prompt_chars=2_000,
        context_chars=1_000,
    )[0] is True


def test_calculator_static_quality_gate_rejects_eval_and_accepts_safe_parser():
    calculator = _task(title="Calculator için tek dosya statik web uygulaması")
    unsafe = "<button>C</button><button>DEL</button>+-*/.=<script>eval(input)</script>"
    safe = "<button>C</button><button>DEL</button>+-*/.=<script>parseExpression(input)</script>"
    broken_decimal = (
        "<button>C</button><button>DEL</button>+-*/.=<script>"
        "if (!current.includes('.')) current += '.';</script>"
    )

    assert "eval" in (
        SupervisorService._static_output_quality_issue(
            task=calculator, path="calculator.html", content=unsafe
        ) or ""
    )
    assert SupervisorService._static_output_quality_issue(
        task=calculator, path="calculator.html", content=safe
    ) is None
    assert "mevcut sayı" in (
        SupervisorService._static_output_quality_issue(
            task=calculator, path="calculator.html", content=broken_decimal
        ) or ""
    )


def test_planet_static_quality_gate_requires_visible_rotation_and_controls():
    planet = _task(title="3D WebGL gezegen animasyonu")
    invisible_rotation = (
        "<script>requestAnimationFrame(animate); planet.rotation.y += .01;</script>"
    )
    visible_and_interactive = (
        "<button id='rotate-left'>Sola Döndür</button>"
        "<script>const texture = new THREE.CanvasTexture(canvas);"
        "function animate(){requestAnimationFrame(animate); planet.rotation.y += .01;"
        "renderer.render(scene, camera);}"
        "canvas.addEventListener('pointerdown', start);"
        "canvas.addEventListener('pointermove', turn);</script>"
    )

    assert "doku" in (
        SupervisorService._static_output_quality_issue(
            task=planet, path="planet.html", content=invisible_rotation
        )
        or ""
    )
    assert "kontrol" in (
        SupervisorService._static_output_quality_issue(
            task=planet, path="planet.html", content=invisible_rotation
        )
        or ""
    )
    assert "CanvasTexture" in (
        SupervisorService._static_output_quality_issue(
            task=planet, path="planet.html", content=invisible_rotation
        )
        or ""
    )
    assert "pointermove" in (
        SupervisorService._static_output_quality_issue(
            task=planet, path="planet.html", content=invisible_rotation
        )
        or ""
    )
    assert SupervisorService._static_output_quality_issue(
        task=planet, path="planet.html", content=visible_and_interactive
    ) is None


def test_planet_quality_gate_rejects_invalid_threejs_even_with_animation_words():
    planet = _task(title="3D dönebilen gezegen")
    broken = """
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <button id="rotate-left">Sola Döndür</button>
    <script>
      const scene = new THREE.Scene();
      const renderer = new THREE.WebGLRenderer();
      const texture = new THREE.TextureLoader().load('earth.jpg');
      position(camera, 2);
      function lighting(){ scene.lighting(); const a = new AmbientLight(); }
      function lighting(){ scene.lighting(); }
      function animate(){ requestAnimationFrame(animate); planet.rotation.y += .01; }
      canvas.addEventListener('pointerdown', start);
      canvas.addEventListener('pointermove', turn);
    </script>
    """

    issue = SupervisorService._static_output_quality_issue(
        task=planet, path="planet.html", content=broken
    ) or ""
    assert "birden fazla" in issue
    assert "scene.lighting" in issue
    assert "renderer.render" in issue


def test_planet_quality_intent_comes_from_acceptance_contract_not_only_title():
    task = _task(title="Tek dosya statik web uygulamasını oluştur")
    task.acceptance_criteria = [
        "Gezegen dönüşü yüzey detayı sayesinde görünür olmalı.",
        "Kullanıcı gezegeni fareyle sürükleyebilmeli.",
    ]
    missing_drag = (
        "<script>const t=new THREE.CanvasTexture(c);"
        "requestAnimationFrame(animate); planet.rotation.y += .01;</script>"
    )

    assert "kontrol" in (
        SupervisorService._static_output_quality_issue(
            task=task, path="planet.html", content=missing_drag
        )
        or ""
    )


def test_html_quality_gate_rejects_module_bundle_loaded_as_classic_script():
    task = _task(title="Tek dosya statik web uygulaması")
    broken = (
        '<script src="https://unpkg.com/three/build/three.module.js"></script>'
        '<script>new THREE.Scene()</script>'
    )
    valid_global = (
        '<script src="https://cdnjs.cloudflare.com/three.min.js"></script>'
        '<script>new THREE.Scene()</script>'
    )

    assert "klasik script" in (
        SupervisorService._static_output_quality_issue(
            task=task, path="app.html", content=broken
        )
        or ""
    )
    assert SupervisorService._static_output_quality_issue(
        task=task, path="app.html", content=valid_global
    ) is None

def test_local_quality_retry_keeps_only_available_route():
    local_only = SimpleNamespace(
        excluded_routes=[],
        last_scores=[
            SimpleNamespace(
                eligible=True,
                route_key="local_qwen",
            ),
            SimpleNamespace(
                eligible=False,
                route_key="gemini",
            ),
        ],
    )
    with_remote = SimpleNamespace(
        excluded_routes=[],
        last_scores=[
            SimpleNamespace(
                eligible=True,
                route_key="local_qwen",
            ),
            SimpleNamespace(
                eligible=True,
                route_key="gemini",
            ),
        ],
    )

    assert not AgentEngine._has_eligible_alternative(
        local_only,
        "local_qwen",
    )
    assert AgentEngine._has_eligible_alternative(
        with_remote,
        "local_qwen",
    )
