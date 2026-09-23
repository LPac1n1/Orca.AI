"""Dossiê do caso real (teto R$ 150.000,00) para os testes dos documentos.

Materiais: grade real (seleção regra B, loja de menor total por lote). Mão de obra: plano
real com a jornada legal. A otimização fecha o teto. As vagas e as evidências são
sintéticas (as empresas das vagas não constam do caso real): servem só para os documentos.
"""

import io
from datetime import UTC, date, datetime
from pathlib import Path

import yaml
from pypdf import PdfWriter

from orca.calculo import calcular_mao_de_obra, centavos_de_texto, centesimos_de_horas
from orca.documentos import (
    ArquivoRef,
    Dossie,
    Empresa,
    EventoDoc,
    EvidenciaDoc,
    OrcamentoDoc,
    ProjetoDoc,
    VagaDoc,
    cargo_doc,
    lote_doc,
    otimizacao_doc,
)
from orca.dominio import normalizar_cnpj
from orca.evidencias import ArmazemArquivos
from orca.otimizacao import ProblemaTeto, fechar_teto, linha_de_cargo, linhas_do_lote
from orca.regras import camada_padrao, resolver
from orca.selecao import ItemLote, Loja, Oferta, ParametrosSelecao, analisar_lote

DADOS = Path(__file__).parents[1] / "dados" / "casos"
GRADE = yaml.safe_load((DADOS / "grade_real_2026.yaml").read_text(encoding="utf-8"))
PLANO = yaml.safe_load((DADOS / "plano_real_2026.yaml").read_text(encoding="utf-8"))
PERFIL = resolver([camada_padrao()])
REGRAS = PERFIL.regras
COLETA = datetime(2026, 9, 23, 14, 0, tzinfo=UTC)
GERADO = datetime(2026, 9, 24, 13, 30, tzinfo=UTC)
TIPO_DA_RUBRICA = {"Sistema de gestão de dados": "servicos"}


def pdf_sintetico(titulo: str) -> bytes:
    escritor = PdfWriter()
    escritor.add_blank_page(width=595, height=842)
    escritor.add_metadata({"/Title": titulo})
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


def cnpj_de_teste(n: int) -> str:
    """CNPJ com dígitos verificadores válidos, só para os testes."""
    base = f"{n:08d}0001"
    for dv in range(100):
        try:
            return normalizar_cnpj(f"{base}{dv:02d}")
        except ValueError:
            continue
    raise AssertionError


def _evidencia(armazem: ArmazemArquivos | None, rotulo: str, url: str) -> EvidenciaDoc | None:
    if armazem is None:
        return None
    arquivos = []
    for tipo, mime, conteudo in (
        ("pdf", "application/pdf", pdf_sintetico(rotulo)),
        ("png", "image/png", b"\x89PNG\r\n" + rotulo.encode()),
        ("mhtml", "multipart/related", f"MIME-Version: 1.0\r\n{rotulo}".encode()),
    ):
        guardado = armazem.guardar(conteudo, mime)
        arquivos.append(ArquivoRef(guardado.caminho, guardado.sha256, tipo))
    return EvidenciaDoc(url, COLETA, "C1", tuple(arquivos))


