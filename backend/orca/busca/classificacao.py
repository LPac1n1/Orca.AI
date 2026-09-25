"""O que cada loja vende (D-74): para indicar as lojas de cada lote sem a pessoa precisar saber.

Três fontes, nesta ordem de confiança:
1. escolha da pessoa (formulário da loja em Catálogos);
2. descoberta pelo sistema: a busca da loja é testada com produtos típicos de cada tipo
   (caneta, arroz, detergente…); a loja vende o tipo quando a busca devolve pelo menos 2
   produtos dele — poucos pedidos, uma vez por loja;
3. aprendizado: páginas confirmadas (🟢) nas pesquisas mostram o que a loja vende (vale
   também para as lojas só com janela, que o sistema não pesquisa sozinho).
Aqui fica só a parte sem rede: os tipos, os produtos de teste e a regra de decisão.
"""

from orca.busca.ranking import Candidato, mesmo_tipo, parecenca, titulo_do_endereco
from orca.correspondencia import Especificacao

# tipo de loja → como aparece na tela
NOMES = {
    "papelaria": "Papelaria e escritório",
    "escritorio": "Papelaria e escritório",
    "alimentos": "Alimentos",
    "bebidas": "Bebidas",
    "limpeza": "Limpeza e higiene",
    "descartaveis": "Descartáveis",
    "utensilios": "Utensílios de casa e cozinha",
    "informatica": "Informática",
}

# produtos de teste de cada tipo (o primeiro que a loja tiver já basta)
AMOSTRAS: dict[str, tuple[str, ...]] = {
    "papelaria": ("Caneta esferográfica", "Grampeador", "Papel sulfite A4"),
    "alimentos": ("Arroz", "Café torrado"),
    "bebidas": ("Refrigerante", "Suco"),
    "limpeza": ("Detergente", "Água sanitária"),
    "descartaveis": ("Copo descartável", "Guardanapo de papel"),
    "utensilios": ("Panela", "Talheres"),
    "informatica": ("Mouse", "Cartucho de tinta"),
}
MINIMO = 2  # produtos do tipo na busca para dizer que a loja vende


def vende_o_tipo(termo: str, candidatos: list[Candidato]) -> bool:
    """A busca por um produto típico trouxe pelo menos 2 produtos desse tipo?"""
    produto = Especificacao(termo)
    quantos = 0
    for c in candidatos:
        titulo = c.titulo or titulo_do_endereco(c.url)
        if mesmo_tipo(produto, titulo, parecenca(produto, titulo), c.marca):
            quantos += 1
            if quantos >= MINIMO:
                return True
    return False


def nomes(categorias) -> list[str]:
    """Os tipos como aparecem na tela, sem repetir ("papelaria" e "escritorio" são um só)."""
    return list(dict.fromkeys(NOMES.get(c, c) for c in categorias))
