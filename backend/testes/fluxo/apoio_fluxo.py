"""Projeto de exemplo gravado no banco, para os testes do fluxo.

Lote "Copa e escritório" (2 itens, 12 meses) com 5 lojas:
- G (Gimba) tem o menor total, mas o leite condensado passa da média (regra B);
- retirando G (Saída 2), T (Tenda) vira a escolhida e tudo fica dentro da média;
- X não tem consulta de CNPJ e fica de fora.
Cargo "Educador social" com 5 vagas: uma repetida em outra plataforma e uma sem salário.
"""

import json
from datetime import UTC, date, datetime

from orca.banco import (
    Cargo,
    Fonte,
    Item,
    Lote,
    Observacao,
    Orcamento,
    Organizacao,
    Projeto,
    definir_camadas_do_projeto,
    sessao_como,
)
from orca.coleta import Captura, DadosCnpj, registrar_captura, registrar_consulta_cnpj
from orca.dominio import normalizar_cnpj

USUARIO = "usuario:Leonardo"
HOJE = date(2026, 9, 24)
COLETA = datetime(2026, 9, 23, 14, 0, tzinfo=UTC)
PAPEL, LEITE = "7891173023001", "7891000100103"

LOJAS = {  # id: (domínio, CNPJ, consultar, preço do papel, preço do leite)
    "K": ("kalunga.com.br", "43283811000150", True, 3600, 1100),
    "G": ("gimba.com.br", "54651716001150", True, 3400, 1100),
    "L": ("lepok.com.br", "19576717000104", True, 3500, 1000),
    "T": ("tendaatacado.com.br", "01157555001186", True, 3450, 1050),
    "X": ("loja-x.com.br", "45543915073650", False, 3000, 800),
}


def cnpj_de_teste(n: int) -> str:
    base = f"{n:08d}0001"
    for dv in range(100):
        try:
            return normalizar_cnpj(f"{base}{dv:02d}")
        except ValueError:
            continue
    raise AssertionError


VAGAS = [  # (id, plataforma, CNPJ, salário mín., salário máx., título, publicada)
    ("v1", "catho.com.br", cnpj_de_teste(701), 250_000, 300_000, "Educador Social", "2026-09-10"),
    ("v2", "catho.com.br", cnpj_de_teste(702), 260_000, None, "Educador(a) Social", "2026-09-11"),
    ("v3", "indeed.com.br", cnpj_de_teste(703), 270_000, None, "Educador Social", "2026-09-12"),
    ("v4", "indeed.com.br", cnpj_de_teste(701), 250_000, 300_000, "Educador Social", "2026-09-12"),  # = v1
    ("v5", "infojobs.com.br", cnpj_de_teste(704), None, None, "Educador Social", "2026-09-12"),  # sem salário
]


def _captura(url: str, momento: datetime = COLETA, semente: str = "") -> Captura:
    marca = f"{url}|{momento.isoformat()}|{semente}".encode()
    return Captura(url, url, momento, "Página", 200, "<html></html>", (), "texto", b"%PDF-" + marca,
                   b"PNG-" + marca, b"MHTML-" + marca, None, "C1", None)


def _fonte(s, dominio: str, tipo: str, cache: dict) -> Fonte:
    if (dominio, tipo) not in cache:
        cache[(dominio, tipo)] = Fonte(tipo=tipo, nome=dominio, dominio=dominio)
        s.add(cache[(dominio, tipo)])
    return cache[(dominio, tipo)]


def observar_item(s, armazem, item: Item, fonte: Fonte, cnpj: str, preco: int, momento: datetime = COLETA,
                  semente: str = "") -> Observacao:
    url = f"https://{fonte.dominio}/produto/{item.ean}"
    evidencia = registrar_captura(s, armazem, _captura(url, momento, semente))
    obs = Observacao(
        alvo_tipo="item", item=item, fonte=fonte, cnpj_vendedor=cnpj, url=url, titulo=item.descricao, marca=item.marca,
        ean=item.ean, preco_centavos=preco, encontrado=True, coletado_em=momento, metodo="C1", evidencia=evidencia,
        preco_no_html=True, autor=s.info["autor"],
    )
    s.add(obs)
    return obs


