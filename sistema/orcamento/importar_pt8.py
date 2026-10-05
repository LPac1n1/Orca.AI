"""Importa o caso real do Parecer Técnico 8 (transcrito em fase0/sejc/pt8_dados.json) para o modelo do sistema."""
import json
from .modelo import Projeto, Config, RubricaRH, RubricaMaterial, PesquisaSalarial, Fonte, Subitem, Evidencia

DATA_VAGAS = '2026-03-25'      # data impressa nas páginas de vaga
DATA_CARRINHOS = '2026-03-26'  # data impressa nos carrinhos


def carregar(caminho_json):
    D = json.load(open(caminho_json, encoding='utf-8'))
    rub = []
    forn = {}
    for r in D['rh']:
        f = r['fornecedores'] if isinstance(r['fornecedores'], list) else forn[int(r['fornecedores'][1:])]
        forn[r['item']] = f
        pes = [PesquisaSalarial(nome=n, cnpj=c, data_pesquisa=DATA_VAGAS, valor=v, evidencia=Evidencia(origem='transcrito'))
               for (n, c), v in zip(f, r['precos'])]
        rub.append(RubricaRH(item=r['item'], cargo=r['cargo'], horas_mes=r['horas_mes'], meses=r['meses'],
                             pesquisas=pes, valor_mensal_plano=r['plano_mensal']))
    for m in D['materiais']:
        fontes = [Fonte(nome=n, cnpj=c, data_pesquisa=DATA_CARRINHOS, evidencia=Evidencia(origem='transcrito')) for n, c in m['fornecedores']]
        subs, extra = [], {}
        for s in m['subitens']:
            subs.append(Subitem(descricao=s['nome'], qtd=s['qtd'], precos=s['precos'], valor_plano=s['plano']))
            if 'fornecedores_proprios' in s:
                extra[s['nome']] = [dict(nome=n, cnpj=c, data_pesquisa=DATA_CARRINHOS) for n, c in s['fornecedores_proprios']]
        rub.append(RubricaMaterial(item=m['item'], descricao=m['rubrica'], meses=m['meses'], fontes=fontes, subitens=subs,
                                   fontes_por_subitem=extra))
    rub.sort(key=lambda r: r.item)
    return Projeto(nome='Projeto de Cidadania e Capacitação em Direitos Humanos', processo='019.00003001/2026-72',
                   proponente='Centro de Promoção e Inclusão Social 26 de Julho', teto=D['teto'], cep='03977-015',
                   config=Config(divisor_horas='praticado', valores_defensaveis=True), rubricas=rub)
