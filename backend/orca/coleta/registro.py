"""Gravação da coleta no banco: arquivos, evidência, fonte, observação, consulta de CNPJ e comprovante.

Uma observação guarda o que foi visto, como foi visto — nunca é alterada (princípio 5).
O preço só é marcado como conferido se aparecer no texto visível da página, e nenhum
dado que não esteja na página é inventado (princípio 1): o que falta vira aviso.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from orca.banco import Arquivo, Cargo, Comprovante, ConsultaCnpj, Evidencia, Fonte, Item, Observacao, agora
from orca.calculo import formatar
from orca.coleta.captura import Captura
from orca.coleta.catalogo import LojaCatalogo, dominio_da_url
from orca.coleta.cnpj import DadosCnpj, consultar_cnpj
from orca.coleta.extracao import (
    cnpjs_no_texto,
    extrair_produto,
    extrair_vaga,
    imagem_da_pagina,
    preco_a_vista,
    preco_aparece,
    precos_perto,
    precos_rotulados,
    precos_visiveis,
)
from orca.dominio import normalizar_cnpj
from orca.evidencias import ArmazemArquivos

SEM_VALIDACAO = "Não foi possível validar automaticamente"
# a página diz que o produto está em falta (sem preço): não adianta abrir na janela
_EM_FALTA = re.compile(r"\b(indispon[ií]vel|esgotado|fora de estoque|sem estoque|avise-me quando chegar)\b", re.I)
FORMAS = {"pix": "no Pix", "boleto": "no boleto", "pix_ou_boleto": "no Pix ou boleto", "parcelado": "parcelado"}
CEP_REGIONAL = ("regiao_por_cep", "pede_cep")


class CapturaPaginas(Protocol):
    def capturar(self, url: str, cep: str | None = None) -> Captura: ...


@dataclass(frozen=True)
class ResultadoColeta:
    observacao: Observacao
    avisos: tuple[str, ...]


# --- Arquivos, evidência e fonte ------------------------------------------------


def _pendente(sessao: Session, classe, condicao):
    """Registro já criado nesta sessão, mas ainda não gravado."""
    return next((o for o in sessao.new if isinstance(o, classe) and condicao(o)), None)


def _arquivo(sessao: Session, armazem: ArmazemArquivos, conteudo: bytes, tipo: str) -> Arquivo:
    guardado = armazem.guardar(conteudo, tipo)
    existente = sessao.get(Arquivo, guardado.sha256) or _pendente(
        sessao, Arquivo, lambda a: a.sha256 == guardado.sha256
    )
    if existente is not None:
        return existente
    arquivo = Arquivo(sha256=guardado.sha256, caminho=guardado.caminho, tipo_mime=tipo, tamanho=guardado.tamanho)
    sessao.add(arquivo)
    return arquivo


def registrar_captura(sessao: Session, armazem: ArmazemArquivos, captura: Captura) -> Evidencia:
    """Guarda PDF, imagem e página salva (MHTML) e cria a evidência."""
    evidencia = Evidencia(
        url=captura.url_final,
        capturado_em=captura.capturado_em,
        metodo=captura.metodo,
        cep=captura.cep,
        pdf=_arquivo(sessao, armazem, captura.pdf, "application/pdf"),
        png=_arquivo(sessao, armazem, captura.png, "image/png"),
        html=_arquivo(sessao, armazem, captura.mhtml, "multipart/related"),
    )
    sessao.add(evidencia)
    return evidencia


def fonte_da_url(
    sessao: Session, url: str, tipo: str = "loja", catalogo: Mapping[str, LojaCatalogo] | None = None
) -> Fonte:
    """A fonte pelo domínio da página (com o nome do catálogo, se conhecida); cria se ainda não existir.

    Para vagas (`tipo="empresa"`), a fonte é o site onde a vaga foi publicada; a empresa
    é identificada pelo CNPJ na observação.
    """
    dominio = dominio_da_url(url)
    entrada = (catalogo or {}).get(dominio)
    if entrada is not None and tipo == "loja":
        tipo = entrada.tipo
    fonte = sessao.scalars(select(Fonte).where(Fonte.dominio == dominio, Fonte.tipo == tipo)).first()
    fonte = fonte or _pendente(sessao, Fonte, lambda f: f.dominio == dominio and f.tipo == tipo)
    if fonte is None:
        fonte = Fonte(
            tipo=tipo,
            nome=entrada.nome if entrada else dominio,
            dominio=dominio,
            catalogo_id=entrada.id if entrada else None,
        )
        sessao.add(fonte)
    return fonte


def _cnpj_identificado(informado: str | None, na_pagina: list[str], marketplace: bool) -> tuple[str | None, str | None]:
    """CNPJ do vendedor/empresa e, se não der para identificar, o aviso."""
    if informado:
        return normalizar_cnpj(informado), None
    if marketplace:  # o CNPJ do rodapé é da plataforma, não do vendedor (D-16)
        return None, "marketplace: informe o CNPJ do vendedor (está na página do vendedor); sem ele o anúncio é descartado (T-12)"
    if len(na_pagina) == 1:
        return na_pagina[0], None
    if not na_pagina:
        return None, "CNPJ não encontrado na página; informe o CNPJ"
    return None, f"a página mostra {len(na_pagina)} CNPJs; indique qual é o do vendedor"


# --- Observações ------------------------------------------------------------------


def registrar_observacao_item(
    sessao: Session,
    item: Item,
    captura: Captura,
    evidencia: Evidencia,
    *,
    preco_informado: int | None = None,
    cnpj_vendedor: str | None = None,
    catalogo: Mapping[str, LojaCatalogo] | None = None,
    avisos_extras: tuple[str, ...] = (),
    preco_no_pix: bool = True,
    preco_da_busca: int | None = None,
) -> ResultadoColeta:
    """Observação de um produto. O preço informado pelo usuário (captura assistida) também é conferido na página.

    D-60 (revisada em 24/09/2026): com `preco_no_pix`, vale o preço no Pix; sem Pix, o do boleto; nunca o
    parcelado. O valor escolhido é um dos escritos na página, perto do preço dos dados estruturados.
    """
    entrada = (catalogo or {}).get(dominio_da_url(captura.url_final))
    extraido = extrair_produto("\n".join([captura.html, *captura.html_quadros]))
    lido = extraido.preco_centavos if extraido else None
    lido_na_pagina = lido is not None and preco_aparece(lido, captura.texto_visivel)
    rotulados = precos_rotulados(lido, captura.texto_visivel) if lido_na_pagina else []
    escolher = preco_no_pix and preco_informado is None and lido_na_pagina
    escolha = preco_a_vista(lido, captura.texto_visivel) if escolher else None
    preco = preco_informado if preco_informado is not None else (escolha.centavos if escolha else lido)
    # A página não traz o preço nos dados (ex.: WooCommerce, produto com variações): vale o preço que a busca
    # da loja mostrou, só se ele estiver escrito na página capturada (princípio 5: o preço é o da prova).
    da_busca = (preco is None and preco_da_busca is not None and preco_da_busca > 0
                and preco_aparece(preco_da_busca, captura.texto_visivel))
    if da_busca:
        preco = preco_da_busca
    conferido = preco_aparece(preco, captura.texto_visivel) if preco is not None else None
    cnpjs_pagina = cnpjs_no_texto(captura.texto_visivel)
    cnpj, aviso_cnpj = _cnpj_identificado(cnpj_vendedor, cnpjs_pagina, bool(entrada and entrada.marketplace))
    distintos = sorted(set(precos_visiveis(captura.texto_visivel)))

    avisos = list(avisos_extras)
    if da_busca:
        avisos.append(f"a página não traz o preço nos dados; {formatar(preco)} foi mostrado pela busca da loja "
                      "e está escrito na página")
    if escolha is not None and escolha.centavos != lido:
        avisos.append(f"preço {FORMAS[escolha.forma]} (D-60): {formatar(escolha.centavos)}; "
                      f"o preço cheio da página é {formatar(lido)}")
    elif escolher and escolha is None and any(r.forma == "parcelado" and r.distancia == 0 for r in rotulados):
        avisos.append(f"{SEM_VALIDACAO}: o preço {formatar(lido)} parece ser o parcelado; "
                      "informe o preço no Pix ou no boleto (D-60)")
    if captura.bloqueio:
        avisos.append(f"possível bloqueio de acesso automático: {captura.bloqueio}; use a captura assistida")
    em_falta = preco is None and _EM_FALTA.search(captura.texto_visivel or "") is not None
    if em_falta:
        avisos.append("o produto está indisponível (em falta) nesta loja")
    elif preco is None:
        avisos.append(f"{SEM_VALIDACAO}: preço não encontrado na página; informe o preço que aparece nela")
    elif not conferido:
        avisos.append(f"{SEM_VALIDACAO}: o preço {formatar(preco)} não aparece no texto visível da página")
    if extraido:
        avisos += extraido.avisos
        if extraido.moeda and extraido.moeda.upper() != "BRL":
            avisos.append(f"preço em outra moeda: {extraido.moeda}")
        if extraido.disponivel is False:
            avisos.append("produto indisponível na página")
    explicados = ({lido} | {r.centavos for r in rotulados if r.forma}) if escolha is not None else set()
    vizinhos = [v for v in precos_perto(preco, captura.texto_visivel) if v not in explicados] if conferido else []
    if vizinhos:
        regra = f" (nesta loja: {entrada.preco_a_usar})" if entrada and entrada.preco_a_usar else ""
        valores = ", ".join(formatar(v) for v in vizinhos[:5])
        avisos.append(
            f"perto do preço aparecem outros valores ({valores}); confira se {formatar(preco)} é o preço certo"
            f"{regra}: no Pix ou no boleto, nunca parcelado; sem clube ou assinatura; preço unitário (D-60 a D-63)"
        )
    if entrada and entrada.cep in CEP_REGIONAL and captura.cep is None:
        avisos.append("o preço desta loja depende do CEP e a página foi capturada sem CEP aplicado")
    if aviso_cnpj:
        avisos.append(aviso_cnpj)

    observacao = Observacao(
        alvo_tipo="item",
        item=item,
        fonte=fonte_da_url(sessao, captura.url_final, catalogo=catalogo),
        cnpj_vendedor=cnpj,
        url=captura.url_final,
        titulo=(extraido.titulo if extraido else None) or captura.titulo or None,
        marca=extraido.marca if extraido else None,
        ean=extraido.ean if extraido else None,
        preco_centavos=preco,
        encontrado=preco is not None,
        disponivel=False if em_falta else (extraido.disponivel if extraido else None),
        coletado_em=captura.capturado_em,
        cep=captura.cep,
        metodo=captura.metodo,
        evidencia=evidencia,
        preco_no_html=conferido,
        dados_brutos=_json({
            "extraido": asdict(extraido) if extraido else None,
            "preco_informado": preco_informado,
            "preco_da_busca": preco_da_busca,
            "preco_lido": lido,
            "escolha_d60": {"forma": escolha.forma, "trecho": escolha.trecho} if escolha else None,
            "precos_rotulados": [{"centavos": r.centavos, "forma": r.forma} for r in rotulados],
            "precos_visiveis": distintos[:60],
            "precos_perto": vizinhos,
            "cnpjs_na_pagina": cnpjs_pagina,
            "imagem": imagem_da_pagina("\n".join([captura.html, *captura.html_quadros]), captura.url_final),  # D-73
            "avisos": avisos,
        }),
        autor=sessao.info["autor"],
    )
    sessao.add(observacao)
    return ResultadoColeta(observacao, tuple(avisos))


def registrar_observacao_cargo(
    sessao: Session,
    cargo: Cargo,
    captura: Captura,
    evidencia: Evidencia,
    *,
    cnpj_empresa: str | None = None,
    salario_min_informado: int | None = None,
    salario_max_informado: int | None = None,
    avisos_extras: tuple[str, ...] = (),
) -> ResultadoColeta:
    """Observação de uma vaga (salário, empresa, local), com os dados da página ou informados pelo usuário."""
    vaga = extrair_vaga("\n".join([captura.html, *captura.html_quadros]))
    informado = salario_min_informado is not None or salario_max_informado is not None
    salario_min = salario_min_informado if informado else (vaga.salario_min_centavos if vaga else None)
    salario_max = salario_max_informado if informado else (vaga.salario_max_centavos if vaga else None)
    referencia = salario_min if salario_min is not None else salario_max  # faixa → menor valor (D-46)
    conferido = preco_aparece(referencia, captura.texto_visivel) if referencia is not None else None
    cnpjs_pagina = cnpjs_no_texto(captura.texto_visivel)
    cnpj, _ = _cnpj_identificado(cnpj_empresa, cnpjs_pagina, marketplace=False)

    avisos = list(avisos_extras)
    if captura.bloqueio:
        avisos.append(f"possível bloqueio de acesso automático: {captura.bloqueio}; use a captura assistida")
    if referencia is None:
        avisos.append("vaga sem salário informado: será descartada (D-46)")
    elif not conferido:
        avisos.append(f"{SEM_VALIDACAO}: o salário {formatar(referencia)} não aparece no texto visível da página")
    if cnpj is None:
        avisos.append("empresa não identificada pelo CNPJ: informe o CNPJ ou a vaga será descartada (D-46)")
    if vaga:
        avisos += vaga.avisos

    observacao = Observacao(
        alvo_tipo="cargo",
        cargo=cargo,
        fonte=fonte_da_url(sessao, captura.url_final, tipo="empresa"),
        cnpj_vendedor=cnpj,
        url=captura.url_final,
        titulo=(vaga.titulo if vaga else None) or captura.titulo or None,
        salario_min_centavos=salario_min,
        salario_max_centavos=salario_max,
        encontrado=referencia is not None,
        coletado_em=captura.capturado_em,
        cep=captura.cep,
        metodo=captura.metodo,
        evidencia=evidencia,
        preco_no_html=conferido,
        dados_brutos=_json({
            "extraido": asdict(vaga) if vaga else None,
            "salario_informado": [salario_min_informado, salario_max_informado] if informado else None,
            "cnpjs_na_pagina": cnpjs_pagina,
            "avisos": avisos,
        }),
        autor=sessao.info["autor"],
    )
    sessao.add(observacao)
    return ResultadoColeta(observacao, tuple(avisos))


# --- Coleta completa por URL (C1) e nova pesquisa ---------------------------------


def coletar_item(
    sessao: Session,
    armazem: ArmazemArquivos,
    navegador: CapturaPaginas,
    item: Item,
    url: str,
    *,
    cep_aplicado: str | None = None,
    cnpj_vendedor: str | None = None,
    catalogo: Mapping[str, LojaCatalogo] | None = None,
) -> ResultadoColeta:
    """Captura a página do produto e registra evidência e observação.

    `cep_aplicado` só é informado quando o CEP foi de fato aplicado no site (o PDF o mostra).
    """
    captura = navegador.capturar(url, cep=cep_aplicado)
    evidencia = registrar_captura(sessao, armazem, captura)
    return registrar_observacao_item(
        sessao, item, captura, evidencia, cnpj_vendedor=cnpj_vendedor, catalogo=catalogo
    )


def coletar_cargo(
    sessao: Session,
    armazem: ArmazemArquivos,
    navegador: CapturaPaginas,
    cargo: Cargo,
    url: str,
    *,
    cnpj_empresa: str | None = None,
) -> ResultadoColeta:
    captura = navegador.capturar(url)
    evidencia = registrar_captura(sessao, armazem, captura)
    return registrar_observacao_cargo(sessao, cargo, captura, evidencia, cnpj_empresa=cnpj_empresa)


def refazer_pesquisa(
    sessao: Session,
    armazem: ArmazemArquivos,
    navegador: CapturaPaginas,
    anterior: Observacao,
    catalogo: Mapping[str, LojaCatalogo] | None = None,
) -> ResultadoColeta:
    """Nova pesquisa da mesma página (ex.: vencida). A anterior fica no histórico, intacta."""
    if anterior.alvo_tipo == "item":
        return coletar_item(
            sessao, armazem, navegador, anterior.item, anterior.url,
            cep_aplicado=anterior.cep, cnpj_vendedor=anterior.cnpj_vendedor, catalogo=catalogo,
        )
    return coletar_cargo(sessao, armazem, navegador, anterior.cargo, anterior.url, cnpj_empresa=anterior.cnpj_vendedor)


def registrar_nao_encontrado(sessao: Session, item: Item, captura: Captura, evidencia: Evidencia, termo: str,
                             candidatos: list[str], catalogo: Mapping[str, LojaCatalogo] | None = None) -> Observacao:
    """A busca da loja não trouxe o item (docs/02 §6.3): fica registrado, com a página da busca como prova."""
    observacao = Observacao(
        alvo_tipo="item", item=item, fonte=fonte_da_url(sessao, captura.url_final, catalogo=catalogo),
        url=captura.url_final, titulo=None, preco_centavos=None, encontrado=False, coletado_em=captura.capturado_em,
        cep=captura.cep, metodo=captura.metodo, evidencia=evidencia, preco_no_html=None,
        dados_brutos=_json({"busca": termo, "candidatos": candidatos[:10],
                            "avisos": [f"não encontrado na busca da loja (termo: “{termo}”)"]}),
        autor=sessao.info["autor"],
    )
    sessao.add(observacao)
    return observacao


# --- Preço escolhido pelo usuário na mesma página -----------------------------------


def precos_da_pagina(observacao: Observacao) -> list[dict]:
    """Os valores lidos perto do preço do produto, com a forma de pagamento (para o usuário escolher)."""
    brutos = json.loads(observacao.dados_brutos or "{}")
    rotulados = brutos.get("precos_rotulados")
    if rotulados:
        vistos, lista = set(), []
        for r in rotulados:
            if r["centavos"] not in vistos:
                vistos.add(r["centavos"])
                lista.append({"centavos": r["centavos"], "forma": r.get("forma")})
        return lista
    valores = sorted({*(brutos.get("precos_perto") or []), *([observacao.preco_centavos] if observacao.preco_centavos else [])})
    return [{"centavos": v, "forma": None} for v in valores]


def _aparece_na_prova(armazem: ArmazemArquivos, observacao: Observacao, preco: int) -> bool:
    brutos = json.loads(observacao.dados_brutos or "{}")
    lidos = {*(brutos.get("precos_visiveis") or []), *(brutos.get("precos_perto") or []),
             *(r["centavos"] for r in brutos.get("precos_rotulados") or [])}
    if preco in lidos:
        return True
    if observacao.evidencia is None or observacao.evidencia.pdf is None:
        return False
    import io

    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        leitor = PdfReader(io.BytesIO(armazem.ler(observacao.evidencia.pdf.caminho)))
        texto = "\n".join(pagina.extract_text() or "" for pagina in leitor.pages)
    except (PdfReadError, ValueError, OSError):
        return False
    return preco_aparece(preco, texto)


def corrigir_preco(sessao: Session, armazem: ArmazemArquivos, anterior: Observacao, preco_centavos: int,
                   justificativa: str) -> Observacao:
    """O usuário escolhe outro valor escrito na mesma página (a mesma prova, sem acessar a loja de novo).

    A observação anterior não muda (princípio 5): nasce uma nova, que passa a valer, com o motivo.
    O valor precisa aparecer na página salva; senão é recusado (princípio 1).
    """
    if anterior.alvo_tipo != "item":
        raise ValueError("Só dá para corrigir o preço de um produto.")
    if not justificativa or not justificativa.strip():
        raise ValueError("Escreva o motivo da correção (fica no histórico).")
    if preco_centavos <= 0:
        raise ValueError("O preço precisa ser maior que zero.")
    if preco_centavos == anterior.preco_centavos:
        raise ValueError("Esse já é o preço usado.")
    if not _aparece_na_prova(armazem, anterior, preco_centavos):
        raise ValueError(f"{formatar(preco_centavos)} não aparece na página salva. Se o preço mudou, cole o link de novo.")
    brutos = json.loads(anterior.dados_brutos or "{}")
    brutos["avisos"] = [f"preço corrigido por uma pessoa: {formatar(preco_centavos)} no lugar de "
                        f"{formatar(anterior.preco_centavos)} (motivo: {justificativa.strip()})"]
    brutos["corrige_observacao"] = anterior.id
    nova = Observacao(
        alvo_tipo="item", item=anterior.item, fonte=anterior.fonte, cnpj_vendedor=anterior.cnpj_vendedor,
        url=anterior.url, titulo=anterior.titulo, marca=anterior.marca, modelo=anterior.modelo,
        apresentacao=anterior.apresentacao, ean=anterior.ean, preco_centavos=preco_centavos, encontrado=True,
        disponivel=anterior.disponivel, coletado_em=anterior.coletado_em, cep=anterior.cep, metodo=anterior.metodo,
        evidencia=anterior.evidencia, preco_no_html=True, dados_brutos=_json(brutos), autor=sessao.info["autor"],
    )
    sessao.add(nova)
    return nova


# --- CNPJ e comprovante -------------------------------------------------------------


def registrar_consulta_cnpj(sessao: Session, dados: DadosCnpj) -> ConsultaCnpj:
    """Guarda a consulta como estava no dia (imutável); só os campos necessários (LGPD)."""
    consulta = ConsultaCnpj(
        cnpj=dados.cnpj,
        razao_social=dados.razao_social,
        nome_fantasia=dados.nome_fantasia,
        situacao=dados.situacao,
        data_situacao=dados.data_situacao,
        municipio=dados.municipio,
        uf=dados.uf,
        provedor=dados.provedor,
        consultado_em=agora(),
        dados_brutos=_json(dados.resumo),
    )
    sessao.add(consulta)
    return consulta


def validar_cnpj(
    sessao: Session, cnpj: str, provedores: list[str], cliente: httpx.Client | None = None
) -> ConsultaCnpj:
    """Consulta a situação cadastral (APIs gratuitas) e guarda o resultado."""
    return registrar_consulta_cnpj(sessao, consultar_cnpj(cnpj, provedores, cliente))


def ultima_consulta(sessao: Session, cnpj: str) -> ConsultaCnpj | None:
    return sessao.scalars(
        select(ConsultaCnpj)
        .where(ConsultaCnpj.cnpj == normalizar_cnpj(cnpj))
        .order_by(ConsultaCnpj.consultado_em.desc())
    ).first()


def registrar_comprovante(sessao: Session, armazem: ArmazemArquivos, cnpj: str, captura: Captura) -> Comprovante:
    """Guarda o comprovante da Receita (PDF) capturado na captura assistida."""
    comprovante = Comprovante(
        cnpj=cnpj,
        arquivo=_arquivo(sessao, armazem, captura.pdf, "application/pdf"),
        emitido_em=captura.capturado_em,
    )
    sessao.add(comprovante)
    return comprovante


def registrar_comprovante_enviado(sessao: Session, armazem: ArmazemArquivos, cnpj: str, pdf: bytes,
                                  emitido_em) -> Comprovante:
    """Comprovante emitido pela pessoa no próprio navegador e enviado em PDF (já conferido)."""
    comprovante = Comprovante(cnpj=cnpj, arquivo=_arquivo(sessao, armazem, pdf, "application/pdf"), emitido_em=emitido_em)
    sessao.add(comprovante)
    return comprovante


def _json(dados) -> str:
    return json.dumps(dados, ensure_ascii=False, default=str)


# --- PDF salvo pelo usuário (último recurso, D-67) -------------------------------------------------


class ErroPdf(ValueError):
    pass


LIMITE_PDF = 20 * 1024 * 1024


def captura_de_pdf(pdf: bytes, url: str, momento, titulo: str | None = None) -> tuple[Captura, tuple[str, ...]]:
    """Lê o texto do PDF salvo pelo usuário e confere se o endereço e o nome do produto aparecem nele."""
    import io

    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    if len(pdf) > LIMITE_PDF:
        raise ErroPdf("O PDF passa de 20 MB.")
    try:
        leitor = PdfReader(io.BytesIO(pdf))
        texto = "\n".join(pagina.extract_text() or "" for pagina in leitor.pages)
    except (PdfReadError, ValueError, OSError) as e:
        raise ErroPdf("O arquivo não é um PDF válido.") from e
    avisos = ["PDF salvo e enviado pelo usuário (D-67): a data da prova é a do envio"]
    dominio = dominio_da_url(url)
    if dominio and dominio not in texto.lower().replace("www.", ""):
        avisos.append(f"o endereço ({dominio}) não aparece no PDF: imprima com cabeçalho e rodapé do navegador ligados")
    titulo = (titulo or "").strip()
    if titulo and " ".join(titulo.lower().split()) not in " ".join(texto.lower().split()):
        avisos.append(f"{SEM_VALIDACAO}: o nome do produto informado não aparece no texto do PDF")
    if not titulo and leitor.metadata and leitor.metadata.title:
        titulo = str(leitor.metadata.title)
    captura = Captura(url, url, momento, titulo, 200, "", (), texto, pdf, b"", b"", None, "C4", None)
    return captura, tuple(avisos)


def registrar_pdf_enviado(sessao: Session, armazem: ArmazemArquivos, captura: Captura) -> Evidencia:
    """Evidência só com o PDF (sem imagem nem página salva)."""
    evidencia = Evidencia(url=captura.url_final, capturado_em=captura.capturado_em, metodo="C4", cep=None,
                          pdf=_arquivo(sessao, armazem, captura.pdf, "application/pdf"))
    sessao.add(evidencia)
    return evidencia
