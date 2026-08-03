from types import SimpleNamespace

from app.agents.delivery import inspect_delivery_status


def write_step():
    return SimpleNamespace(
        tool="workspace_write",
        tool_result={"changed": True},
    )


def test_write_requires_verification_status():
    result = inspect_delivery_status(
        agent_id="frontend",
        answer="Dosya oluşturuldu.",
        trace=[write_step()],
    )
    assert result.accepted is False


def test_unverified_status_is_accepted_without_test():
    result = inspect_delivery_status(
        agent_id="frontend",
        answer=(
            "Dosya oluşturuldu.\n"
            "Doğrulama Durumu: test edilmedi; package.json bulunmuyor."
        ),
        trace=[write_step()],
    )
    assert result.accepted is True


def test_false_verified_claim_is_rejected():
    result = inspect_delivery_status(
        agent_id="frontend",
        answer=(
            "Dosya oluşturuldu ve çalışıyor.\n"
            "Doğrulama Durumu: doğrulandı."
        ),
        trace=[write_step()],
    )
    assert result.accepted is False
