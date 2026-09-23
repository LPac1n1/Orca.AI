"""Escolha das vagas de um cargo (docs/02 §10.3; D-46 a D-49, P-04).

A detecção de vagas repetidas (mesma vaga em várias plataformas) é feita na
coleta; aqui cada vaga já chega com o seu `grupo` de duplicidade.
"""

from collections.abc import Sequence
from dataclasses import dataclass

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
