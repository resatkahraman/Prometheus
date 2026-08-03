import pytest
from pydantic import ValidationError

from app.core.schemas import OrchestrateRequest


def test_requires_exactly_one_input_shape():
    with pytest.raises(ValidationError):
        OrchestrateRequest()

    with pytest.raises(ValidationError):
        OrchestrateRequest(
            message="merhaba",
            messages=[{"role": "user", "content": "merhaba"}],
        )


def test_direct_requires_provider():
    with pytest.raises(ValidationError):
        OrchestrateRequest(message="merhaba", mode="direct")