def criar_projeto(fabrica, armazem) -> dict:
    """Grava o projeto de exemplo e devolve os ids."""
    with sessao_como(fabrica, USUARIO) as s:
        projeto = Projeto(
            organizacao=Organizacao(nome="OSC Exemplo", cnpj=cnpj_de_teste(123)), nome="Projeto Exemplo",
            teto_centavos=1_611_720, duracao_meses=12, data_entrega=date(2026, 12, 15),
        )
        s.add(projeto)
        definir_camadas_do_projeto(s, projeto)
        materiais = Orcamento(projeto=projeto, nome="Material de consumo", tipo="materiais")
        pessoal = Orcamento(projeto=projeto, nome="Recursos humanos", tipo="mao_de_obra")
        lote = Lote(orcamento=materiais, nome="Copa e escritório")
        papel = Item(lote=lote, descricao="Papel sulfite A4 75g 500 folhas", categoria="papel", marca="Chamex",
                     ean=PAPEL, qtd_planejada=10, mes_inicio=1, mes_fim=12)
        leite = Item(lote=lote, descricao="Leite condensado 395g", categoria="alimento", marca="Moça", ean=LEITE,
                     qtd_planejada=5, mes_inicio=1, mes_fim=12)
        cargo = Cargo(orcamento=pessoal, nome="Educador social", regime="recibo", jornada_id="regra_geral",
                      horas_planejadas_centesimos=8000, mes_inicio=1, mes_fim=12)
        s.add_all([papel, leite, cargo])
        fontes: dict = {}
        for chave, (dominio, cnpj, consultar, preco_papel, preco_leite) in LOJAS.items():
            fonte = _fonte(s, dominio, "loja", fontes)
            observar_item(s, armazem, papel, fonte, cnpj, preco_papel)
            observar_item(s, armazem, leite, fonte, cnpj, preco_leite)
            if consultar:
                registrar_consulta_cnpj(s, DadosCnpj(cnpj, f"Loja {chave} Ltda", f"Loja {chave}", "ATIVA", None,
                                                     "São Paulo", "SP", "teste", {}))
        vagas = {}
        for vid, dominio, cnpj, smin, smax, titulo, publicada in VAGAS:
            url = f"https://{dominio}/vaga/{vid}"
            evidencia = registrar_captura(s, armazem, _captura(url))
            obs = Observacao(
                alvo_tipo="cargo", cargo=cargo, fonte=_fonte(s, dominio, "empresa", fontes), cnpj_vendedor=cnpj,
                url=url, titulo=titulo, salario_min_centavos=smin, salario_max_centavos=smax,
                encontrado=smin is not None, coletado_em=COLETA, metodo="C1", evidencia=evidencia, preco_no_html=True,
                dados_brutos=json.dumps({"extraido": {"cidade": "São Paulo", "data_publicacao": publicada}}),
                autor=USUARIO,
            )
            s.add(obs)
            vagas[vid] = obs
            registrar_consulta_cnpj(s, DadosCnpj(cnpj, f"Empresa {vid}", None, "ATIVA", None, "São Paulo", "SP", "teste", {}))
        s.flush()
        return {"projeto": projeto.id, "lote": lote.id, "papel": papel.id, "leite": leite.id, "cargo": cargo.id,
                "materiais": materiais.id, "vagas": {k: v.id for k, v in vagas.items()},
                "fontes": {k: fontes[(LOJAS[k][0], "loja")].id for k in LOJAS}}


def loja(ids: dict, chave: str) -> str:
    return f"{ids['fontes'][chave]}:{LOJAS[chave][1]}"
