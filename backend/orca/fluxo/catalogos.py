"""Catálogos e pares da OSC (D-64 a D-66).

- A OSC edita o catálogo de atributos e vocabulário e o de lojas pela interface. As
  edições ficam numa camada por cima do catálogo do sistema, com versão (nada é apagado).
- Antes de salvar uma mudança no vocabulário, o teste de correspondência roda com
  todos os pares (os do sistema e os da OSC): se aparecer um 🟢 errado novo, a mudança é recusada.
- Os pares da OSC nascem das decisões (confirmar ou recusar um produto), de códigos de
  barras iguais em lojas diferentes, ou são escritos à mão.
"""

import copy
import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from orca.banco import (
    CatalogoCamada,
    Correspondencia,
    Item,
    Lote,
    Observacao,
    Orcamento,
    ParReferencia,
    Projeto,
    agora,
)
from orca.coleta.catalogo import LojaCatalogo, catalogo_de_dados, ler_atributos_dados, ler_catalogo_dados
from orca.correspondencia import LEITORES, Avaliacao, Par, Vocabulario, avaliar, pares_do_sistema

SO_POR_PESSOA = frozenset({"escopo", "periodicidade", "unidade_de_cobranca", "modelo_exato"})
COLETAS = ("C0", "C1", "C2", "C3", "C4", "proposta")


class ErroCatalogo(ValueError):
    pass


