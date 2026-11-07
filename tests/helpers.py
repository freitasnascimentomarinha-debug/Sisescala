from sisescala import auth


def cad_ativo(c, login, nome, senha, email="a@b.com", ramal="2345", celular="21987654321"):
    """Conta já aprovada (o autocadastro real fica pendente até o administrador aprovar)."""
    adm = next((u for u in c.usuarios if u.admin and u.ativo), None)
    return auth.criar_usuario(c, adm.id if adm else None, login, nome, senha, email=email, ramal=ramal,
                              celular=celular, exigir_contato=True)
