"""Monta o conjunto de referência de correspondência (T-11): testes/dados/correspondencia/pares_referencia.csv.

Uso (fora dos testes; acessa a internet com poucas consultas):
    python ferramentas/montar_pares_referencia.py baixar <pasta>
    python ferramentas/montar_pares_referencia.py montar <pasta>

Fontes:
- Atacadão: API pública de busca (a loja do catálogo com dados abertos, coleta C0);
  20 consultas, uma por termo.
- Open Food Facts (base aberta, ODbL): busca por marca e consulta por código de barras.

Como os rótulos são dados (ver LEIAME.md):
- "mesmo": o mesmo código de barras nas duas fontes, com nomes escritos de outro jeito.
  Pares com cadastro claramente errado ou quantidade divergente ficam de fora.
- "diferente": dois produtos do Atacadão com códigos diferentes, em que cada título tem
  uma característica que o outro não tem (tamanho, sabor, tipo, fragrância, medidas…),
  revisados um a um; ou o mesmo produto de marcas diferentes. Se um título só omite
  uma palavra do outro, o par é ambíguo e fica de fora.
"""

import csv
import itertools
import json
import random
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orca.correspondencia.texto import PALAVRAS_VAZIAS, compacto, normalizar  # noqa: E402

CSV = Path(__file__).resolve().parents[1] / "testes" / "dados" / "correspondencia" / "pares_referencia.csv"
COLUNAS = ["id", "categoria", "loja_a", "titulo_a", "marca_a", "ean_a", "loja_b", "titulo_b", "marca_b", "ean_b",
           "rotulo", "motivo", "origem_titulos", "coletado_em"]
AGENTE = "Orca.AI/0.1 (github.com/LPac1n1/Orca.AI; montador de orcamentos para OSCs)"
TERMOS = ["cafe pilao", "cafe melitta", "cafe 3 coracoes", "acucar", "arroz", "feijao", "leite", "oleo de soja",
          "macarrao", "biscoito", "achocolatado", "suco", "detergente", "agua sanitaria", "sabao em po",
          "papel higienico", "copo descartavel", "guardanapo", "papel sulfite", "desinfetante"]
CAMPOS_OFF = "code,product_name,product_name_pt,generic_name_pt,brands,quantity"

# Revisão humana dos pares (feita em 23/09/2026)
EXCLUIR_MESMO = {
    "7896005803721": "o Open Food Facts cadastrou outro produto (biscoito) com este código",
    "7898080640673": "quantidade diverge entre as fontes (400 g × 500 g)",
    "7896045104147": "quantidade diverge entre as fontes (560 g × 400 g)",
    "7898152990170": "nome traduzido e errado no Open Food Facts",
}
EXCLUIR_DIFERENTE = {
    frozenset({"7896348300772", "7896348300765"}): "mesmo filtro em edições promocionais diferentes (ambíguo)",
    frozenset({"7896006400011", "51663924"}): "20x22 cm × 22x20 cm: mesmas medidas (ambíguo)",
}
CATEGORIAS = {
    "Mercearia": "alimento", "Padaria e matinais": "alimento", "Frios e congelados": "alimento",
    "Hortifrúti": "alimento", "Suplementos alimentares": "alimento", "Bebidas": "bebida", "Limpeza": "limpeza",
    "Higiene e perfumaria": "higiene", "Descartáveis e embalagens": "descartavel", "Papelaria": "papel",
}
# Os 10 primeiros pares (levantamento de lojas, 23/09/2026): categoria e marcas
PRIMEIROS = {
    "1": ("alimento", "Pilão", "Pilão"), "2": ("alimento", "Pilão", "Pilão"), "3": ("alimento", "Pilão", "Pilão"),
    "4": ("alimento", "Pilão", "Bulnez"), "5": ("alimento", "Pilão", "Pilão"), "6": ("papel", "Chamex", ""),
    "7": ("papel", "Chamex", ""), "8": ("papel", "Chamex", ""), "9": ("papel", "Paper One", ""),
    "10": ("papel", "Chamex", ""),
}
PAPEL_MESMO = [  # títulos copiados das páginas em 23/09/2026
    ("kalunga", "Papel Sulfite A4, 75g, 210mmx297mm, Chamex - PT 500 FL", "Chamex", "7891173023001",
     "amazon", "Chamex - Papel Sulfite, A4, 75g, 500 folhas", "", ""),
]


