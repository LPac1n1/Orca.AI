"""O leitor de carrinho deve ler corretamente os 6 carrinhos reais aceitos pela SEJC (docs-base, Parecer 8)."""
import os
import pytest

from orcamento.importar_pt8 import carregar
from orcamento.leitor_pdf import ler
from orcamento.modelo import RubricaMaterial

AQUI = os.path.dirname(__file__)
RAIZ = os.path.join(AQUI, '..', '..')
BASE = os.path.join(RAIZ, 'docs-base', 'Parecer Técnico 8', 'Orçamentos')
PALAVRAS = {
    'Água sanitária 5L': ['sanitaria'], 'Desinfetante 5L': ['bak'], 'Sabão em pó 1,6Kg': ['tixan'], 'Detergente 500mL': ['limpol'],
    'Álcool 1L': ['coperalcool'], 'Sacos de Lixo 50L 50 Unidades': ['lixo'], 'Bloco de notas 4 Cores': ['post-it'],
    'Pasta sanfonada 12 Divisórias': ['sanfonada'], 'Folha sulfite 500 Folhas': ['chamex'], 'Grampeador de mesa 26/6': ['grampeador'],
    'Grampo 5000 Unidades': ['grampo', '5000'], 'Perfurador 4 Furos': ['perfurador'], 'Lápis preto 4 Unidades': ['lapis'],
    'Clips 100 Unidades': ['clips'], 'Caneta esferográfica 50 Unidades': ['caneta'],
}
CASOS = [('15. Limpeza', 'Limpeza + utensílios', ['Carrefour', 'Tenda', 'Atacadão']),
         ('12. Material pedagógico e escritório', 'Material Pedagógico e Escritório', ['Lepok', 'Kalunga', 'Gimba'])]


@pytest.mark.skipif(not os.path.isdir(BASE), reason='docs-base não disponível')
@pytest.mark.parametrize('pasta,rubrica,lojas', CASOS)
def test_le_carrinhos_reais(pasta, rubrica, lojas):
    p = carregar(os.path.join(RAIZ, 'fase0', 'sejc', 'pt8_dados.json'))
    rub = next(r for r in p.rubricas if isinstance(r, RubricaMaterial) and r.descricao == rubrica)
    for s in rub.subitens:
        s.palavras = PALAVRAS[s.descricao]
    for loja in lojas:
        res = ler(open(os.path.join(BASE, pasta, f'{loja}.pdf'), 'rb').read(), rub.subitens)
        soma = 0
        for s in rub.subitens:
            r = res['itens'][s.descricao]
            assert r['status'] == 'OK', (loja, s.descricao, r)
            assert r['unitario'] in s.precos, (loja, s.descricao, r['unitario'], s.precos)
            soma += r['subtotal']
        assert soma in res['valores_impressos'], (loja, soma)  # a soma lida é o total impresso no carrinho
        assert res['cnpjs'], loja
