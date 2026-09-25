"""Lojas que o sistema sabe pesquisar (Fase 2, etapa 10), a partir do catálogo de lojas.

Cada loja do catálogo pode ter `busca`:
- `modo: api_vtex` — API pública de catálogo VTEX (busca por texto e por código de barras);
- `modo: api_vtex_is` — busca pública das lojas VTEX mais novas ("intelligent search"; texto e código de barras);
- `modo: api_woocommerce` — API pública de produtos das lojas WooCommerce (WordPress);
- `modo: pagina` — a página de busca do próprio site, aberta pelo navegador sem janela;
  `produto` é o pedaço do endereço que identifica a página de um produto e `seletor` (opcional)
  é a lista de resultados na página: fora dela (menus, "sugestões", "vistos por último") nada é lido;
- `modo: assistida` — a loja recusa programas (D-67) ou o robots.txt proíbe a busca por programas:
  a janela abre na busca e a pessoa escolhe.
Sem `busca`, a loja só entra colando o link. Antes de ligar a busca automática de uma loja, confira
o robots.txt dela (levantamento em docs/07 §5).
"""

from dataclasses import dataclass
from urllib.parse import quote

MODOS_AUTOMATICOS = ("api_vtex", "api_vtex_is", "api_woocommerce", "pagina")
MODOS_COM_EAN = ("api_vtex", "api_vtex_is")  # buscas que aceitam o código de barras

# categoria do item → categoria do catálogo de lojas
CATEGORIA_DA_LOJA = {
    "papel": "papelaria", "caneta": "papelaria", "papelaria": "papelaria",
    "alimento": "alimentos", "bebida": "bebidas",
    "limpeza": "limpeza", "higiene": "limpeza", "descartavel": "descartaveis", "utensilio": "utensilios",
    "eletronico": "informatica",
}


@dataclass(frozen=True)
class LojaDeBusca:
    id: str
    nome: str
    dominio: str
    modo: str  # api_vtex | pagina | assistida
    url: str
    produto: str | None
    categorias: tuple[str, ...]
    seletor: str | None = None  # a lista de resultados na página de busca (modo pagina)

    @property
    def automatica(self) -> bool:
        return self.modo in MODOS_AUTOMATICOS

    @property
    def aceita_ean(self) -> bool:
        return self.modo in MODOS_COM_EAN

    def endereco(self, termo: str) -> str:
        """Endereço da busca (para a página e para a janela da captura assistida)."""
        return self.url.replace("{termo}", quote(termo)) if "{termo}" in self.url else self.url

    def atende(self, categorias_dos_itens: set[str | None]) -> bool:
        """A loja vende todas as categorias do lote (itens sem categoria não restringem)."""
        pedidas = {CATEGORIA_DA_LOJA.get(c or "", c) for c in categorias_dos_itens if c}
        return pedidas <= set(self.categorias)


def lojas_de_busca(catalogo: dict) -> list[LojaDeBusca]:
    """As lojas do catálogo (já com as mudanças da OSC) que têm busca configurada."""
    lojas = []
    for entrada in catalogo.get("lojas") or []:
        busca = entrada.get("busca")
        if not isinstance(busca, dict) or busca.get("modo") not in (*MODOS_AUTOMATICOS, "assistida") or not busca.get("url"):
            continue
        lojas.append(LojaDeBusca(
            id=entrada["id"], nome=entrada["nome"], dominio=entrada["dominio"], modo=busca["modo"], url=busca["url"],
            produto=busca.get("produto"), categorias=tuple(entrada.get("categorias") or ()),
            seletor=busca.get("seletor") or None,
        ))
    return lojas