def baixar(pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    cliente = httpx.Client(headers={"User-Agent": AGENTE}, timeout=60, follow_redirects=True)
    produtos = {}
    for termo in TERMOS:
        r = cliente.get("https://www.atacadao.com.br/api/catalog_system/pub/products/search",
                        params={"ft": termo, "_from": 0, "_to": 49})
        for p in r.json() if r.status_code in (200, 206) else []:
            for item in p.get("items", []):
                if item.get("ean"):
                    produtos[item["ean"]] = {"ean": item["ean"], "titulo": p.get("productName"), "marca": p.get("brand"),
                                             "categoria": (p.get("categories") or [""])[0], "termo": termo}
        time.sleep(1.5)
    (pasta / "atacadao.json").write_text(json.dumps(list(produtos.values()), ensure_ascii=False, indent=1), "utf-8")

    def etiqueta(marca):
        s = "".join(c for c in unicodedata.normalize("NFD", marca.lower()) if unicodedata.category(c) != "Mn")
        return re.sub(r"[^a-z0-9]+", "-", s).strip("-")

    off = {}
    marcas = [m for m, n in Counter(etiqueta(p["marca"]) for p in produtos.values() if p["marca"]).most_common(30) if n >= 4]
    for marca in marcas:
        r = cliente.get("https://world.openfoodfacts.org/api/v2/search", params={
            "brands_tags": marca, "countries_tags_en": "brazil", "page_size": 200, "fields": CAMPOS_OFF})
        for p in r.json().get("products", []) if r.status_code == 200 else []:
            off[p["code"]] = p
        time.sleep(7)  # limite do Open Food Facts para buscas
    for ean in [e for e, p in produtos.items() if p["termo"].startswith("cafe") and e not in off][:80]:
        r = cliente.get(f"https://world.openfoodfacts.org/api/v2/product/{ean}.json", params={"fields": CAMPOS_OFF})
        if r.status_code == 200 and r.json().get("status") == 1:
            off[ean] = {**r.json()["product"], "code": ean}
        time.sleep(1)
    (pasta / "off.json").write_text(json.dumps(off, ensure_ascii=False, indent=1), "utf-8")


def _categoria(caminho: str) -> str:
    return CATEGORIAS.get(caminho.strip("/").split("/")[0], "")


def _palavras(titulo: str) -> set[str]:
    t = re.sub(r"(\d)\s+(g|kg|ml|l|un|m|cm)\b", r"\1\2", normalizar(titulo))
    return {w for w in re.findall(r"[a-z0-9,]+", t) if w not in PALAVRAS_VAZIAS}


def _titulo_off(p: dict) -> str | None:
    nome = (p.get("product_name_pt") or p.get("product_name") or "").strip()
    if len(re.findall(r"[a-zA-Zà-ú]{2,}", nome)) < 2:
        return None  # nome genérico demais ("Café", "Tradicional")
    quantidade = (p.get("quantity") or "").strip()
    if re.search(r"\d\s*(g|kg|ml|l|un)\b", quantidade, re.I) and compacto(quantidade) not in compacto(nome):
        nome = f"{nome} {quantidade}"
    return nome


def montar(pasta: Path) -> None:
    atacadao = json.loads((pasta / "atacadao.json").read_text("utf-8"))
    off = json.loads((pasta / "off.json").read_text("utf-8"))
    por_ean = {p["ean"]: p for p in atacadao}
    linhas = []

    with CSV.open(encoding="utf-8") as f:  # os 10 primeiros pares, revisados à mão
        for r in csv.DictReader(f):
            if r["id"] in PRIMEIROS:
                categoria, marca_a, marca_b = PRIMEIROS[r["id"]]
                linhas.append({**{k: r.get(k, "") for k in COLUNAS}, "categoria": categoria, "marca_a": marca_a, "marca_b": marca_b})

    for loja_a, ta, ma, ea, loja_b, tb, mb, eb in PAPEL_MESMO:
        linhas.append({"categoria": "papel", "loja_a": loja_a, "titulo_a": ta, "marca_a": ma, "ean_a": ea, "loja_b": loja_b,
                       "titulo_b": tb, "marca_b": mb, "ean_b": eb, "rotulo": "mesmo",
                       "motivo": "mesma marca, formato, gramatura e nº de folhas", "origem_titulos": "pagina",
                       "coletado_em": "2026-09-23"})
    chamex = [p for p in atacadao if p["titulo"] == "Papel Sulfite Chamex A4 75g 500 folhas"]
    if chamex:
        p = chamex[0]
        linhas.append({"categoria": "papel", "loja_a": "atacadao", "titulo_a": p["titulo"], "marca_a": p["marca"],
                       "ean_a": p["ean"], "loja_b": "kalunga", "titulo_b": PAPEL_MESMO[0][1], "marca_b": "Chamex",
                       "ean_b": PAPEL_MESMO[0][3], "rotulo": "mesmo",
                       "motivo": "mesma marca, formato, gramatura e nº de folhas", "origem_titulos": "api+pagina",
                       "coletado_em": "2026-09-23"})

    # "mesmo": mesmo código de barras no Atacadão e no Open Food Facts
    for ean in sorted(set(por_ean) & set(off)):
        if ean in EXCLUIR_MESMO:
            continue
        a, o = por_ean[ean], off[ean]
        titulo_b = _titulo_off(o)
        if not titulo_b or normalizar(titulo_b) == normalizar(a["titulo"]):
            continue
        linhas.append({"categoria": _categoria(a["categoria"]), "loja_a": "atacadao", "titulo_a": a["titulo"],
                       "marca_a": a["marca"], "ean_a": ean, "loja_b": "openfoodfacts", "titulo_b": titulo_b,
                       "marca_b": (o.get("brands") or "").split(",")[0].strip(), "ean_b": ean, "rotulo": "mesmo",
                       "motivo": "mesmo código de barras; nomes escritos de outro jeito", "origem_titulos": "api+off",
                       "coletado_em": "2026-09-23"})

    # "diferente": mesma marca, cada título com uma característica que o outro não tem
    grupos = defaultdict(list)
    for p in atacadao:
        grupos[(p["termo"], (p["marca"] or "").lower())].append(p)
    candidatos = []
    for (termo, _), produtos in grupos.items():
        vistos = set()
        for a, b in itertools.combinations(produtos, 2):
            if a["ean"] == b["ean"] or normalizar(a["titulo"]) == normalizar(b["titulo"]):
                continue
            sa, sb = _palavras(a["titulo"]) - _palavras(b["titulo"]), _palavras(b["titulo"]) - _palavras(a["titulo"])
            if not sa or not sb or len(sa) + len(sb) > 4:
                continue
            chave = (tuple(sorted(sa)), tuple(sorted(sb)))
            if chave not in vistos:
                vistos.add(chave)
                candidatos.append((termo, a, b, sorted(sa), sorted(sb)))
    random.seed(7)
    por_termo = defaultdict(list)
    for c in candidatos:
        por_termo[c[0]].append(c)
    for termo, lista in por_termo.items():
        random.shuffle(lista)
        for _, a, b, sa, sb in lista[:14]:
            if frozenset({a["ean"], b["ean"]}) in EXCLUIR_DIFERENTE:
                continue
            linhas.append({"categoria": _categoria(a["categoria"]), "loja_a": "atacadao", "titulo_a": a["titulo"],
                           "marca_a": a["marca"], "ean_a": a["ean"], "loja_b": "atacadao", "titulo_b": b["titulo"],
                           "marca_b": b["marca"], "ean_b": b["ean"], "rotulo": "diferente",
                           "motivo": f"{' '.join(sa)} × {' '.join(sb)}", "origem_titulos": "api", "coletado_em": "2026-09-23"})

    # "diferente": o mesmo produto de outra marca
    sem_marca = defaultdict(list)
    for p in atacadao:
        if p["marca"]:
            chave = re.sub(r"\s+", " ", normalizar(p["titulo"]).replace(normalizar(p["marca"]), " ")).strip()
            sem_marca[(_categoria(p["categoria"]), chave)].append(p)
    trocas = []
    for (categoria, _), produtos in sem_marca.items():
        for a, b in itertools.combinations(produtos, 2):
            if compacto(a["marca"]) != compacto(b["marca"]):
                trocas.append((categoria, a, b))
    random.shuffle(trocas)
    for categoria, a, b in trocas[:30]:
        linhas.append({"categoria": categoria, "loja_a": "atacadao", "titulo_a": a["titulo"], "marca_a": a["marca"],
                       "ean_a": a["ean"], "loja_b": "atacadao", "titulo_b": b["titulo"], "marca_b": b["marca"],
                       "ean_b": b["ean"], "rotulo": "diferente", "motivo": f"marca {a['marca']} × {b['marca']}",
                       "origem_titulos": "api", "coletado_em": "2026-09-23"})

    with CSV.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUNAS, lineterminator="\n")
        escritor.writeheader()
        for i, linha in enumerate(linhas, 1):
            escritor.writerow({**{k: linha.get(k, "") for k in COLUNAS}, "id": i})
    rotulos = Counter(l["rotulo"] for l in linhas)
    print(f"{len(linhas)} pares: {dict(rotulos)}")


if __name__ == "__main__":
    acao, pasta = sys.argv[1], Path(sys.argv[2])
    {"baixar": baixar, "montar": montar}[acao](pasta)
