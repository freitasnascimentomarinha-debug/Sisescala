"""Verificar documento (usuário logado): confere o código impresso no detalhe assinado e mostra o conteúdo assinado."""
from sisescala.sessao import pagina
from sisescala.tela_verificacao import mostrar

mostrar(pagina().ctx, completo=True)
