"""Último degrau das trocas (decisão da OSC, 27/09/2026): quando o item pedido não existe igual em 3 lojas — nem como produto de
outra marca, nem parecido (outro tamanho/variante), nem relacionado (mesma família) — entra um produto que faz parte da CATEGORIA
da rubrica (alimentação → produto alimentício; limpeza → produto de limpeza; escritório/pedagógico → material de papelaria).

Candidatos, nesta ordem: os "itens que podem ser acrescentados" da própria rubrica (lista da OSC) e depois os produtos típicos
da categoria abaixo. Nunca entra um produto que já é outro item da cesta. Entre os que existem iguais em 3 lojas, fica o de preço
mais próximo do valor que o item tinha no plano (para não desequilibrar a rubrica); a IA escolhe o mais razoável entre os primeiros."""
from . import identidade as ID

CATALOGO = {
    'alimentacao': [
        'Biscoito cream cracker 400g', 'Biscoito maisena 400g', 'Biscoito de polvilho 100g', 'Torrada tradicional 160g', 'Achocolatado em pó 400g',
        'Leite em pó integral 400g', 'Suco de caju 1L', 'Suco de maracujá 1L', 'Néctar de pêssego 1L', 'Bolo pronto 250g', 'Barra de cereal 3 unidades',
        'Cereal matinal 300g', 'Aveia em flocos 250g', 'Granola 250g', 'Açúcar refinado 1kg', 'Chá mate 250g', 'Requeijão 200g',
        'Queijo muçarela fatiado 150g', 'Presunto fatiado 200g', 'Iogurte 170g', 'Amendoim torrado 150g', 'Pipoca de micro-ondas 100g',
        'Rosquinha de coco 400g', 'Wafer 140g', 'Pão de queijo congelado 400g', 'Margarina 500g', 'Mel 280g', 'Doce de leite 400g',
    ],
    'limpeza': [
        'Esponja multiuso 4 unidades', 'Pano de chão', 'Pano multiuso 5 unidades', 'Luva de borracha', 'Vassoura', 'Rodo 40cm',
        'Desengordurante 500mL', 'Limpador multiuso 500mL', 'Papel toalha 2 rolos', 'Papel higiênico 12 rolos', 'Sabonete líquido 500mL',
        'Álcool em gel 500g', 'Sacos de lixo 30L', 'Sacos de lixo 100L', 'Lustra móveis 200mL', 'Limpa vidros 500mL', 'Amaciante 2L',
        'Sabão em barra 5 unidades', 'Palha de aço 8 unidades', 'Desinfetante 2L', 'Água sanitária 2L', 'Lava-roupas líquido 3L',
    ],
    'papelaria': [
        'Caneta esferográfica azul', 'Lápis preto', 'Borracha branca', 'Apontador com depósito', 'Cola branca 90g', 'Cola bastão 10g',
        'Tesoura escolar', 'Régua 30cm', 'Marca texto', 'Fita adesiva transparente', 'Envelope saco kraft', 'Pasta com elástico',
        'Caderno espiral 96 folhas', 'Bloco de notas adesivas', 'Papel sulfite A4 500 folhas', 'Grampeador', 'Grampo 26/6', 'Clips',
        'Giz de cera 12 cores', 'Lápis de cor 12 cores', 'Cartolina', 'Papel color set', 'Folha de EVA', 'Canetinha hidrográfica 12 cores',
        'Pincel atômico', 'Corretivo líquido', 'Perfurador', 'Pasta sanfonada', 'Pasta catálogo',
    ],
}


def candidatos(setor, outros_itens, extras=()):
    """Produtos da categoria que podem substituir um item não encontrado: primeiro os extras da rubrica, depois o catálogo;
    fora os que já são outro item da cesta (mesmo produto ou parecido — nível 0 ou 1)."""
    out = []
    for t in list(extras) + CATALOGO.get(setor or '', []):
        if t in out:
            continue
        if any(ID.nivel(d, t, [], ID.familia_padrao(d)) in (0, 1) or ID.nivel(t, d, [], ID.familia_padrao(t)) in (0, 1) for d in outros_itens):
            continue
        out.append(t)
    return out
