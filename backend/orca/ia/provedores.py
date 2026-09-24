"""Provedores de IA plugáveis (D-50): nenhum (padrão), Gemini (plano grátis) ou modelo local (Ollama).

O sistema funciona sem IA. Quando ligada, ela só recebe dados públicos (títulos e
descrições de produtos, D-51) e só propõe (D-52); quem valida a resposta é quem pediu.
"""

import json
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from orca.cofre import Cofre

PROVEDORES = ("nenhum", "gemini", "local")
MODELO_GEMINI = "gemini-2.5-flash"  # plano grátis; dá para trocar em Opcionais
ENDERECO_LOCAL = "http://localhost:11434"  # Ollama


class ErroIA(RuntimeError):
    pass


class ErroFormatoIA(ErroIA):
    """A IA respondeu, mas fora do formato combinado: a resposta é ignorada e a próxima segue."""


@dataclass
class ConfigIA:
    """O que fica na configuração do computador (a chave, não: fica no cofre)."""

    provedor: str = "nenhum"
    modelo: str = ""
    endereco: str = ""


class ProvedorIA(Protocol):
    nome: str
    modelo: str

    def responder_json(self, pedido: str) -> dict: ...


def _json(texto: str) -> dict:
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", (texto or "").strip())
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as erro:
        raise ErroFormatoIA("A IA não respondeu no formato combinado (JSON).") from erro
    if not isinstance(dados, dict):
        raise ErroFormatoIA("A IA não respondeu no formato combinado (JSON).")
    return dados


class Gemini:
    nome = "gemini"

    def __init__(self, cliente: httpx.Client, chave: str, modelo: str = MODELO_GEMINI):
        self.cliente, self._chave, self.modelo = cliente, chave, modelo or MODELO_GEMINI

    def responder_json(self, pedido: str) -> dict:
        endereco = f"https://generativelanguage.googleapis.com/v1beta/models/{self.modelo}:generateContent"
        corpo = {"contents": [{"role": "user", "parts": [{"text": pedido}]}],
                 "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
        try:  # a chave vai no cabeçalho, nunca no endereço
            r = self.cliente.post(endereco, headers={"x-goog-api-key": self._chave}, json=corpo, timeout=60)
        except httpx.HTTPError as erro:
            raise ErroIA(f"Não deu para falar com o Gemini: {erro.__class__.__name__}") from erro
        if r.status_code == 429:
            raise ErroIA("O plano grátis do Gemini chegou ao limite de pedidos; tente mais tarde.")
        if r.status_code in (401, 403) or (r.status_code == 400 and "API key" in r.text):
            raise ErroIA("O Gemini recusou a chave. Confira a chave em Opcionais.")
        if r.status_code == 404:
            raise ErroIA(f"O Gemini não tem o modelo “{self.modelo}”. Troque o nome do modelo em Opcionais.")
        if r.status_code >= 400:
            raise ErroIA(f"O Gemini respondeu com erro (código {r.status_code}).")
        try:
            texto = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (ValueError, KeyError, IndexError, TypeError) as erro:
            raise ErroFormatoIA("O Gemini não mandou resposta (talvez bloqueada pelo filtro dele).") from erro
        return _json(texto)


class ModeloLocal:
    """Modelo rodando no próprio computador (Ollama): nada sai da máquina."""

    nome = "local"

    def __init__(self, cliente: httpx.Client, endereco: str, modelo: str):
        self.cliente, self.endereco, self.modelo = cliente, (endereco or ENDERECO_LOCAL).rstrip("/"), modelo

    def responder_json(self, pedido: str) -> dict:
        corpo = {"model": self.modelo, "messages": [{"role": "user", "content": pedido}], "format": "json",
                 "stream": False, "options": {"temperature": 0}}
        try:
            r = self.cliente.post(f"{self.endereco}/api/chat", json=corpo, timeout=180)
        except httpx.HTTPError as erro:
            raise ErroIA(f"Não deu para falar com o modelo local em {self.endereco}. O Ollama está aberto?") from erro
        if r.status_code == 404:
            raise ErroIA(f"O modelo local “{self.modelo}” não foi encontrado (no Ollama: ollama pull {self.modelo}).")
        if r.status_code >= 400:
            raise ErroIA(f"O modelo local respondeu com erro (código {r.status_code}).")
        try:
            texto = r.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as erro:
            raise ErroIA("O modelo local não mandou resposta.") from erro
        return _json(texto)


def provedor_configurado(config: ConfigIA, cofre: Cofre, cliente: httpx.Client) -> ProvedorIA | None:
    """O provedor escolhido em Opcionais, ou None (sem IA, o padrão)."""
    if config.provedor == "gemini":
        chave = cofre.ler("gemini")
        if not chave:
            raise ErroIA("Falta a chave do Gemini (em Opcionais).")
        return Gemini(cliente, chave, config.modelo)
    if config.provedor == "local":
        if not config.modelo:
            raise ErroIA("Informe o nome do modelo local (em Opcionais).")
        return ModeloLocal(cliente, config.endereco, config.modelo)
    return None
