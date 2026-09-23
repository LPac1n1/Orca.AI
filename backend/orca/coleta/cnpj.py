"""Consulta da situação cadastral do CNPJ em APIs gratuitas (docs/02 §11; docs/04 §5.4).

Provedores tentados em ordem (regra `cnpj.provedores`). Só os dados necessários são
guardados — nada de sócios, e-mails ou telefones (LGPD).
"""

import json
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

import httpx

from orca.dominio import normalizar_cnpj

_SITUACOES_RECEITA = {1: "NULA", 2: "ATIVA", 3: "SUSPENSA", 4: "INAPTA", 8: "BAIXADA"}
CAMPOS_GUARDADOS = (
    "cnpj", "razao_social", "nome_fantasia", "situacao", "data_situacao",
    "municipio", "uf", "cnae_principal", "natureza_juridica", "matriz_filial",
)


class ErroCnpj(RuntimeError):
    pass


@dataclass(frozen=True)
class DadosCnpj:
    cnpj: str
    razao_social: str | None
    nome_fantasia: str | None
    situacao: str | None  # "ATIVA", "BAIXADA"…
    data_situacao: date | None
    municipio: str | None
    uf: str | None
    provedor: str
    resumo: dict[str, Any]  # só CAMPOS_GUARDADOS

    @property
    def ativo(self) -> bool:
        return self.situacao == "ATIVA"


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _situacao(valor: Any) -> str | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, int) or (isinstance(valor, str) and valor.strip().isdigit()):
        return _SITUACOES_RECEITA.get(int(valor), f"CÓDIGO {valor}")
    return _sem_acento(str(valor)).strip().upper()


def _data(valor: Any) -> date | None:
    try:
        return date.fromisoformat(str(valor)[:10]) if valor else None
    except ValueError:
        return None


def _vazio(valor: Any) -> Any:
    return valor if valor not in ("", None) else None


class ProvedorCnpj(Protocol):
    nome: str

    def consultar(self, cnpj: str, cliente: httpx.Client) -> DadosCnpj: ...


class OpenCnpj:
    nome = "opencnpj"
    url = "https://api.opencnpj.org/{cnpj}"

    def consultar(self, cnpj: str, cliente: httpx.Client) -> DadosCnpj:
        d = _obter(cliente, self.url.format(cnpj=cnpj))
        return _montar(
            self.nome, cnpj, d.get("razao_social"), d.get("nome_fantasia"), d.get("situacao_cadastral"),
            d.get("data_situacao_cadastral"), d.get("municipio"), d.get("uf"), d.get("cnae_principal"),
            d.get("natureza_juridica"), d.get("matriz_filial"),
        )


class BrasilApi:
    nome = "brasilapi"
    url = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"

    def consultar(self, cnpj: str, cliente: httpx.Client) -> DadosCnpj:
        d = _obter(cliente, self.url.format(cnpj=cnpj))
        situacao = d.get("descricao_situacao_cadastral") or d.get("situacao_cadastral")
        matriz = {1: "Matriz", 2: "Filial"}.get(d.get("identificador_matriz_filial"))
        return _montar(
            self.nome, cnpj, d.get("razao_social"), d.get("nome_fantasia"), situacao,
            d.get("data_situacao_cadastral"), d.get("municipio"), d.get("uf"), d.get("cnae_fiscal"),
            d.get("natureza_juridica"), matriz,
        )


PROVEDORES: dict[str, ProvedorCnpj] = {p.nome: p for p in (OpenCnpj(), BrasilApi())}


def _obter(cliente: httpx.Client, url: str) -> dict:
    try:
        resposta = cliente.get(url, timeout=20)
    except httpx.HTTPError as e:
        raise ErroCnpj(f"falha de conexão: {e}") from e
    if resposta.status_code == 404:
        raise ErroCnpj("CNPJ não encontrado")
    if resposta.status_code != 200:
        raise ErroCnpj(f"o serviço respondeu com o código {resposta.status_code}")
    try:
        dados = resposta.json()
    except json.JSONDecodeError as e:
        raise ErroCnpj("resposta inválida do serviço") from e
    if not isinstance(dados, dict):
        raise ErroCnpj("resposta inválida do serviço")
    return dados


def _montar(provedor, cnpj, razao, fantasia, situacao, data_sit, municipio, uf, cnae, natureza, matriz) -> DadosCnpj:
    dados = DadosCnpj(
        cnpj=cnpj,
        razao_social=_vazio(razao),
        nome_fantasia=_vazio(fantasia),
        situacao=_situacao(situacao),
        data_situacao=_data(data_sit),
        municipio=_vazio(municipio),
        uf=_vazio(uf),
        provedor=provedor,
        resumo={},
    )
    resumo = {
        "cnpj": cnpj, "razao_social": dados.razao_social, "nome_fantasia": dados.nome_fantasia,
        "situacao": dados.situacao, "data_situacao": dados.data_situacao.isoformat() if dados.data_situacao else None,
        "municipio": dados.municipio, "uf": dados.uf, "cnae_principal": _vazio(cnae),
        "natureza_juridica": _vazio(natureza), "matriz_filial": _vazio(matriz),
    }
    return DadosCnpj(**{**dados.__dict__, "resumo": resumo})


def consultar_cnpj(cnpj: str, provedores: list[str], cliente: httpx.Client | None = None) -> DadosCnpj:
    """Consulta o CNPJ nos provedores, em ordem; o primeiro que responder vale."""
    cnpj = normalizar_cnpj(cnpj)
    proprio = cliente is None
    cliente = cliente or httpx.Client(headers={"User-Agent": "Orca.AI (montador de orcamentos para OSCs)"})
    erros = []
    try:
        for nome in provedores:
            if nome not in PROVEDORES:
                erros.append(f"{nome}: provedor desconhecido")
                continue
            try:
                return PROVEDORES[nome].consultar(cnpj, cliente)
            except ErroCnpj as e:
                erros.append(f"{nome}: {e}")
    finally:
        if proprio:
            cliente.close()
    raise ErroCnpj("Não foi possível validar automaticamente o CNPJ. " + "; ".join(erros))
