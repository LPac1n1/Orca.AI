"""Camadas de regras: leitura, soma em ordem, versão e origem de cada regra (docs/02 §4).

Ordem das camadas: sistema → osc → secretaria → projeto → orcamento.
Cada camada declara só o que muda. Na soma:
  - grupos de chaves são somados recursivamente;
  - listas e valores simples substituem o anterior;
  - um grupo vazio ({}) limpa o grupo.
O resultado guarda de qual camada veio cada regra e uma impressão digital
(SHA-256) do perfil completo, gravada em cada cálculo.
"""

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from importlib import resources
from types import MappingProxyType
from typing import Any

import yaml
from pydantic import ValidationError

from orca.regras.modelo import PerfilRegras

NIVEIS = ("sistema", "osc", "secretaria", "projeto", "orcamento")
METADADOS = ("perfil", "camada", "versao", "descricao", "fonte")


class ErroRegras(ValueError):
    """Um ou mais problemas num perfil de regras, descritos em português."""

    def __init__(self, problemas: Sequence[str]):
        self.problemas = list(problemas)
        super().__init__("\n".join(self.problemas))


class _Leitor(yaml.SafeLoader):
    """Leitor de YAML sem números decimais (evita float nas regras)."""


def _recusar_decimal(loader: yaml.SafeLoader, node: yaml.Node) -> Any:
    raise ErroRegras(
        [
            f"linha {node.start_mark.line + 1}: o valor decimal {node.value!r} não é aceito; "
            "use números inteiros (ex.: percentual -20 em vez de -0.20)"
        ]
    )


def _data_como_texto(loader: yaml.SafeLoader, node: yaml.Node) -> str:
    return loader.construct_scalar(node)


_Leitor.add_constructor("tag:yaml.org,2002:float", _recusar_decimal)
_Leitor.add_constructor("tag:yaml.org,2002:timestamp", _data_como_texto)


