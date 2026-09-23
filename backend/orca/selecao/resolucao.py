"""Item acima da média na Regra B: as duas saídas (D-23; docs/02 §9.2; docs/03 §5).

Saída 1 — trocar o produto: o item é substituído por um alternativo, cotado nas
mesmas 3 lojas.
Saída 2 — trocar a loja: a loja escolhida sai do trio, entra a próxima da
classificação e tudo é conferido de novo, até resolver ou acabarem as lojas.

As duas são calculadas e apresentadas; quem escolhe é o usuário. Nunca se troca
uma das outras lojas do trio para subir a média (D-27).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from orca.calculo import Cotacao, formatar, formatar_exato
from orca.selecao.lojas import analisar_lote
from orca.selecao.modelos import AnaliseLote, ItemLote, Loja, Oferta, ParametrosSelecao, SemTrio


@dataclass(frozen=True)
class TentativaTrocaLoja:
    removida: Loja
    motivo: str
    resultado: AnaliseLote | SemTrio


@dataclass(frozen=True)
class ResultadoTrocaLoja:
    sucesso: bool
    tentativas: tuple[TentativaTrocaLoja, ...]
    final: AnaliseLote | None
    mensagem: str


def trocar_loja(itens: Sequence[ItemLote], lojas: Sequence[Loja], p: ParametrosSelecao) -> ResultadoTrocaLoja:
    """Saída 2: retira a loja escolhida enquanto houver item acima da média."""
    analise = analisar_lote(itens, lojas, p)
    if isinstance(analise, SemTrio):
        return ResultadoTrocaLoja(False, (), None, analise.mensagem)
    if not analise.violacoes:
        return ResultadoTrocaLoja(True, (), analise, "Nenhum item acima da média; nada a trocar.")

    retiradas: list[str] = []
    tentativas: list[TentativaTrocaLoja] = []
    while True:
        removida = analise.escolhida
        motivo = "; ".join(v.mensagem for v in analise.violacoes)
        retiradas.append(removida.id)
        nova = analisar_lote(itens, lojas, p, excluir=frozenset(retiradas))
        tentativas.append(TentativaTrocaLoja(removida, motivo, nova))
        if isinstance(nova, SemTrio):
            return ResultadoTrocaLoja(
                False,
                tuple(tentativas),
                None,
                f"Depois de retirar {len(retiradas)} {'loja' if len(retiradas) == 1 else 'lojas'}, "
                f"não há mais lojas elegíveis para formar o trio. Pesquise mais lojas ou troque o produto.",
            )
        if not nova.violacoes:
            nomes = ", ".join(t.removida.nome for t in tentativas)
            return ResultadoTrocaLoja(
                True,
                tuple(tentativas),
                nova,
                f"Resolvido retirando {nomes}. Nova loja do Orçamento 1: {nova.escolhida.nome} "
                f"({formatar(nova.trio[0].total_centavos)}).",
            )
        analise = nova


@dataclass(frozen=True)
class Alternativa:
    """Produto alternativo para um item, com as ofertas encontradas (loja_id → oferta)."""

    id: str
    nome: str
    ofertas: Mapping[str, Oferta]


@dataclass(frozen=True)
class OpcaoTrocaProduto:
    alternativa: Alternativa
    valida: bool
    motivo: str
    cotacao: Cotacao | None
    preco_final_centavos: int | None
    impacto_centavos: int | None  # mudança no total da loja escolhida (quantidade × meses)


def trocar_produto(
    itens: Sequence[ItemLote],
    analise: AnaliseLote,
    item_id: str,
    alternativas: Sequence[Alternativa],
) -> list[OpcaoTrocaProduto]:
    """Saída 1: avalia cada alternativa nas mesmas lojas do trio; as válidas vêm primeiro."""
    p = analise.parametros
    item = next((i for i in itens if i.id == item_id), None)
    if item is None:
        raise ValueError(f"Item {item_id!r} não está no lote")
    trio = [lc.loja for lc in analise.trio]
    escolhida = trio[0]
    totais = {lc.loja.id: lc.total_centavos for lc in analise.trio}

    opcoes = []
    for alt in alternativas:
        faltam = [l.nome for l in trio if (o := alt.ofertas.get(l.id)) is None or not o.utilizavel]
        if faltam:
            opcoes.append(
                OpcaoTrocaProduto(alt, False, "não encontrado como idêntico em: " + ", ".join(faltam), None, None, None)
            )
            continue
        precos = tuple(alt.ofertas[l.id].preco_centavos for l in trio)
        cotacao = Cotacao(precos)
        novos_totais = {
            l.id: totais[l.id] + (alt.ofertas[l.id].preco_centavos - l.ofertas[item.id].preco_centavos) * item.quantidade_total
            for l in trio
        }
        impacto = novos_totais[escolhida.id] - totais[escolhida.id]
        motivos = []
        if p.base_preco_final == "B" and not cotacao.dentro_da_media(precos[0], p.comparar_com):
            motivos.append(
                f"{formatar(precos[0])} na loja {escolhida.nome} passa da média {formatar_exato(cotacao.media_exata)}"
            )
        mais_barata = min(
            trio, key=lambda l: (novos_totais[l.id], -l.qualidade_evidencia, l.nome, l.id)
        )
        if mais_barata.id != escolhida.id:
            motivos.append(f"a loja {escolhida.nome} deixaria de ter o menor total (D-26)")
        preco_final = precos[0] if p.base_preco_final == "B" else cotacao.preco_regra_a()
        opcoes.append(
            OpcaoTrocaProduto(
                alternativa=alt,
                valida=not motivos,
                motivo="; ".join(motivos) if motivos else "atende as regras",
                cotacao=cotacao,
                preco_final_centavos=preco_final,
                impacto_centavos=impacto,
            )
        )
    # Válidas primeiro (menor impacto antes); depois as avaliadas e, por último, as não encontradas.
    return sorted(
        opcoes,
        key=lambda o: (
            not o.valida,
            o.impacto_centavos is None,
            abs(o.impacto_centavos or 0),
            o.alternativa.nome,
        ),
    )
