import pytest

from app.agent.protocol import (
    AgentProtocolError,
    parse_single_file_action,
)


def test_complete_file_envelope_becomes_workspace_write():
    raw = '''<<<ADAM_FILE path="src/components/Calculator.tsx">>>
export default function Calculator() {
  return <div>Calculator</div>;
}
<<<END_ADAM_FILE>>>'''
    action = parse_single_file_action(
        raw,
        "src/components/Calculator.tsx",
    )
    assert action.action == "tool"
    assert action.tool == "workspace_write"
    assert action.arguments["path"] == (
        "src/components/Calculator.tsx"
    )
    assert "return <div>" in action.arguments["content"]


def test_file_envelope_strips_redundant_inner_code_fence():
    raw = '''<<<ADAM_FILE path="tests/calculator.test.js">>>
```js
import test from "node:test";
```
<<<END_ADAM_FILE>>>'''

    action = parse_single_file_action(
        raw,
        "tests/calculator.test.js",
    )

    assert action.arguments["content"] == (
        'import test from "node:test";\n'
    )


def test_file_envelope_allows_ignored_trailing_delivery_summary():
    raw = '''<<<ADAM_FILE path="src/app.js">>>
export const value = 7.5;
<<<END_ADAM_FILE>>>

Doğrulama Durumu: test edilmedi/doğrulanmadı'''

    action = parse_single_file_action(raw, "src/app.js")

    assert action.tool == "workspace_write"
    assert action.arguments["content"] == (
        "export const value = 7.5;\n"
    )


def test_multiple_file_envelopes_are_rejected():
    raw = '''<<<ADAM_FILE path="src/app.js">>>
export const value = 1;
<<<END_ADAM_FILE>>>
<<<ADAM_FILE path="src/app.js">>>
export const value = 2;
<<<END_ADAM_FILE>>>'''

    with pytest.raises(AgentProtocolError, match="birden fazla"):
        parse_single_file_action(raw, "src/app.js")


def test_truncated_file_envelope_is_never_applied():
    raw = '''<<<ADAM_FILE path="src/components/Calculator.tsx">>>
export default function Calculator() {
  return <div>'''
    with pytest.raises(AgentProtocolError, match="kesildi"):
        parse_single_file_action(
            raw,
            "src/components/Calculator.tsx",
        )


def test_wrong_exact_path_is_rejected():
    raw = '''<<<ADAM_FILE path="src/Calculator.tsx">>>
export default function Calculator() { return null; }
<<<END_ADAM_FILE>>>'''
    with pytest.raises(AgentProtocolError, match="beklenen dosya"):
        parse_single_file_action(
            raw,
            "src/components/Calculator.tsx",
        )


def test_complete_local_plain_source_can_enter_verification_gate():
    raw = """export function discountedPrice(price, percent) {
  return price - (price * percent / 100);
}"""

    action = parse_single_file_action(
        raw,
        "src/discount.js",
        allow_plain_complete=True,
    )

    assert action.tool == "workspace_write"
    assert action.arguments["path"] == "src/discount.js"
    assert action.arguments["content"].endswith("\n")


def test_plain_source_remains_rejected_without_local_stop_signal():
    raw = "export const value = 1;"

    with pytest.raises(AgentProtocolError, match="ADAM_FILE"):
        parse_single_file_action(raw, "src/app.js")


def test_truncated_envelope_is_rejected_even_with_local_stop_signal():
    raw = '''<<<ADAM_FILE path="src/app.js">>>
export function unfinished() {'''

    with pytest.raises(AgentProtocolError, match="kesildi"):
        parse_single_file_action(
            raw,
            "src/app.js",
            allow_plain_complete=True,
        )
