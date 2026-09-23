"""Pacote completo (ZIP) com a estrutura de docs/02 §18 e o manifesto de impressões digitais.

Os arquivos de evidência vêm do armazém e são conferidos ao ler (o nome é o SHA-256
do conteúdo). O manifesto lista o SHA-256 de todos os arquivos do pacote.
"""

import hashlib
import io
import json
import re
import unicodedata
import zipfile
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from orca.documentos.conformidade import conferir
from orca.documentos.modelo import Dossie, EvidenciaDoc
from orca.documentos.pdf import BRASILIA, Renderizador, juntar_pdfs
from orca.documentos.planilhas import grade_comparativa, plano_de_aplicacao
from orca.evidencias import ArmazemArquivos

EXTENSOES = {"pdf": "pdf", "png": "png", "mhtml": "mhtml"}


def nome_de_arquivo(texto: str, limite: int = 60) -> str:
    """Sem acentos nem símbolos: funciona em qualquer sistema ("Café 500g" → "Cafe_500g")."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    limpo = re.sub(r"[^A-Za-z0-9.-]+", "_", sem_acento).strip("_.")
    return (limpo[:limite].rstrip("_.") or "sem_nome")


def _json(dados) -> bytes:
    def padrao(v):
        if isinstance(v, (datetime, date)):
            return v.isoformat()
        raise TypeError(type(v).__name__)

    return json.dumps(dados, ensure_ascii=False, indent=2, default=padrao).encode("utf-8")


def _arquivos_da_evidencia(armazem: ArmazemArquivos, evidencia: EvidenciaDoc | None, prefixo: str) -> dict[str, bytes]:
    if evidencia is None:
        return {}
    return {f"{prefixo}.{EXTENSOES[a.tipo]}": armazem.ler(a.caminho) for a in evidencia.arquivos if a.tipo in EXTENSOES}


def montar_arquivos(dossie: Dossie, armazem: ArmazemArquivos, renderizador: Renderizador, hoje: date) -> dict[str, bytes]:
    """Todos os arquivos do pacote: caminho relativo → conteúdo (sem o manifesto)."""
    arquivos: dict[str, bytes] = {}
    conferencias = conferir(dossie, hoje)

    arquivos["00_RESUMO/resumo.pdf"] = renderizador.resumo(dossie, conferencias)
    arquivos["00_RESUMO/conformidade.pdf"] = renderizador.conformidade(dossie, conferencias, hoje)
    arquivos["00_RESUMO/pesquisa.pdf"] = renderizador.pesquisa(dossie)

    comprovantes = {}  # raiz do CNPJ ou CNPJ → PDF do comprovante
    for cnpj, empresa in sorted(dossie.empresas.items()):
        if empresa.comprovante is not None:
            conteudo = armazem.ler(empresa.comprovante.caminho)
            comprovantes[cnpj] = conteudo
            arquivos[f"04_CNPJ/{cnpj}_{nome_de_arquivo(empresa.nome, 40)}.pdf"] = conteudo

    for o in dossie.orcamentos:
        pasta = nome_de_arquivo(o.nome)
        if o.lotes:
            posicoes = max(len(l.lojas) for l in o.lotes)
            for k in range(posicoes):
                arquivos[f"01_ORCAMENTOS/{pasta}/Orcamento_{k + 1}.pdf"] = renderizador.orcamento(dossie, o, k)
            arquivos[f"01_ORCAMENTOS/{pasta}/grade_comparativa.xlsx"] = grade_comparativa(o, dossie)
            arquivos[f"01_ORCAMENTOS/{pasta}/grade_comparativa.pdf"] = renderizador.grade(dossie, o)
        arquivos[f"01_ORCAMENTOS/{pasta}/Orcamento_Final.pdf"] = renderizador.orcamento_final(dossie, o)

        numero = 0
        for lote in o.lotes:
            for linha in lote.linhas:
                numero += 1
                destino = f"02_COTACOES/{pasta}/{numero:02d}_{nome_de_arquivo(linha.nome, 40)}"
                paginas = [renderizador.capa_cotacao(dossie, o, lote, linha)]
                for k, fonte in enumerate(linha.fontes, 1):
                    capturados = _arquivos_da_evidencia(armazem, fonte.evidencia, f"fonte_{k}")
                    arquivos |= {f"{destino}/{nome}": dados for nome, dados in capturados.items()}
                    if f"fonte_{k}.pdf" in capturados:
                        paginas.append(capturados[f"fonte_{k}.pdf"])
                for loja in lote.lojas:
                    if loja.empresa.cnpj in comprovantes:
                        paginas.append(comprovantes[loja.empresa.cnpj])
                arquivos[f"{destino}/cotacao.pdf"] = juntar_pdfs(paginas)

        for cargo in o.cargos:
            destino = f"03_VAGAS/{nome_de_arquivo(cargo.nome)}"
            paginas = [renderizador.capa_cargo(dossie, cargo)]
            for k, vaga in enumerate(cargo.vagas, 1):
                capturados = _arquivos_da_evidencia(armazem, vaga.evidencia, f"vaga_{k}")
                arquivos |= {f"{destino}/{nome}": dados for nome, dados in capturados.items()}
                if f"vaga_{k}.pdf" in capturados:
                    paginas.append(capturados[f"vaga_{k}.pdf"])
                if vaga.empresa.cnpj in comprovantes:
                    paginas.append(comprovantes[vaga.empresa.cnpj])
            arquivos[f"{destino}/cotacao.pdf"] = juntar_pdfs(paginas)

    arquivos["05_PLANO/plano_aplicacao.xlsx"] = plano_de_aplicacao(dossie)
    arquivos["06_MEMORIA_CALCULO/memoria_calculo.pdf"] = renderizador.memoria(dossie)
    arquivos["06_MEMORIA_CALCULO/otimizacao.json"] = _json({
        "otimizacao": asdict(dossie.otimizacao),
        "linhas": [
            {"orcamento": o.nome, "lote": l.nome, "item": linha.nome, "preco_final_centavos": linha.preco_final_centavos,
             "quantidade": linha.quantidade, "quantidade_planejada": linha.quantidade_planejada, "meses": linha.meses,
             "total_centavos": linha.total_no_projeto}
            for o in dossie.orcamentos for l in o.lotes for linha in l.linhas
        ] + [
            {"orcamento": o.nome, "cargo": c.nome, "valor_mensal_centavos": c.valor_mensal_centavos,
             "horas_mes_centesimos": c.horas_mes_centesimos, "horas_planejadas_centesimos": c.horas_planejadas_centesimos,
             "postos": c.postos, "meses": c.meses, "total_centavos": c.total_no_projeto}
            for o in dossie.orcamentos for c in o.cargos
        ],
        "total_centavos": dossie.total_centavos,
        "teto_centavos": dossie.projeto.teto_centavos,
    })
    arquivos["07_AUDITORIA/historico.pdf"] = renderizador.historico(dossie)
    arquivos["07_AUDITORIA/historico.json"] = _json([asdict(e) for e in dossie.eventos])
    return arquivos


def manifesto(dossie: Dossie, arquivos: dict[str, bytes]) -> bytes:
    p = dossie.projeto
    return _json({
        "sistema": f"Orça.AI {p.versao_sistema}".strip(),
        "projeto": p.nome,
        "gerado_em": p.gerado_em,
        "impressao_regras": p.impressao_regras,
        "total_centavos": dossie.total_centavos,
        "teto_centavos": p.teto_centavos,
        "arquivos": [
            {"caminho": caminho, "sha256": hashlib.sha256(dados).hexdigest(), "bytes": len(dados)}
            for caminho, dados in sorted(arquivos.items())
        ],
    })


def gerar_pacote(dossie: Dossie, armazem: ArmazemArquivos, renderizador: Renderizador, hoje: date | None = None) -> bytes:
    """O ZIP completo, com uma pasta raiz <PROJETO>_<AAAA-MM-DD>."""
    gerado = dossie.projeto.gerado_em or datetime.now(BRASILIA)
    local = gerado.astimezone(BRASILIA)
    hoje = hoje or local.date()
    raiz = f"{nome_de_arquivo(dossie.projeto.nome, 50)}_{local.date().isoformat()}"
    arquivos = montar_arquivos(dossie, armazem, renderizador, hoje)
    arquivos["07_AUDITORIA/manifesto.json"] = manifesto(dossie, arquivos)
    saida = io.BytesIO()
    carimbo = local.timetuple()[:6]
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zip_:
        for caminho, dados in sorted(arquivos.items()):
            info = zipfile.ZipInfo(f"{raiz}/{caminho}", date_time=carimbo)
            info.compress_type = zipfile.ZIP_DEFLATED
            zip_.writestr(info, dados)
    return saida.getvalue()


def salvar_pacote(conteudo: bytes, pasta_exportacoes: Path | str, dossie: Dossie) -> Path:
    """Grava em exportacoes/<projeto>/<AAAA-MM-DD_HHMMSS>.zip (nunca sobrescreve)."""
    local = (dossie.projeto.gerado_em or datetime.now(BRASILIA)).astimezone(BRASILIA)
    destino = Path(pasta_exportacoes) / nome_de_arquivo(dossie.projeto.nome, 50) / f"{local:%Y-%m-%d_%H%M%S}.zip"
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        raise FileExistsError(f"Já existe um pacote gerado neste momento: {destino}")
    destino.write_bytes(conteudo)
    return destino