def montar(armazem: ArmazemArquivos | None = None, otimizar: bool = True) -> tuple[Dossie, ProblemaTeto]:
    empresas = {
        normalizar_cnpj(d["cnpj"]): Empresa(d["nome"], normalizar_cnpj(d["cnpj"]), "ATIVA", COLETA)
        for d in GRADE["lojas"].values()
    }
    kalunga = normalizar_cnpj(GRADE["lojas"]["kalunga"]["cnpj"])
    if armazem is not None:  # um comprovante da Receita emitido
        g = armazem.guardar(pdf_sintetico("comprovante Kalunga"), "application/pdf")
        empresas[kalunga] = Empresa(empresas[kalunga].nome, kalunga, "ATIVA", COLETA, ArquivoRef(g.caminho, g.sha256, "pdf"))

    analises, linhas, restricoes = [], [], []
    for n, lote in enumerate(GRADE["lotes"]):
        meses = PLANO["meses_por_lote"][lote["nome"]]
        itens = [ItemLote(f"l{n}i{k}", i["nome"], i["qtd"], meses) for k, i in enumerate(lote["itens"])]
        lojas = [
            Loja(chave, GRADE["lojas"][chave]["nome"], normalizar_cnpj(GRADE["lojas"][chave]["cnpj"]),
                 {it.id: Oferta(centavos_de_texto(b["precos"][pos])) for it, b in zip(itens, lote["itens"])})
            for pos, chave in enumerate(lote["lojas"])
        ]
        analise = analisar_lote(itens, lojas, ParametrosSelecao.de_regras(REGRAS))
        novas, restricao = linhas_do_lote(analise, REGRAS, orcamento=lote["rubrica"], lote=lote["nome"])
        linhas += novas
        restricoes.append(restricao)
        analises.append((lote, analise))

    calculos = []
    for n, c in enumerate(PLANO["cargos"]):
        calculo = calcular_mao_de_obra([centavos_de_texto(s) for s in c["salarios"]], c["jornada_legal"],
                                       centesimos_de_horas(c["horas"]), c["meses"], c["postos"])
        calculos.append((f"c{n}", c, calculo))
    problema = ProblemaTeto(
        centavos_de_texto(PLANO["teto"]),
        materiais=tuple(linhas),
        mao_de_obra=tuple(linha_de_cargo(i, c["nome"], "Recursos Humanos", calc, REGRAS) for i, c, calc in calculos),
        lotes=tuple(restricoes),
    )
    solucao = fechar_teto(problema, tempo_limite_s=60) if otimizar else None

    orcamentos: dict[str, list] = {}
    for lote, analise in analises:
        evidencias = {
            (loja.loja.id, linha.item.id): _evidencia(armazem, f"{loja.loja.nome} {linha.item.nome}",
                                                       f"https://loja.exemplo/{loja.loja.id}/{linha.item.id}")
            for loja in analise.trio for linha in analise.linhas
        } if armazem else None
        doc = lote_doc(analise, lote["nome"], quantidades=solucao.quantidades if solucao else None,
                       empresas=empresas, evidencias=evidencias)
        orcamentos.setdefault(lote["rubrica"], []).append(doc)

    cargos = []
    for i, c, calculo in calculos:
        vagas = []
        for k, salario in enumerate(calculo.salarios):
            cnpj = cnpj_de_teste(900 + 10 * int(i[1:]) + k)
            vagas.append(VagaDoc(Empresa(f"Empresa de teste {i}-{k + 1}", cnpj), salario, f"{c['nome']} (vaga {k + 1})",
                                 "catho", _evidencia(armazem, f"vaga {i} {k}", f"https://vagas.exemplo/{i}/{k}")))
        horas = solucao.horas_centesimos[i] if solucao else None
        cargos.append(cargo_doc(i, c["nome"], "recibo", calculo, vagas, horas_finais_centesimos=horas))

    docs = tuple(OrcamentoDoc(nome, TIPO_DA_RUBRICA.get(nome, "materiais"), lotes=tuple(lotes))
                 for nome, lotes in orcamentos.items())
    docs += (OrcamentoDoc("Recursos Humanos", "mao_de_obra", cargos=tuple(cargos)),)
    projeto = ProjetoDoc(
        nome="Projeto de teste — caso real 2026",
        organizacao=Empresa("OSC de teste", cnpj_de_teste(123)),
        teto_centavos=problema.teto_centavos,
        duracao_meses=12,
        orgao="Secretaria de teste",
        instrumento="Termo de fomento",
        data_entrega=date(2026, 10, 30),
        impressao_regras=PERFIL.impressao,
        versao_sistema="0.1.0",
        gerado_em=GERADO,
    )
    eventos = (EventoDoc(COLETA, "projeto", "p1", "criar", "usuario:Leonardo"),)
    return Dossie(projeto, docs, otimizacao_doc(problema, solucao), empresas, eventos), problema
