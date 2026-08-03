import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.tools.registry import build_default_tool_registry


def make_workspace(root: Path) -> None:
    (root / "src/components").mkdir(parents=True)
    (root / "tests/src/components").mkdir(parents=True)
    (root / "node_modules/.bin").mkdir(parents=True)
    (root / "node_modules/vitest").mkdir(parents=True)
    (root / "node_modules/react").mkdir(parents=True)
    (root / "node_modules/@testing-library/react").mkdir(parents=True)
    (root / "node_modules/.bin/vitest").write_text("", encoding="utf-8")
    (root / "package.json").write_text(
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
    (root / "src/components/ScoreCard.test.tsx").write_text(
        "import { render } from '@testing-library/react';\n"
        "import '@testing-library/jest-dom';\n"
        "describe('ScoreCard', () => { test('x', () => expect(true).toBe(true)) });\n",
        encoding="utf-8",
    )
    (root / "tests/src/components/TestButton.test.tsx").write_text(
        "describe('TestButton', () => { test('x', () => expect(true).toBe(true)) });\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_preflight_installs_missing_test_package_before_model(
    monkeypatch,
    tmp_path: Path,
):
    make_workspace(tmp_path)
    registry = build_default_tool_registry(
        settings=Settings(workspace_root=tmp_path)
    )
    terminal = registry.get("safe_terminal")
    monkeypatch.setattr(terminal, "_resolve_npm_base", lambda: ["npm"])

    result = await terminal.preflight(
        {"preset": "npm_test", "extra_args": ["--run"]}
    )

    assert result["failure_kind"] == "npm_test_packages_missing"
    assert result["missing_packages"] == ["@testing-library/jest-dom"]
    assert result["remediation"]["arguments"] == {
        "preset": "npm_install_dev",
        "extra_args": ["@testing-library/jest-dom"],
    }


@pytest.mark.asyncio
async def test_preflight_uses_vitest_globals_without_rewriting_tests(
    monkeypatch,
    tmp_path: Path,
):
    make_workspace(tmp_path)
    (tmp_path / "node_modules/@testing-library/jest-dom").mkdir(parents=True)
    registry = build_default_tool_registry(
        settings=Settings(workspace_root=tmp_path)
    )
    terminal = registry.get("safe_terminal")
    monkeypatch.setattr(terminal, "_resolve_npm_base", lambda: ["npm"])

    result = await terminal.preflight(
        {"preset": "npm_test", "extra_args": ["--run"]}
    )

    assert result["failure_kind"] == "vitest_globals_required"
    assert result["remediation"]["arguments"] == {
        "preset": "npm_test",
        "extra_args": ["--run", "--globals"],
    }

    ready = await terminal.preflight(
        {
            "preset": "npm_test",
            "extra_args": ["--run", "--globals"],
        }
    )
    assert ready["ready"] is True


@pytest.mark.asyncio
async def test_preflight_does_not_add_vitest_flags_to_node_test_runner(
    monkeypatch,
    tmp_path: Path,
):
    (tmp_path / "tests").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "node --test"}}),
        encoding="utf-8",
    )
    (tmp_path / "tests/calculator.test.js").write_text(
        "import test from 'node:test';\n"
        "test('works', () => {});\n",
        encoding="utf-8",
    )
    registry = build_default_tool_registry(
        settings=Settings(workspace_root=tmp_path)
    )
    terminal = registry.get("safe_terminal")
    monkeypatch.setattr(terminal, "_resolve_npm_base", lambda: ["npm"])

    result = await terminal.preflight(
        {"preset": "npm_test", "extra_args": []}
    )

    assert result["ready"] is True
    assert result["logical_command"] == ["npm", "test", "--"]


@pytest.mark.asyncio
async def test_preflight_runs_dependency_free_node_tests_without_install(
    monkeypatch,
    tmp_path: Path,
):
    (tmp_path / "test").mkdir()
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "node --test"}}),
        encoding="utf-8",
    )
    (tmp_path / "test/example.test.js").write_text(
        "import test from 'node:test';\n"
        "test('works', () => {});\n",
        encoding="utf-8",
    )
    registry = build_default_tool_registry(
        settings=Settings(workspace_root=tmp_path)
    )
    terminal = registry.get("safe_terminal")
    monkeypatch.setattr(terminal, "_resolve_npm_base", lambda: ["npm"])

    result = await terminal.preflight(
        {"preset": "npm_test", "extra_args": []}
    )

    assert not (tmp_path / "node_modules").exists()
    assert result["ready"] is True
    assert result["logical_command"] == ["npm", "test", "--"]
