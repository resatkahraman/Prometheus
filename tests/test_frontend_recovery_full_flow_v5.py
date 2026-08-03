import json
from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.models import SupervisorCommand, SupervisorTask
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class ModelMustNotRun:
    def __init__(self):
        self.calls = 0

    async def run(self, request):
        self.calls += 1
        raise AssertionError("Frontend harness recovery must not call a model")


@pytest.mark.asyncio
async def test_report_scenario_finishes_without_focused_agent(
    monkeypatch,
    tmp_path: Path,
):
    (tmp_path / "src/components").mkdir(parents=True)
    (tmp_path / "tests/src/components").mkdir(parents=True)
    (tmp_path / "node_modules/.bin").mkdir(parents=True)
    (tmp_path / "node_modules/vitest").mkdir(parents=True)
    (tmp_path / "node_modules/react").mkdir(parents=True)
    (tmp_path / "node_modules/@testing-library/react").mkdir(parents=True)
    (tmp_path / "node_modules/.bin/vitest").write_text("", encoding="utf-8")

    (tmp_path / "src/components/ScoreCard.tsx").write_text(
        "export default function ScoreCard(){return null}",
        encoding="utf-8",
    )
    (tmp_path / "src/components/ScoreCard.test.tsx").write_text(
        "import '@testing-library/jest-dom';\n"
        "describe('ScoreCard',()=>{test('x',()=>expect(true).toBe(true))});\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/src/components/TestButton.test.tsx").write_text(
        "describe('TestButton',()=>{test('x',()=>expect(true).toBe(true))});\n",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {"test": "vitest"},
                "dependencies": {"react": "1.0.0"},
                "devDependencies": {
                    "vitest": "0.24.5",
                    "@testing-library/react": "1.0.0",
                },
            }
        ),
        encoding="utf-8",
    )

    settings = Settings(
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
        supervisor_approval_background=False,
        supervisor_auto_review=True,
    )
    tools = build_default_tool_registry(settings=settings)
    terminal = tools.get("safe_terminal")
    monkeypatch.setattr(terminal, "_resolve_npm_base", lambda: ["npm"])

    executed = []

    async def fake_execute_approved(arguments):
        executed.append(arguments)
        preset = arguments["preset"]
        if preset == "npm_install_dev":
            assert arguments["extra_args"] == ["@testing-library/jest-dom"]
            (tmp_path / "node_modules/@testing-library/jest-dom").mkdir(
                parents=True
            )
            manifest = json.loads(
                (tmp_path / "package.json").read_text(encoding="utf-8")
            )
            manifest.setdefault("devDependencies", {})[
                "@testing-library/jest-dom"
            ] = "6.0.0"
            (tmp_path / "package.json").write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )
            return {
                "preset": preset,
                "command": ["npm", "install", "--save-dev", "@testing-library/jest-dom"],
                "logical_command": ["npm", "install", "--save-dev", "@testing-library/jest-dom"],
                "cwd": str(tmp_path),
                "exit_code": 0,
                "timed_out": False,
                "stdout": "added 1 package",
                "stderr": "",
                "success": True,
                "runtime_revision": "terminal-env-v5",
            }
        if preset == "npm_test":
            assert arguments["extra_args"] == ["--run", "--globals"]
            return {
                "preset": preset,
                "command": ["npm", "test", "--", "--run", "--globals"],
                "logical_command": ["npm", "test", "--", "--run", "--globals"],
                "cwd": str(tmp_path),
                "exit_code": 0,
                "timed_out": False,
                "stdout": "3 passed",
                "stderr": "",
                "success": True,
                "runtime_revision": "terminal-env-v5",
            }
        raise AssertionError(arguments)

    monkeypatch.setattr(terminal, "execute_approved", fake_execute_approved)

    agent = ModelMustNotRun()
    service = SupervisorService(
        settings=settings,
        agent=agent,
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = SupervisorTask(
        id="TASK-002",
        title="ScoreCard ve davranış testleri",
        priority="zorunlu",
        assigned_agent="frontend",
        evidence=[],
        acceptance_criteria=["npm test başarılı"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayır",
        verification="npm test -- --run",
        user_approval="gerekli",
        exact_files=[
            "src/components/ScoreCard.tsx",
            "src/components/ScoreCard.test.tsx",
        ],
        status="ready",
        autonomy_granted=True,
    )
    command = SupervisorCommand(
        id="cmd",
        goal="ScoreCard testlerini tamamla",
        status="ready",
        autonomy_mode="task",
        plan_text="",
        tasks=[task],
    )
    await service.store.put(command)

    result = await service.run_task(
        command_id="cmd",
        task_id="TASK-002",
        background=False,
    )
    assert result.tasks[0].status == "awaiting_approval"
    assert result.tasks[0].approval_tool == "safe_terminal"
    pending = result.tasks[0].approval_history[-1]
    assert pending.arguments == {
        "preset": "npm_install_dev",
        "extra_args": ["@testing-library/jest-dom"],
    }

    result = await service.approve(
        command_id="cmd",
        task_id="TASK-002",
        background=False,
    )

    assert result.tasks[0].status == "completed"
    assert result.tasks[0].review_answer.startswith("KABUL")
    assert agent.calls == 0
    assert executed == [
        {
            "preset": "npm_install_dev",
            "extra_args": ["@testing-library/jest-dom"],
        },
        {
            "preset": "npm_test",
            "extra_args": ["--run", "--globals"],
        },
    ]
    assert not any(
        event.type == "focused_step_failed" for event in result.events
    )