def _impressao(conteudo: dict) -> str:
    return hashlib.sha256(json.dumps(conteudo, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


# --- Mescla (catálogo do sistema + mudanças da OSC) ------------------------------------------------


def _lista(sinonimos) -> list[str]:
    return list(sinonimos) if isinstance(sinonimos, list | tuple) else [sinonimos] if sinonimos else []


def mesclar_atributos(base: dict, mudancas: dict | None) -> dict:
    """`categorias` da OSC trocam a lista da categoria; `vocabulario` troca os sinônimos de cada valor.

    `None` retira (a categoria, o grupo ou o valor) do catálogo da OSC.
    """
    resultado = copy.deepcopy(base)
    if not mudancas:
        return resultado
    categorias = resultado.setdefault("categorias", {})
    for categoria, atributos in (mudancas.get("categorias") or {}).items():
        if atributos is None:
            categorias.pop(categoria, None)
        else:
            categorias[categoria] = list(atributos)
    vocabulario = resultado.setdefault("vocabulario", {})
    for atributo, grupos in (mudancas.get("vocabulario") or {}).items():
        for grupo, valores in grupos.items():
            if valores is None:
                (vocabulario.get(atributo) or {}).pop(grupo, None)
                continue
            destino = vocabulario.setdefault(atributo, {}).setdefault(grupo, {})
            for valor, sinonimos in valores.items():
                if sinonimos is None:
                    destino.pop(valor, None)
                else:
                    destino[valor] = _lista(sinonimos)
            if not destino:
                vocabulario[atributo].pop(grupo)
        if atributo in vocabulario and not vocabulario[atributo]:
            vocabulario.pop(atributo)
    return resultado


def diferenca_de_atributos(base: dict, editado: dict) -> dict:
    """O que a OSC mudou em relação ao catálogo do sistema — é isso que fica gravado na camada.

    Assim, quando o catálogo do sistema ganha sinônimos numa versão nova do programa,
    a OSC recebe o que ela não mudou.
    """
    mudancas: dict = {}
    base_cat, ed_cat = base.get("categorias") or {}, editado.get("categorias") or {}
    categorias = {c: list(a) for c, a in ed_cat.items() if c not in base_cat or list(base_cat[c]) != list(a)}
    categorias.update({c: None for c in base_cat if c not in ed_cat})
    if categorias:
        mudancas["categorias"] = categorias
    bv, ev = base.get("vocabulario") or {}, editado.get("vocabulario") or {}
    vocabulario: dict = {}
    for atributo in dict.fromkeys([*bv, *ev]):
        b_grupos, e_grupos = bv.get(atributo) or {}, ev.get(atributo) or {}
        for grupo in dict.fromkeys([*b_grupos, *e_grupos]):
            b, e = b_grupos.get(grupo), e_grupos.get(grupo)
            if not e:
                if b:
                    vocabulario.setdefault(atributo, {})[grupo] = None
                continue
            valores = {}
            for valor in dict.fromkeys([*(b or {}), *e]):
                if valor not in e:
                    valores[valor] = None
                elif valor not in (b or {}) or _lista(b[valor]) != _lista(e[valor]):
                    valores[valor] = _lista(e[valor])
            if valores:
                vocabulario.setdefault(atributo, {})[grupo] = valores
    if vocabulario:
        mudancas["vocabulario"] = vocabulario
    return mudancas


def mesclar_lojas(base: dict, mudancas: dict | None) -> dict:
    """Lojas da OSC trocam (pelo id) ou acrescentam entradas do catálogo do sistema."""
    resultado = copy.deepcopy(base)
    for entrada in (mudancas or {}).get("lojas") or []:
        grupo = "fornecedores_servico" if entrada.get("tipo") == "fornecedor" else "lojas"
        for g in ("lojas", "fornecedores_servico"):
            resultado[g] = [e for e in resultado.get(g) or [] if e["id"] != entrada["id"]]
        resultado.setdefault(grupo, []).append({k: v for k, v in entrada.items() if k != "tipo"})
    return resultado


def diferenca_de_lojas(base: dict, editado: dict) -> dict:
    """Entradas novas ou mudadas pela OSC (as do sistema não são retiradas: basta não usá-las)."""
    def limpa(entrada: dict) -> dict:
        return {k: v for k, v in entrada.items() if k != "tipo" and v is not None and v != "" and v != []}

    originais = {e["id"]: (g, limpa(e)) for g in ("lojas", "fornecedores_servico") for e in base.get(g) or []}
    lojas = []
    for grupo in ("lojas", "fornecedores_servico"):
        for entrada in editado.get(grupo) or []:
            nova = limpa(entrada)
            if originais.get(nova.get("id")) != (grupo, nova):
                lojas.append({**nova, "tipo": "fornecedor" if grupo == "fornecedores_servico" else "loja"})
    return {"lojas": lojas} if lojas else {}


def validar_atributos(dados: dict) -> Vocabulario:
    """O catálogo mesclado precisa ser coerente: cada atributo tem leitor, vocabulário ou é conferido por pessoa."""
    try:
        vocabulario = Vocabulario.de_dados(dados)
    except (AttributeError, TypeError, KeyError) as e:
        raise ErroCatalogo(f"catálogo de atributos com formato inválido ({e})") from e
    conhecidos = set(LEITORES) | {g.atributo for g in vocabulario.grupos} | SO_POR_PESSOA
    problemas = [
        f"categoria “{categoria}”: atributo “{atributo}” desconhecido"
        for categoria, atributos in vocabulario.categorias.items()
        for atributo in atributos if atributo not in conhecidos
    ]
    for grupo in vocabulario.grupos:
        sinonimos = [s for lista in grupo.valores.values() for s in lista]
        repetidos = sorted({s for s in sinonimos if sinonimos.count(s) > 1})
        if repetidos:
            problemas.append(f"{grupo.atributo}/{grupo.nome}: sinônimo em mais de um valor: {', '.join(repetidos)}")
        if any(not s for s in sinonimos):
            problemas.append(f"{grupo.atributo}/{grupo.nome}: sinônimo vazio")
    if problemas:
        raise ErroCatalogo("; ".join(problemas))
    return vocabulario


def _problemas_da_busca(loja: dict) -> list[str]:
    """A busca automática da loja (D-68), se configurada, precisa de endereço válido."""
    busca = loja.get("busca")
    if busca is None:
        return []
    nome = loja.get("nome") or loja.get("id") or "?"
    if not isinstance(busca, dict) or busca.get("modo") not in ("api_vtex", "pagina", "assistida"):
        return [f"{nome}: o modo da busca deve ser api_vtex, pagina ou assistida"]
    url = str(busca.get("url") or "")
    problemas = []
    if not url.startswith("https://"):
        problemas.append(f"{nome}: o endereço da busca deve começar com https://")
    if busca["modo"] != "api_vtex" and "{termo}" not in url:
        problemas.append(f"{nome}: o endereço da busca precisa ter {{termo}} no lugar do que se pesquisa")
    if busca["modo"] == "pagina" and not str(busca.get("produto") or "").strip():
        problemas.append(f"{nome}: diga que pedaço aparece nos endereços de produto (ex.: /produto/)")
    return problemas


def validar_lojas(dados: dict) -> dict[str, LojaCatalogo]:
    problemas = []
    ids = []
    for grupo in ("lojas", "fornecedores_servico"):
        for e in dados.get(grupo) or []:
            for campo in ("id", "nome", "dominio", "coleta"):
                if not str(e.get(campo) or "").strip():
                    problemas.append(f"loja {e.get('id') or '?'}: falta “{campo}”")
            if e.get("coleta") and e["coleta"] not in COLETAS:
                problemas.append(f"loja {e.get('id')}: coleta deve ser uma destas: {', '.join(COLETAS)}")
            problemas += _problemas_da_busca(e)
            ids.append(e.get("id"))
    repetidos = sorted({i for i in ids if ids.count(i) > 1 and i})
    if repetidos:
        problemas.append("ids repetidos: " + ", ".join(repetidos))
    if problemas:
        raise ErroCatalogo("; ".join(problemas))
    return catalogo_de_dados(dados)


# --- Camadas gravadas ------------------------------------------------------------------------------


def camada_vigente(sessao: Session, organizacao_id: str, tipo: str) -> CatalogoCamada | None:
    return sessao.scalars(
        select(CatalogoCamada)
        .where(CatalogoCamada.organizacao_id == organizacao_id, CatalogoCamada.tipo == tipo)
        .order_by(CatalogoCamada.versao.desc())
    ).first()


def atributos_da_organizacao(sessao: Session, organizacao_id: str | None) -> dict:
    camada = camada_vigente(sessao, organizacao_id, "atributos") if organizacao_id else None
    return mesclar_atributos(ler_atributos_dados(), camada.conteudo if camada else None)


def vocabulario_da_organizacao(sessao: Session, organizacao_id: str | None) -> Vocabulario:
    return Vocabulario.de_dados(atributos_da_organizacao(sessao, organizacao_id))


def lojas_da_organizacao(sessao: Session, organizacao_id: str | None) -> dict:
    camada = camada_vigente(sessao, organizacao_id, "lojas") if organizacao_id else None
    return mesclar_lojas(ler_catalogo_dados(), camada.conteudo if camada else None)


def catalogo_da_organizacao(sessao: Session, organizacao_id: str | None) -> dict[str, LojaCatalogo]:
    return catalogo_de_dados(lojas_da_organizacao(sessao, organizacao_id))


def _gravar(sessao: Session, organizacao_id: str, tipo: str, conteudo: dict, resumo: str | None) -> CatalogoCamada:
    atual = camada_vigente(sessao, organizacao_id, tipo)
    if atual is not None and atual.impressao == _impressao(conteudo):
        return atual  # nada mudou
    camada = CatalogoCamada(organizacao_id=organizacao_id, tipo=tipo, versao=(atual.versao + 1 if atual else 1),
                            conteudo=conteudo, impressao=_impressao(conteudo), resumo=resumo,
                            autor=sessao.info["autor"])
    sessao.add(camada)
    return camada


# --- Pares da OSC e avaliação ------------------------------------------------------------------------


def par_de(r: ParReferencia) -> Par:
    return Par(r.titulo_a, r.titulo_b, r.rotulo, r.categoria, r.marca_a, r.marca_b, r.ean_a, r.ean_b, r.origem, r.id)


def pares_da_organizacao(sessao: Session, organizacao_id: str) -> list[Par]:
    registros = sessao.scalars(select(ParReferencia).where(
        ParReferencia.organizacao_id == organizacao_id, ParReferencia.excluido_em.is_(None)).order_by(ParReferencia.criado_em))
    return [par_de(r) for r in registros]


@dataclass(frozen=True)
class ResultadoDaMudanca:
    antes: Avaliacao
    depois: Avaliacao

    @property
    def novos_falsos_verdes(self) -> tuple[Par, ...]:
        """Pares diferentes que só viram 🟢 com a mudança. Os que já erravam antes não bloqueiam."""
        ja_erravam = {p.id for p in self.antes.falsos_verdes}
        return tuple(p for p in self.depois.falsos_verdes if p.id not in ja_erravam)

    @property
    def aprovada(self) -> bool:
        return not self.novos_falsos_verdes


def avaliar_mudanca_de_atributos(sessao: Session, organizacao_id: str, mudancas: dict) -> ResultadoDaMudanca:
    """Roda o teste de correspondência com o catálogo atual e com o catálogo mudado."""
    novo = validar_atributos(mesclar_atributos(ler_atributos_dados(), mudancas))
    pares = pares_do_sistema() + pares_da_organizacao(sessao, organizacao_id)
    return ResultadoDaMudanca(avaliar(pares, vocabulario_da_organizacao(sessao, organizacao_id)), avaliar(pares, novo))


def salvar_atributos(sessao: Session, organizacao_id: str, mudancas: dict, resumo: str | None = None) -> CatalogoCamada:
    """Grava as mudanças da OSC no catálogo de atributos, só se não criarem nenhum 🟢 errado (D-65)."""
    resultado = avaliar_mudanca_de_atributos(sessao, organizacao_id, mudancas)
    if not resultado.aprovada:
        novos = resultado.novos_falsos_verdes
        exemplos = "; ".join(f"“{p.titulo_a}” × “{p.titulo_b}”" for p in novos[:5])
        raise ErroCatalogo(f"A mudança faria {len(novos)} par(es) de produtos diferentes virarem 🟢: {exemplos}")
    return _gravar(sessao, organizacao_id, "atributos", mudancas, resumo)


def salvar_lojas(sessao: Session, organizacao_id: str, mudancas: dict, resumo: str | None = None) -> CatalogoCamada:
    validar_lojas(mesclar_lojas(ler_catalogo_dados(), mudancas))
    return _gravar(sessao, organizacao_id, "lojas", mudancas, resumo)


def _organizacao_do_item(item: Item) -> str:
    return item.lote.orcamento.projeto.organizacao_id


def par_da_decisao(sessao: Session, correspondencia: Correspondencia) -> ParReferencia | None:
    """A decisão de uma pessoa vira um par rotulado (D-64): confirmar = mesmo; recusar = diferente."""
    if correspondencia.origem != "humano" or correspondencia.status == "amarelo":
        return None
    item, obs = correspondencia.item, correspondencia.observacao
    chave = f"decisao:{item.id}:{obs.id}"
    existente = sessao.scalars(select(ParReferencia).where(ParReferencia.chave == chave)).first()
    rotulo = "mesmo" if correspondencia.status == "verde" else "diferente"
    if existente is not None:
        if existente.rotulo == rotulo:
            return existente  # mesma decisão (se a OSC tinha retirado o par, ele continua retirado)
        existente.excluido_em = existente.excluido_em or agora()  # a decisão mudou: o par antigo sai
        existente.chave = None
        sessao.flush()  # libera a chave para o par novo
    especificacao = " ".join(p for p in (item.descricao, item.modelo, item.apresentacao) if p)
    par = ParReferencia(
        organizacao_id=_organizacao_do_item(item), categoria=item.categoria,
        titulo_a=especificacao, marca_a=item.marca, ean_a=item.ean,
        titulo_b=obs.titulo or obs.url, marca_b=obs.marca, ean_b=obs.ean, rotulo=rotulo,
        motivo=(correspondencia.motivos or [None])[0], origem="decisao", chave=chave,
    )
    sessao.add(par)
    return par


def sincronizar_pares_de_ean(sessao: Session, organizacao_id: str) -> list[ParReferencia]:
    """Páginas de lojas diferentes com o mesmo código de barras = o mesmo produto (D-64), sem precisar de rótulo."""
    consulta = (
        select(Observacao, Item)
        .join(Item, Observacao.item_id == Item.id)
        .join(Lote, Item.lote_id == Lote.id)
        .join(Orcamento, Lote.orcamento_id == Orcamento.id)
        .join(Projeto, Orcamento.projeto_id == Projeto.id)
        .where(Projeto.organizacao_id == organizacao_id, Observacao.ean.is_not(None), Observacao.titulo.is_not(None))
        .order_by(Observacao.coletado_em, Observacao.id)
    )
    por_ean: dict[str, list[tuple[Observacao, Item]]] = {}
    for obs, item in sessao.execute(consulta):
        grupo = por_ean.setdefault(obs.ean.zfill(14), [])
        if all(o.fonte_id != obs.fonte_id for o, _ in grupo):  # uma página por loja
            grupo.append((obs, item))
    # cada página entra em um par só; pares retirados pela OSC continuam contando (não voltam)
    chaves = sessao.scalars(select(ParReferencia.chave).where(
        ParReferencia.organizacao_id == organizacao_id, ParReferencia.chave.like("ean:%")))
    usadas = {parte for chave in chaves for parte in chave.split(":")[1:]}
    novos = []
    for grupo in por_ean.values():
        for b, _ in grupo:
            if b.id in usadas or len(grupo) < 2:
                continue
            a, item = next((o, i) for o, i in grupo if o.id != b.id)  # a página mais antiga das outras lojas
            chave = f"ean:{a.id}:{b.id}"
            usadas |= {a.id, b.id}
            par = ParReferencia(organizacao_id=organizacao_id, categoria=item.categoria, titulo_a=a.titulo,
                                marca_a=a.marca, ean_a=a.ean, titulo_b=b.titulo, marca_b=b.marca, ean_b=b.ean,
                                rotulo="mesmo", motivo="mesmo código de barras em lojas diferentes", origem="ean",
                                chave=chave)
            sessao.add(par)
            novos.append(par)
    return novos


def adicionar_par(sessao: Session, organizacao_id: str, titulo_a: str, titulo_b: str, rotulo: str,
                  categoria: str | None = None, marca_a: str | None = None, marca_b: str | None = None,
                  motivo: str | None = None) -> ParReferencia:
    """Par escrito à mão pela OSC (ex.: dois anúncios que o sistema confunde)."""
    if rotulo not in ("mesmo", "diferente"):
        raise ErroCatalogo("o rótulo deve ser “mesmo” ou “diferente”")
    if not titulo_a.strip() or not titulo_b.strip():
        raise ErroCatalogo("escreva os dois produtos")
    par = ParReferencia(organizacao_id=organizacao_id, categoria=categoria or None, titulo_a=titulo_a.strip(),
                        marca_a=marca_a or None, titulo_b=titulo_b.strip(), marca_b=marca_b or None, rotulo=rotulo,
                        motivo=motivo or None, origem="usuario")
    sessao.add(par)
    return par


def retirar_par(sessao: Session, par: ParReferencia) -> None:
    """Retira o par do teste (continua no banco). Pares automáticos retirados não voltam (a chave fica)."""
    if par.excluido_em is None:
        par.excluido_em = agora()
