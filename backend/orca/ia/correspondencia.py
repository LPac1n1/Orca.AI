"""A IA confere os 🟡 (docs/04 §6: "julgar correspondência 🟡").

Ela só pode manter o 🟡 ou rebaixar para 🔴, com motivo; nunca promove para 🟢 (D-52,
princípio 4 — o banco também recusa). Recebe só dados públicos do produto pedido e do
anúncio (D-51): descrição, marca, modelo, apresentação e atributos; título, marca e
código de barras da página. Nenhum dado da OSC ou de pessoas.
"""

import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ValidationError, field_validator

from orca.correspondencia import Anuncio, Especificacao
from orca.ia.provedores import ErroFormatoIA, ProvedorIA

PEDIDO = """Você confere anúncios de lojas para um orçamento. Mesmo produto = mesma marca, mesmo modelo e mesma \
apresentação (tamanho, peso, volume, quantidade na embalagem), e também mesmo sabor, cor ou tipo, quando houver.

Produto pedido:
{item}

Anúncio da loja:
{anuncio}

Responda só com JSON, neste formato: {{"mesmo_produto": "sim" ou "nao" ou "incerto", "motivo": "frase curta em português"}}
Responda "nao" só se houver uma diferença clara entre os dois (outra marca, outro tamanho, outra quantidade, outro \
sabor ou tipo). Se faltar informação, responda "incerto"."""


class _Resposta(BaseModel):
    mesmo_produto: Literal["sim", "nao", "incerto"]
    motivo: str

    @field_validator("mesmo_produto", mode="before")
    @classmethod
    def _sem_acento(cls, valor):
        return valor.strip().lower().replace("não", "nao") if isinstance(valor, str) else valor

    @field_validator("motivo")
    @classmethod
    def _curto(cls, valor: str) -> str:
        valor = " ".join(valor.split())
        if not valor:
            raise ValueError("motivo vazio")
        return valor[:300]


@dataclass(frozen=True)
class Julgamento:
    resposta: str  # sim | nao | incerto
    motivo: str
    entrada: dict  # o que foi enviado (para o registro da tarefa)

    @property
    def rebaixar(self) -> bool:
        return self.resposta == "nao"


def dados_enviados(especificacao: Especificacao, anuncio: Anuncio) -> dict:
    """Só dados públicos de produto (D-51)."""
    item = {"descricao": especificacao.descricao, "marca": especificacao.marca, "modelo": especificacao.modelo,
            "apresentacao": especificacao.apresentacao, "atributos": dict(especificacao.atributos) or None}
    pagina = {"titulo": anuncio.titulo, "marca": anuncio.marca, "codigo_de_barras": anuncio.ean,
              "complemento": anuncio.complemento or None}
    return {"produto_pedido": {k: v for k, v in item.items() if v},
            "anuncio": {k: v for k, v in pagina.items() if v}}


def julgar_correspondencia(provedor: ProvedorIA, especificacao: Especificacao, anuncio: Anuncio) -> Julgamento:
    entrada = dados_enviados(especificacao, anuncio)
    pedido = PEDIDO.format(item=json.dumps(entrada["produto_pedido"], ensure_ascii=False),
                           anuncio=json.dumps(entrada["anuncio"], ensure_ascii=False))
    try:
        resposta = _Resposta.model_validate(provedor.responder_json(pedido))
    except ValidationError as erro:
        raise ErroFormatoIA("A IA não respondeu no formato combinado.") from erro
    return Julgamento(resposta.mesmo_produto, resposta.motivo, entrada)
