"""Busca automática de produtos nas lojas (Fase 2, etapa 10; D-68).

A busca só aponta o caminho: para cada item, o sistema pergunta à loja (API pública ou
página de busca), escolhe o melhor candidato e captura a página do produto, que é a prova
— exatamente como se a pessoa tivesse colado o link.
"""

from orca.busca.conectores import Consulta, ErroBusca, Ritmo, buscar_na_pagina, buscar_vtex, candidatos_da_pagina
from orca.busca.lojas import CATEGORIA_DA_LOJA, LojaDeBusca, lojas_de_busca
from orca.busca.vagas import PlataformaDeVagas, ler_plataformas, plataforma_do_endereco, plataformas_de_vagas
from orca.busca.ranking import (
    Candidato,
    CandidatoAvaliado,
    avaliar_candidatos,
    bom_o_bastante,
    ordem_dos_itens,
    parecenca,
    termo_curto,
    termo_de_busca,
    titulo_do_endereco,
)

__all__ = [
    "CATEGORIA_DA_LOJA",
    "Candidato",
    "CandidatoAvaliado",
    "Consulta",
    "ErroBusca",
    "LojaDeBusca",
    "PlataformaDeVagas",
    "Ritmo",
    "avaliar_candidatos",
    "bom_o_bastante",
    "buscar_na_pagina",
    "buscar_vtex",
    "candidatos_da_pagina",
    "ler_plataformas",
    "lojas_de_busca",
    "ordem_dos_itens",
    "parecenca",
    "plataforma_do_endereco",
    "plataformas_de_vagas",
    "termo_curto",
    "termo_de_busca",
    "titulo_do_endereco",
]
