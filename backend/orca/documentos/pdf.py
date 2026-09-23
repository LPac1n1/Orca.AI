"""PDFs dos documentos: HTML (Jinja2) → PDF pelo Edge (Playwright); pypdf junta arquivos (docs/04 §2).

Um só motor de renderização para tudo. Os modelos ficam em `documentos/modelos/`.
"""

import html
import io
from datetime import date, datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from playwright.sync_api import sync_playwright
from pypdf import PdfReader, PdfWriter

from orca.calculo import formatar, formatar_exato, formatar_horas
from orca.documentos.conformidade import Conferencia, resumo_da_conformidade
from orca.documentos.modelo import CargoDoc, Dossie, LinhaCotacao, LoteDoc, OrcamentoDoc
from orca.dominio import formatar_cnpj

BRASILIA = ZoneInfo("America/Sao_Paulo")
SITUACOES = {"ok": "OK", "atencao": "ATENÇÃO", "problema": "PROBLEMA"}
TIPOS = {"materiais": "Materiais", "mao_de_obra": "Mão de obra", "servicos": "Serviços"}
REGIMES = {"mei": "MEI", "recibo": "Recibo (RPA)", "clt": "CLT"}


def _datahora(momento: datetime | None) -> str:
    return momento.astimezone(BRASILIA).strftime("%d/%m/%Y %H:%M") if momento else "—"


def _data(dia: date | None) -> str:
    return dia.strftime("%d/%m/%Y") if dia else "—"


def ambiente() -> Environment:
    env = Environment(
        loader=FileSystemLoader(Path(__file__).parent / "modelos"),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(
        reais=formatar,
        exato=lambda v: formatar_exato(v if isinstance(v, Fraction) else Fraction(v)),
        horas=formatar_horas,
        cnpj=lambda c: formatar_cnpj(c) if c else "não identificado",
        data=_data,
        datahora=_datahora,
        regime=lambda r: REGIMES.get(r, r),
    )
    return env


def _otimizacao_texto(dossie: Dossie) -> str:
    return {
        "otima": "teto fechado (solução ótima)",
        "viavel": "teto fechado (solução válida; o tempo acabou antes de provar a melhor)",
        "sem_otimizacao": "não otimizado",
    }[dossie.otimizacao.status]


def _contar_linhas(orcamento: OrcamentoDoc) -> int:
    return sum(len(l.linhas) for l in orcamento.lotes) + len(orcamento.cargos)


class Renderizador:
    """Use com `with Renderizador() as r: r.pdf(html)` — abre o Edge sem janela uma vez só."""

    def __init__(self, canal: str = "msedge"):
        self.canal = canal
        self.env = ambiente()

    def __enter__(self) -> "Renderizador":
        self._playwright = sync_playwright().start()
        self._navegador = self._playwright.chromium.launch(channel=self.canal, headless=True)
        self._pagina = self._navegador.new_page()
        return self

    def __exit__(self, *_erro) -> None:
        self._navegador.close()
        self._playwright.stop()

    def pdf(self, conteudo_html: str, rodape: str = "", paisagem: bool = False) -> bytes:
        self._pagina.set_content(conteudo_html, wait_until="load")
        return self._pagina.pdf(
            format="A4",
            landscape=paisagem,
            print_background=True,
            display_header_footer=True,
            header_template="<span></span>",
            footer_template=(
                '<div style="font-size:7px;width:100%;padding:0 10mm;font-family:Arial,sans-serif;color:#555;'
                f'display:flex;justify-content:space-between;"><span>{html.escape(rodape)}</span>'
                '<span>página <span class="pageNumber"></span> de <span class="totalPages"></span></span></div>'
            ),
            margin={"top": "12mm", "bottom": "14mm", "left": "10mm", "right": "10mm"},
        )

    # --- Documentos ------------------------------------------------------------------------------

    def _documento(self, modelo: str, dossie: Dossie, titulo: str, paisagem: bool = False, **contexto) -> bytes:
        p = dossie.projeto
        conteudo = self.env.get_template(modelo).render(
            titulo=titulo, projeto=p, dossie=dossie, situacoes=SITUACOES, tipos=TIPOS,
            otimizacao_texto=_otimizacao_texto(dossie), contar_linhas=_contar_linhas, **contexto,
        )
        rodape = f"Orça.AI · {p.nome} · {titulo} · gerado em {_datahora(p.gerado_em)} (Brasília)"
        return self.pdf(conteudo, rodape, paisagem)

    def resumo(self, dossie: Dossie, conferencias: tuple[Conferencia, ...]) -> bytes:
        return self._documento("resumo.html", dossie, "Resumo do orçamento", conferencias=conferencias,
                               contagem=resumo_da_conformidade(conferencias))

    def conformidade(self, dossie: Dossie, conferencias: tuple[Conferencia, ...], hoje: date) -> bytes:
        return self._documento("conformidade.html", dossie, "Relatório de conformidade", conferencias=conferencias, hoje=hoje)

    def orcamento(self, dossie: Dossie, orcamento: OrcamentoDoc, posicao: int) -> bytes:
        return self._documento("orcamento.html", dossie, f"{orcamento.nome} — Orçamento {posicao + 1}",
                               orcamento=orcamento, posicao=posicao)

    def orcamento_final(self, dossie: Dossie, orcamento: OrcamentoDoc) -> bytes:
        return self._documento("orcamento_final.html", dossie, f"{orcamento.nome} — Orçamento final", orcamento=orcamento)

    def grade(self, dossie: Dossie, orcamento: OrcamentoDoc) -> bytes:
        return self._documento("grade.html", dossie, f"{orcamento.nome} — Grade comparativa", paisagem=True,
                               orcamento=orcamento)

    def memoria(self, dossie: Dossie) -> bytes:
        return self._documento("memoria.html", dossie, "Memória de cálculo")

    def pesquisa(self, dossie: Dossie) -> bytes:
        return self._documento("pesquisa.html", dossie, "Relatório de pesquisa")

    def historico(self, dossie: Dossie) -> bytes:
        return self._documento("historico.html", dossie, "Histórico de alterações")

    def capa_cotacao(self, dossie: Dossie, orcamento: OrcamentoDoc, lote: LoteDoc, linha: LinhaCotacao) -> bytes:
        return self._documento("cotacao.html", dossie, f"Cotação — {linha.nome}", orcamento=orcamento, lote=lote, linha=linha)

    def capa_cargo(self, dossie: Dossie, cargo: CargoDoc) -> bytes:
        return self._documento("cotacao_cargo.html", dossie, f"Cotação — {cargo.nome}", cargo=cargo)


def juntar_pdfs(partes: list[bytes]) -> bytes:
    """Junta PDFs na ordem dada (capa da cotação + páginas capturadas + comprovantes)."""
    escritor = PdfWriter()
    for parte in partes:
        escritor.append(PdfReader(io.BytesIO(parte)))
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()

