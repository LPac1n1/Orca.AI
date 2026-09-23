"""Armazém de arquivos de evidência, endereçados pelo conteúdo (docs/04 §4).

Cada arquivo é gravado em `evidencias/ab/cd/<sha256>.<ext>`: o nome é a impressão
digital do conteúdo. Nada é sobrescrito; ao ler, a impressão é conferida. Os arquivos
ficam marcados como somente leitura.
"""

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

EXTENSOES = {
    "application/pdf": "pdf",
    "image/png": "png",
    "multipart/related": "mhtml",
    "text/html": "html",
    "application/json": "json",
}


class ErroIntegridade(RuntimeError):
    """O arquivo gravado não confere com a impressão digital."""


@dataclass(frozen=True)
class ArquivoGuardado:
    sha256: str
    caminho: str  # relativo à pasta de dados, com "/"
    tipo_mime: str
    tamanho: int


def impressao(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


class ArmazemArquivos:
    def __init__(self, pasta_dados: Path | str):
        self.raiz = Path(pasta_dados)

    def _relativo(self, sha: str, tipo_mime: str) -> str:
        if tipo_mime not in EXTENSOES:
            raise ValueError(f"Tipo de arquivo não aceito: {tipo_mime}")
        return f"evidencias/{sha[:2]}/{sha[2:4]}/{sha}.{EXTENSOES[tipo_mime]}"

    def guardar(self, conteudo: bytes, tipo_mime: str) -> ArquivoGuardado:
        sha = impressao(conteudo)
        relativo = self._relativo(sha, tipo_mime)
        destino = self.raiz / relativo
        if destino.exists():
            if impressao(destino.read_bytes()) != sha:
                raise ErroIntegridade(f"O arquivo {relativo} existe mas foi alterado")
        else:
            destino.parent.mkdir(parents=True, exist_ok=True)
            temporario = destino.with_suffix(destino.suffix + ".tmp")
            temporario.write_bytes(conteudo)
            os.replace(temporario, destino)
            destino.chmod(stat.S_IREAD)  # somente leitura
        return ArquivoGuardado(sha, relativo, tipo_mime, len(conteudo))

    def ler(self, caminho_relativo: str) -> bytes:
        """Lê e confere a impressão digital (o nome do arquivo)."""
        caminho = self.raiz / caminho_relativo
        conteudo = caminho.read_bytes()
        esperado = caminho.stem
        if impressao(conteudo) != esperado:
            raise ErroIntegridade(f"O arquivo {caminho_relativo} foi alterado depois de gravado")
        return conteudo
