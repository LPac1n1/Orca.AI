"""Pacote completo (ZIP) do caso real, com PDFs gerados pelo Edge."""

import hashlib
import io
import json
import zipfile
from datetime import date

import pytest
from pypdf import PdfReader

from caso_documentos import montar
from orca.documentos import Renderizador, gerar_pacote, nome_de_arquivo, salvar_pacote
from orca.evidencias import ArmazemArquivos, ErroIntegridade

pytestmark = pytest.mark.navegador
HOJE = date(2026, 9, 24)


@pytest.fixture(scope="module")
def renderizador():
    try:
        with Renderizador() as r:
            yield r
    except Exception as e:  # noqa: BLE001 — sem Edge no computador
        pytest.skip(f"Microsoft Edge indisponível: {e}")


@pytest.fixture(scope="module")
def pacote(tmp_path_factory, renderizador):
    armazem = ArmazemArquivos(tmp_path_factory.mktemp("dados"))
    dossie, _ = montar(armazem)
    conteudo = gerar_pacote(dossie, armazem, renderizador, HOJE)
    return dossie, armazem, zipfile.ZipFile(io.BytesIO(conteudo)), conteudo


def _texto(zip_: zipfile.ZipFile, caminho: str) -> str:
    leitor = PdfReader(io.BytesIO(zip_.read(caminho)))
    return " ".join(" ".join(p.extract_text() for p in leitor.pages).split())


def test_estrutura_do_pacote(pacote):
    dossie, _, zip_, _ = pacote
    nomes = zip_.namelist()
    raiz = "Projeto_de_teste_caso_real_2026_2026-09-24/"
    assert all(n.startswith(raiz) for n in nomes)
    relativos = {n[len(raiz):] for n in nomes}
    for esperado in (
        "00_RESUMO/resumo.pdf", "00_RESUMO/conformidade.pdf", "00_RESUMO/pesquisa.pdf",
        "01_ORCAMENTOS/Material_Pedagogico_e_Escritorio/Orcamento_1.pdf",
        "01_ORCAMENTOS/Material_Pedagogico_e_Escritorio/Orcamento_3.pdf",
        "01_ORCAMENTOS/Material_Pedagogico_e_Escritorio/Orcamento_Final.pdf",
        "01_ORCAMENTOS/Material_Pedagogico_e_Escritorio/grade_comparativa.xlsx",
        "01_ORCAMENTOS/Material_Pedagogico_e_Escritorio/grade_comparativa.pdf",
        "01_ORCAMENTOS/Recursos_Humanos/Orcamento_Final.pdf",
        "02_COTACOES/Material_Pedagogico_e_Escritorio/01_Bloco_de_notas_4_Cores/cotacao.pdf",
        "02_COTACOES/Material_Pedagogico_e_Escritorio/01_Bloco_de_notas_4_Cores/fonte_1.pdf",
        "02_COTACOES/Material_Pedagogico_e_Escritorio/01_Bloco_de_notas_4_Cores/fonte_3.mhtml",
        "03_VAGAS/Coordenador_de_projetos/cotacao.pdf",
        "03_VAGAS/Coordenador_de_projetos/vaga_2.png",
        "04_CNPJ/43283811000150_Kalunga_SA.pdf",
        "05_PLANO/plano_aplicacao.xlsx",
        "06_MEMORIA_CALCULO/memoria_calculo.pdf", "06_MEMORIA_CALCULO/otimizacao.json",
        "07_AUDITORIA/historico.pdf", "07_AUDITORIA/historico.json", "07_AUDITORIA/manifesto.json",
    ):
        assert esperado in relativos, esperado
    itens = sum(len(l.linhas) for o in dossie.orcamentos for l in o.lotes)
    assert sum(1 for n in relativos if n.startswith("02_COTACOES/") and n.endswith("/cotacao.pdf")) == itens


def test_manifesto_confere_todos_os_arquivos(pacote):
    _, _, zip_, _ = pacote
    raiz = zip_.namelist()[0].split("/")[0]
    manifesto = json.loads(zip_.read(f"{raiz}/07_AUDITORIA/manifesto.json"))
    assert manifesto["total_centavos"] == manifesto["teto_centavos"] == 15_000_000
    listados = {a["caminho"]: a["sha256"] for a in manifesto["arquivos"]}
    no_zip = {n[len(raiz) + 1:] for n in zip_.namelist()} - {"07_AUDITORIA/manifesto.json"}
    assert set(listados) == no_zip
    for caminho, sha in listados.items():
        assert hashlib.sha256(zip_.read(f"{raiz}/{caminho}")).hexdigest() == sha


def test_conteudo_dos_pdfs(pacote):
    dossie, _, zip_, _ = pacote
    raiz = zip_.namelist()[0].split("/")[0]
    resumo = _texto(zip_, f"{raiz}/00_RESUMO/resumo.pdf")
    assert "R$ 150.000,00" in resumo and "Orça.AI" in resumo
    conformidade = _texto(zip_, f"{raiz}/00_RESUMO/conformidade.pdf")
    assert "PROBLEMA" in conformidade and "Folha sulfite 500 Folhas" in conformidade
    orcamento_1 = _texto(zip_, f"{raiz}/01_ORCAMENTOS/Material_Pedagogico_e_Escritorio/Orcamento_1.pdf")
    assert "Lepok" in orcamento_1 and "19.576.717/0001-04" in orcamento_1 and "Não é um documento emitido pela loja" in orcamento_1
    grade = _texto(zip_, f"{raiz}/01_ORCAMENTOS/Alimentacao/grade_comparativa.pdf")
    assert "ACIMA DA MÉDIA" in grade and "Banana chips" in grade
    memoria = _texto(zip_, f"{raiz}/06_MEMORIA_CALCULO/memoria_calculo.pdf")
    assert "Valor-hora" in memoria and "sem problemas" in memoria
    cotacao = PdfReader(io.BytesIO(zip_.read(
        f"{raiz}/02_COTACOES/Material_Pedagogico_e_Escritorio/02_Pasta_sanfonada_12_Divisorias/cotacao.pdf")))
    # capa (1+ páginas) + 3 páginas capturadas + comprovante da Kalunga (loja do lote)
    assert len(cotacao.pages) >= 5
    assert "Pasta sanfonada 12 Divisórias" in " ".join(cotacao.pages[0].extract_text().split())


def test_pacote_recusa_evidencia_alterada(tmp_path, renderizador):
    armazem = ArmazemArquivos(tmp_path)
    dossie, _ = montar(armazem)
    arquivo = dossie.orcamentos[0].lotes[0].linhas[0].fontes[0].evidencia.arquivo("pdf")
    caminho = tmp_path / arquivo.caminho
    caminho.chmod(0o666)
    caminho.write_bytes(b"%PDF-1.4 adulterado")
    with pytest.raises(ErroIntegridade):
        gerar_pacote(dossie, armazem, renderizador, HOJE)


def test_salvar_pacote_nao_sobrescreve(tmp_path, pacote):
    dossie, _, _, conteudo = pacote
    destino = salvar_pacote(conteudo, tmp_path, dossie)
    assert destino.name == "2026-09-24_103000.zip" and destino.parent.name == nome_de_arquivo(dossie.projeto.nome, 50)
    with pytest.raises(FileExistsError):
        salvar_pacote(conteudo, tmp_path, dossie)
