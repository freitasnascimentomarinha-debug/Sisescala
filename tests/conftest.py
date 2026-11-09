import pytest

from sisescala import auth


@pytest.fixture(autouse=True)
def _bcrypt_rapido(monkeypatch):
    monkeypatch.setattr(auth, "ROUNDS", 4)


@pytest.fixture(autouse=True)
def _fila_do_mais_antigo_ao_mais_moderno(monkeypatch):
    """Os testes antigos foram escritos com a fila do mais antigo ao mais moderno (m1 primeiro). O padrão do sistema
    agora é do mais moderno ao mais antigo; aqui o padrão dos testes continua o antigo, e os testes do novo padrão
    pedem `sentido_fila="moderno_antigo"` explicitamente."""
    from sisescala.modelos import Escala
    original = Escala.__init__

    def init(self, *args, **kwargs):
        kwargs.setdefault("sentido_fila", "antigo_moderno")
        original(self, *args, **kwargs)
    monkeypatch.setattr(Escala, "__init__", init)
