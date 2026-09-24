"""Chaves opcionais (SerpApi, Gemini) no Gerenciador de Credenciais do Windows (docs/04 §8).

Nenhuma chave vai para a pasta de dados, para o banco ou para a configuração: a pasta
pode estar no OneDrive e o repositório é público. A interface só sabe se a chave existe;
o valor nunca volta para a tela.
"""

from typing import Protocol

SERVICO = "Orca.AI"
CHAVES = ("serpapi", "gemini")


class ErroCofre(RuntimeError):
    pass


class Cofre(Protocol):
    def ler(self, nome: str) -> str | None: ...
    def gravar(self, nome: str, valor: str) -> None: ...
    def apagar(self, nome: str) -> None: ...


def _conferir(nome: str) -> str:
    if nome not in CHAVES:
        raise ErroCofre(f"Chave desconhecida: {nome}")
    return nome


class CofreDoWindows:
    """Gerenciador de Credenciais do Windows, pela biblioteca keyring."""

    def _keyring(self):
        try:
            import keyring
            from keyring.errors import KeyringError
        except ImportError as erro:  # pragma: no cover — dependência do pacote
            raise ErroCofre("A biblioteca keyring não está instalada.") from erro
        return keyring, KeyringError

    def ler(self, nome: str) -> str | None:
        keyring, KeyringError = self._keyring()
        try:
            return keyring.get_password(SERVICO, _conferir(nome)) or None
        except KeyringError as erro:
            raise ErroCofre(f"Não deu para ler o Gerenciador de Credenciais: {erro}") from erro

    def gravar(self, nome: str, valor: str) -> None:
        keyring, KeyringError = self._keyring()
        try:
            keyring.set_password(SERVICO, _conferir(nome), valor)
        except KeyringError as erro:
            raise ErroCofre(f"Não deu para gravar no Gerenciador de Credenciais: {erro}") from erro

    def apagar(self, nome: str) -> None:
        keyring, KeyringError = self._keyring()
        try:
            keyring.delete_password(SERVICO, _conferir(nome))
        except keyring.errors.PasswordDeleteError:
            pass  # já não existia
        except KeyringError as erro:
            raise ErroCofre(f"Não deu para apagar do Gerenciador de Credenciais: {erro}") from erro


class CofreEmMemoria:
    """Para os testes: nunca toca no Gerenciador de Credenciais de verdade."""

    def __init__(self, **chaves: str):
        self.chaves = {_conferir(k): v for k, v in chaves.items()}

    def ler(self, nome: str) -> str | None:
        return self.chaves.get(_conferir(nome))

    def gravar(self, nome: str, valor: str) -> None:
        self.chaves[_conferir(nome)] = valor

    def apagar(self, nome: str) -> None:
        self.chaves.pop(_conferir(nome), None)
