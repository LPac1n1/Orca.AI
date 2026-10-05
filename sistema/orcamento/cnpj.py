"""Consulta de situação cadastral em APIs públicas gratuitas (espelhos dos dados abertos da Receita), com cache local.
Serve para triagem. O Comprovante oficial da Receita tem CAPTCHA e é emitido pela pessoa (link gerado pelo sistema)."""
import json
import time
import datetime as dt
import httpx

from .db import conectar, agora
from .regras import cnpj_digitos, cnpj_formatar, cnpj_dv_ok

PROVEDORES = [
    ('BrasilAPI', 'https://brasilapi.com.br/api/cnpj/v1/{}', lambda j: (j.get('descricao_situacao_cadastral'), j.get('razao_social'), j.get('data_situacao_cadastral'), j.get('cnae_fiscal_descricao'))),
    ('MinhaReceita', 'https://minhareceita.org/{}', lambda j: (j.get('descricao_situacao_cadastral'), j.get('razao_social'), j.get('data_situacao_cadastral'), j.get('cnae_fiscal_descricao'))),
    ('CNPJá', 'https://open.cnpja.com/office/{}', lambda j: ((j.get('status') or {}).get('text', '').upper() or None, (j.get('company') or {}).get('name'), j.get('statusDate'), (j.get('mainActivity') or {}).get('text'))),
]
URL_COMPROVANTE = 'https://solucoes.receita.fazenda.gov.br/servicos/cnpjreva/cnpjreva_solicitacao.asp'
CACHE_DIAS = 7


def consultar(cnpj, forcar=False):
    c14 = cnpj_digitos(cnpj); fmt = cnpj_formatar(cnpj)
    if not cnpj_dv_ok(c14):
        return dict(cnpj=fmt, situacao='INVÁLIDO', fonte='dígito verificador', consultado_em=agora())
    with conectar() as db:
        row = db.execute('SELECT consultado_em, situacao, json FROM cnpj_cache WHERE cnpj=?', (fmt,)).fetchone()
        if row and not forcar:
            idade = dt.datetime.now().astimezone() - dt.datetime.fromisoformat(row['consultado_em'])
            if idade.days < CACHE_DIAS:
                return json.loads(row['json'])
    for nome, url, extrai in PROVEDORES:
        try:
            r = httpx.get(url.format(c14), timeout=20, headers={'User-Agent': 'orcamento-osc/0.1'})
            if r.status_code == 200:
                sit, razao, data_sit, cnae = extrai(r.json())
                res = dict(cnpj=fmt, situacao=sit, razao_social=razao, data_situacao=data_sit, cnae=cnae, fonte=nome,
                           consultado_em=agora(), resposta=r.json())
                with conectar() as db:
                    db.execute('INSERT OR REPLACE INTO cnpj_cache (cnpj, consultado_em, situacao, json) VALUES (?,?,?,?)',
                               (fmt, res['consultado_em'], sit, json.dumps(res, ensure_ascii=False)))
                return res
        except Exception:
            pass
        time.sleep(0.5)
    return dict(cnpj=fmt, situacao=None, fonte='nenhuma API respondeu', consultado_em=agora())


def do_cache(cnpjs):
    """Somente o que já foi consultado (sem rede): {cnpj_formatado: resultado}."""
    out = {}
    with conectar() as db:
        for c in cnpjs:
            fmt = cnpj_formatar(c)
            row = db.execute('SELECT json FROM cnpj_cache WHERE cnpj=?', (fmt,)).fetchone()
            if row:
                out[fmt] = json.loads(row['json'])
    return out


def situacoes(cnpjs, forcar=False):
    return {cnpj_formatar(c): consultar(c, forcar).get('situacao') for c in cnpjs if c}
