"""Escolha das vagas de um cargo (docs/02 §10.3; D-46 a D-49, P-04).

`agrupar_duplicadas` marca a mesma vaga publicada em várias plataformas (D-49);
`selecionar_vagas` usa esse `grupo` para contar cada vaga uma vez só.
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from difflib import SequenceMatcher

from orca.calculo import Cotacao
from orca.dominio import cnpj_raiz


@dataclass(frozen=True)
class Vaga:
    id: str
    empresa: str | None
    cnpj: str | None  # empresa identificada = CNPJ encontrado
    salario_min_centavos: int | None
    salario_max_centavos: int | None = None
    grupo: str | None = None  # mesma vaga em plataformas diferentes = mesmo grupo (D-49)
    plataforma: str | None = None

    @property
    def salario_referencia(self) -> int | None:
        """Faixa salarial → menor valor (D-46). Salário único vem em qualquer um dos campos."""
        if self.salario_min_centavos is not None:
            return self.salario_min_centavos
        return self.salario_max_centavos


@dataclass(frozen=True)
class SelecaoVagas:
    escolhidas: tuple[Vaga, ...]
    descartadas: tuple[tuple[Vaga, str], ...]
    cotacao: Cotacao | None
    suficiente: bool
    mensagem: str


def selecionar_vagas(vagas: Sequence[Vaga], n: int = 3, empresas_distintas: bool = True) -> SelecaoVagas:
    """As `n` vagas válidas de menor salário, de empresas diferentes (D-48, P-04)."""
    descartadas: list[tuple[Vaga, str]] = []
    validas: list[Vaga] = []
    for vaga in vagas:
        if vaga.salario_referencia is None:
            descartadas.append((vaga, "sem salário informado (D-46)"))
        elif not vaga.cnpj:
            descartadas.append((vaga, "empresa não identificada com segurança (D-46)"))
        else:
            validas.append(vaga)

    ordenadas = sorted(validas, key=lambda v: (v.salario_referencia, v.id))
    representantes: dict[str, Vaga] = {}
    unicas: list[Vaga] = []
    for vaga in ordenadas:
        if vaga.grupo is not None and vaga.grupo in representantes:
            original = representantes[vaga.grupo]
            descartadas.append((vaga, f"mesma vaga de {original.empresa} já considerada (D-49)"))
            continue
        if vaga.grupo is not None:
            representantes[vaga.grupo] = vaga
        unicas.append(vaga)

    escolhidas: list[Vaga] = []
    empresas: dict[str, str] = {}
    for vaga in unicas:
        if len(escolhidas) == n:
            break
        raiz = cnpj_raiz(vaga.cnpj)
        if empresas_distintas and raiz in empresas:
            descartadas.append((vaga, f"empresa já usada na cotação: {empresas[raiz]} (P-04)"))
            continue
        escolhidas.append(vaga)
        empresas[raiz] = vaga.empresa or vaga.cnpj

    suficiente = len(escolhidas) == n
    cotacao = Cotacao(tuple(v.salario_referencia for v in escolhidas)) if suficiente else None
    mensagem = (
        f"{n} vagas escolhidas: as de menor salário entre {len(unicas)} válidas."
        if suficiente
        else f"Só {len(escolhidas)} de {n} vagas válidas encontradas; pesquise mais vagas."
    )
    return SelecaoVagas(tuple(escolhidas), tuple(descartadas), cotacao, suficiente, mensagem)


# --- Duplicidade (D-49) --------------------------------------------------------------

SIMILARIDADE_CLARA = 0.9
SIMILARIDADE_INCERTA = 0.6
DIAS_CLARO = 15
DIAS_MAXIMO = 45
_PALAVRAS_VAZIAS = {"vaga", "vagas", "de", "da", "do", "das", "dos", "para", "e", "em", "a", "o", "ou"}


@dataclass(frozen=True)
class AnuncioVaga:
    """Dados de uma vaga para comparar com as outras."""

    vaga: Vaga
    titulo: str
    cidade: str | None = None
    publicada_em: date | None = None
    identificador: str | None = None  # código da vaga na empresa, quando a página mostra


@dataclass(frozen=True)
class ParIncerto:
    a: str
    b: str
    motivo: str


@dataclass(frozen=True)
class Duplicidade:
    vagas: tuple[Vaga, ...]  # com `grupo` preenchido nas duplicadas claras
    incertos: tuple[ParIncerto, ...]  # 🟡: o usuário decide (automacao.descartar_vaga_duplicada_incerta)


def _normalizar(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn"
    )
    sem_genero = re.sub(r"\((?:a|as|o|os)\)|/a\b", "", sem_acento)  # "auxiliar(a)", "educador/a"
    palavras = re.findall(r"[a-z0-9]+", sem_genero)
    return " ".join(p for p in palavras if p not in _PALAVRAS_VAZIAS)


def semelhanca_titulos(a: str, b: str) -> float:
    """0 a 1. Igual depois de normalizar (acentos, gênero, palavras vazias, ordem) = 1."""
    na, nb = _normalizar(a), _normalizar(b)
    if not na or not nb:
        return 0.0
    if sorted(na.split()) == sorted(nb.split()):
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _faixas_compativeis(a: Vaga, b: Vaga) -> bool:
    def faixa(v: Vaga) -> tuple[int, int]:
        minimo = v.salario_min_centavos if v.salario_min_centavos is not None else v.salario_max_centavos
        maximo = v.salario_max_centavos if v.salario_max_centavos is not None else v.salario_min_centavos
        return minimo, maximo

    (a1, a2), (b1, b2) = faixa(a), faixa(b)
    return a1 <= b2 and b1 <= a2


def _comparar(x: AnuncioVaga, y: AnuncioVaga) -> str | None:
    """'clara', 'incerta:<motivo>' ou None (vagas diferentes)."""
    a, b = x.vaga, y.vaga
    if not a.cnpj or not b.cnpj or cnpj_raiz(a.cnpj) != cnpj_raiz(b.cnpj):
        return None  # empresas diferentes (ou não identificadas, que serão descartadas)
    if a.salario_referencia is None or b.salario_referencia is None or not _faixas_compativeis(a, b):
        return None
    if x.cidade and y.cidade and _normalizar(x.cidade) != _normalizar(y.cidade):
        return None
    dias = abs((x.publicada_em - y.publicada_em).days) if x.publicada_em and y.publicada_em else None
    if dias is not None and dias > DIAS_MAXIMO:
        return None
    if x.identificador and y.identificador:
        return "clara" if x.identificador.strip().lower() == y.identificador.strip().lower() else None
    semelhanca = semelhanca_titulos(x.titulo, y.titulo)
    if semelhanca < SIMILARIDADE_INCERTA:
        return None
    mesmo_salario = a.salario_referencia == b.salario_referencia
    mesma_cidade = bool(x.cidade and y.cidade)
    datas_proximas = dias is not None and dias <= DIAS_CLARO
    if semelhanca >= SIMILARIDADE_CLARA and mesmo_salario and mesma_cidade and datas_proximas:
        return "clara"
    faltas = []
    if semelhanca < SIMILARIDADE_CLARA:
        faltas.append(f"títulos parecidos ({semelhanca:.0%})")
    if not mesmo_salario:
        faltas.append("faixas salariais que se cruzam")
    if not mesma_cidade:
        faltas.append("cidade não informada")
    if not datas_proximas:
        faltas.append("datas de publicação distantes ou não informadas")
    return "incerta:mesma empresa, " + ", ".join(faltas)


def agrupar_duplicadas(anuncios: Sequence[AnuncioVaga]) -> Duplicidade:
    """Mesma empresa, cargo equivalente, salário e local compatíveis e datas próximas = mesma vaga (D-49).

    Casos claros recebem o mesmo `grupo` (o id da primeira vaga, em ordem de id);
    casos incertos são devolvidos para o usuário decidir — nunca descartados sozinhos.
    """
    ordem = sorted(anuncios, key=lambda a: a.vaga.id)
    pai = {a.vaga.id: a.vaga.id for a in ordem}

    def raiz(i: str) -> str:
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i

    incertos = []
    for i, x in enumerate(ordem):
        for y in ordem[i + 1:]:
            resultado = _comparar(x, y)
            if resultado == "clara":
                ra, rb = raiz(x.vaga.id), raiz(y.vaga.id)
                pai[max(ra, rb)] = min(ra, rb)
            elif resultado:
                incertos.append(ParIncerto(x.vaga.id, y.vaga.id, resultado.removeprefix("incerta:")))
    tamanho: dict[str, int] = {}
    for a in ordem:
        tamanho[raiz(a.vaga.id)] = tamanho.get(raiz(a.vaga.id), 0) + 1
    vagas = tuple(
        replace(a.vaga, grupo=raiz(a.vaga.id)) if tamanho[raiz(a.vaga.id)] > 1 else a.vaga for a in anuncios
    )
    incertos = [p for p in incertos if raiz(p.a) != raiz(p.b)]  # já ficaram juntas por outro caminho
    return Duplicidade(vagas, tuple(incertos))
