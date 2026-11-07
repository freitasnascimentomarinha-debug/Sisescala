import pytest

from sisescala import auth


@pytest.fixture(autouse=True)
def _bcrypt_rapido(monkeypatch):
    monkeypatch.setattr(auth, "ROUNDS", 4)