def _canonico(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _impressao(obj: Any) -> str:
    return hashlib.sha256(_canonico(obj).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Camada:
    """Uma camada de regras, como escrita no arquivo."""

    nome: str
    nivel: str
    versao: int
    conteudo: Mapping[str, Any]
    descricao: str | None = None
    fonte: str | None = None

    @property
    def impressao(self) -> str:
        return _impressao(
            {"perfil": self.nome, "camada": self.nivel, "versao": self.versao, "conteudo": self.conteudo}
        )

    def para_yaml(self) -> str:
        dados: dict[str, Any] = {"perfil": self.nome, "camada": self.nivel, "versao": self.versao}
        for chave in ("descricao", "fonte"):
            if getattr(self, chave):
                dados[chave] = getattr(self, chave)
        dados.update(copy.deepcopy(dict(self.conteudo)))
        return yaml.safe_dump(dados, allow_unicode=True, sort_keys=False)


def ler_camada(texto: str, origem: str = "texto") -> Camada:
    """Lê uma camada escrita em YAML. `origem` aparece nas mensagens de erro."""
    try:
        dados = yaml.load(texto, Loader=_Leitor)  # noqa: S506 — _Leitor deriva do SafeLoader
    except ErroRegras as e:
        raise ErroRegras([f"{origem}: {p}" for p in e.problemas]) from None
    except yaml.YAMLError as e:
        raise ErroRegras([f"{origem}: o arquivo não é um YAML válido ({e})"]) from None
    if not isinstance(dados, dict):
        raise ErroRegras([f"{origem}: o perfil precisa ser um grupo de chaves"])

    problemas = []
    nome, nivel, versao = dados.get("perfil"), dados.get("camada"), dados.get("versao")
    if not isinstance(nome, str) or not nome.strip():
        problemas.append(f"{origem}: falta o nome do perfil (chave 'perfil')")
    if nivel not in NIVEIS:
        problemas.append(f"{origem}: 'camada' deve ser uma destas: {', '.join(NIVEIS)}")
    if isinstance(versao, bool) or not isinstance(versao, int) or versao < 1:
        problemas.append(f"{origem}: 'versao' deve ser um número inteiro a partir de 1")
    for chave in ("descricao", "fonte"):
        if dados.get(chave) is not None and not isinstance(dados[chave], str):
            problemas.append(f"{origem}: '{chave}' deve ser texto")
    conteudo = {k: v for k, v in dados.items() if k not in METADADOS}
    for chave, valor in conteudo.items():
        if not isinstance(valor, dict):
            problemas.append(f"{origem}: '{chave}' deve ser um grupo de regras")
    if problemas:
        raise ErroRegras(problemas)
    return Camada(
        nome=nome.strip(),
        nivel=nivel,
        versao=versao,
        conteudo=conteudo,
        descricao=dados.get("descricao"),
        fonte=dados.get("fonte"),
    )


def camada_padrao() -> Camada:
    """O perfil padrão do sistema, distribuído com o programa."""
    texto = resources.files("orca.regras").joinpath("padrao-sistema.yaml").read_text(encoding="utf-8")
    return ler_camada(texto, "padrao-sistema.yaml")


@dataclass(frozen=True)
class RefCamada:
    """Identificação de uma camada usada num perfil resolvido."""

    nome: str
    nivel: str
    versao: int
    impressao: str


@dataclass(frozen=True)
class PerfilResolvido:
    """Perfil completo e validado, com a cadeia de camadas e a origem de cada regra."""

    regras: PerfilRegras
    cadeia: tuple[RefCamada, ...]
    impressao: str
    origem: Mapping[str, str] = field(repr=False)

    def origem_de(self, caminho: str) -> str:
        """Nome da camada que definiu a regra (ex.: 'fontes.validade_dias')."""
        responsavel = _responsavel(self.origem, caminho)
        if responsavel is None:
            raise KeyError(f"Regra desconhecida: {caminho}")
        return responsavel


def _registrar(origem: dict[str, str], caminho: tuple[str, ...], valor: Any, camada: str) -> None:
    texto = ".".join(caminho)
    for chave in [c for c in origem if c == texto or c.startswith(texto + ".")]:
        del origem[chave]
    if isinstance(valor, dict) and valor:
        for k, v in valor.items():
            _registrar(origem, caminho + (str(k),), v, camada)
    else:
        origem[texto] = camada


def _somar(base: dict, sobre: Mapping, camada: str, origem: dict[str, str], caminho: tuple[str, ...] = ()) -> None:
    for chave, valor in sobre.items():
        c = caminho + (str(chave),)
        if isinstance(valor, dict) and valor and isinstance(base.get(chave), dict):
            _somar(base[chave], valor, camada, origem, c)
        else:
            base[chave] = copy.deepcopy(valor)
            _registrar(origem, c, valor, camada)


_MENSAGENS = {
    "extra_forbidden": "chave desconhecida",
    "missing": "falta definir esta regra",
    "int_type": "deve ser um número inteiro",
    "bool_type": "deve ser true ou false",
    "string_type": "deve ser texto",
    "list_type": "deve ser uma lista",
    "dict_type": "deve ser um grupo de chaves",
    "model_type": "deve ser um grupo de chaves",
    "too_short": "não pode ficar vazia",
}


def _mensagem(erro: dict) -> tuple[str, str]:
    """(caminho, mensagem em português) para um erro de validação."""
    tipo, ctx = erro["type"], erro.get("ctx") or {}
    caminho = ctx.get("campo") or ".".join(str(p) for p in erro["loc"])
    if tipo == "regra_invalida":
        return caminho, erro["msg"]
    if tipo == "literal_error":
        opcoes = str(ctx.get("expected", "")).replace(" or ", " ou ")
        return caminho, f"valor {erro['input']!r} não permitido; use: {opcoes}"
    if tipo == "greater_than_equal":
        return caminho, f"deve ser maior ou igual a {ctx.get('ge')}"
    if tipo == "less_than_equal":
        return caminho, f"deve ser menor ou igual a {ctx.get('le')}"
    return caminho, _MENSAGENS.get(tipo, erro["msg"])


def _responsavel(origem: Mapping[str, str], caminho: str) -> str | None:
    if caminho in origem:
        return origem[caminho]
    nomes = sorted({nome for chave, nome in origem.items() if chave.startswith(caminho + ".")})
    return " + ".join(nomes) if nomes else None


def resolver(camadas: Sequence[Camada]) -> PerfilResolvido:
    """Soma as camadas em ordem e valida o perfil completo."""
    if not camadas:
        raise ErroRegras(["informe ao menos a camada do sistema"])
    problemas = []
    invalidas = [c for c in camadas if c.nivel not in NIVEIS]
    if invalidas:
        raise ErroRegras([f"camada '{c.nome}': nível desconhecido '{c.nivel}'" for c in invalidas])
    if camadas[0].nivel != "sistema":
        problemas.append(f"a primeira camada deve ser a do sistema, não '{camadas[0].nivel}' ({camadas[0].nome})")
    posicoes = [NIVEIS.index(c.nivel) for c in camadas]
    for anterior, atual, camada in zip(posicoes, posicoes[1:], camadas[1:]):
        if atual <= anterior:
            problemas.append(
                f"camada fora de ordem: '{camada.nivel}' ({camada.nome}) vem depois de '{NIVEIS[anterior]}'; "
                f"a ordem é {' → '.join(NIVEIS)}, cada nível no máximo uma vez"
            )
    if problemas:
        raise ErroRegras(problemas)

    soma: dict[str, Any] = {}
    origem: dict[str, str] = {}
    for camada in camadas:
        _somar(soma, camada.conteudo, camada.nome, origem)

    try:
        regras = PerfilRegras.model_validate(soma)
    except ValidationError as e:
        linhas = []
        for erro in e.errors():
            caminho, mensagem = _mensagem(erro)
            responsavel = _responsavel(origem, caminho)
            linhas.append(f"{caminho}: {mensagem}" + (f" (camada '{responsavel}')" if responsavel else ""))
        raise ErroRegras(linhas) from None

    return PerfilResolvido(
        regras=regras,
        cadeia=tuple(RefCamada(c.nome, c.nivel, c.versao, c.impressao) for c in camadas),
        impressao=_impressao(regras.model_dump(mode="json")),
        origem=MappingProxyType(origem),
    )
