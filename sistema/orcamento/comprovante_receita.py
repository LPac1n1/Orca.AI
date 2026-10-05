"""Comprovante OFICIAL de Inscrição e de Situação Cadastral (Receita Federal) de cada CNPJ do projeto.

A página oficial de emissão tem CAPTCHA (hCaptcha): o sistema NÃO resolve CAPTCHA. Por isso o caminho é:
 1. o sistema abre a página oficial já com o CNPJ preenchido (um clique por empresa);
 2. a pessoa resolve o CAPTCHA, clica em Consultar e salva a página em PDF (Ctrl+P → Salvar como PDF) na pasta "Orça.AI", em Documentos
    (decisão da OSC, 05/10/2026: é a pasta dos comprovantes, no lugar de Downloads);
 3. o sistema importa os PDFs (dessa pasta ou enviados pela tela), CONFERE que é o comprovante oficial, que o CNPJ é do projeto e que a
    situação é ATIVA, e guarda o arquivo com SHA-256 como evidência do CNPJ.
Enquanto o comprovante não é importado, a situação vem da base oficial de dados abertos da Receita (mensal), só como informação."""
import datetime as dt
import glob
import os
import re
import sys

URL_EMISSAO = 'https://solucoes.receita.fazenda.gov.br/Servicos/cnpjreva/Cnpjreva_Solicitacao.asp?cnpj={}'
TITULO = re.compile(r'COMPROVANTE\s+DE\s+INSCRI[ÇC][ÃA]O\s+E\s+DE\s+SITUA[ÇC][ÃA]O\s+CADASTRAL', re.I)
CNPJ = re.compile(r'\b(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})\b')
SITUACAO = re.compile(r'SITUA[ÇC][ÃA]O\s+CADASTRAL\s+(ATIVA|BAIXADA|INAPTA|SUSPENSA|NULA)\b', re.I)
EMITIDO = re.compile(r'Emitido\s+no\s+dia\s+(\d{2})/(\d{2})/(\d{4})(?:\s+[àa]s\s+(\d{2}:\d{2}(?::\d{2})?))?', re.I)
NOME = re.compile(r'NOME\s+EMPRESARIAL\s+(.{3,150}?)\s+T[ÍI]TULO\s+DO\s+ESTABELECIMENTO', re.I | re.S)


def url_emissao(cnpj):
    return URL_EMISSAO.format(re.sub(r'\D', '', cnpj or ''))


def ler(pdf):
    """dict(cnpj, situacao, emitido_em, razao) se o PDF é o comprovante oficial; None se não é."""
    try:
        import pymupdf
        texto = ''.join(pg.get_text() for pg in pymupdf.open(stream=pdf, filetype='pdf'))
    except Exception:
        return None
    t = re.sub(r'\s+', ' ', texto)
    if not TITULO.search(t):
        return None
    c, s, e, n = CNPJ.search(t), SITUACAO.search(t), EMITIDO.search(t), NOME.search(t)
    if not c:
        return None
    emitido = f'{e.group(3)}-{e.group(2)}-{e.group(1)}' + (f'T{e.group(4)}' if e.group(4) else '') if e else None
    return dict(cnpj=c.group(1), situacao=s.group(1).upper() if s else None, emitido_em=emitido, razao=n.group(1).strip() if n else None)


def conferir(info, cnpjs_do_projeto, validade_dias=180):
    """Problema do comprovante para o projeto (None se serve)."""
    if not info:
        return 'o arquivo não é o Comprovante de Inscrição e de Situação Cadastral da Receita'
    if info['cnpj'] not in cnpjs_do_projeto:
        return f'o CNPJ {info["cnpj"]} não é de nenhuma empresa do projeto'
    if info['situacao'] != 'ATIVA':
        return f'situação cadastral {info["situacao"] or "não lida"} (precisa ser ATIVA — R07)'
    if info['emitido_em'] and dt.date.fromisoformat(info['emitido_em'][:10]) < dt.date.today() - dt.timedelta(days=validade_dias):
        return f'comprovante emitido em {info["emitido_em"][:10]}: mais antigo que {validade_dias} dias'
    return None


PASTA = 'Orça.AI'   # dentro de Documentos


def pasta_documentos():
    """A pasta Documentos de verdade deste computador. No Windows ela pode estar no OneDrive (C:\\Users\\nome\\OneDrive\\Documentos): vale a
    que o Windows aponta, que é a que aparece como "Documentos" na janela de salvar."""
    if sys.platform == 'win32':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as h:
                p = os.path.expandvars(str(winreg.QueryValueEx(h, 'Personal')[0]))
            if p and os.path.isdir(p):
                return p
        except OSError:
            pass
    casa = os.path.expanduser('~')
    return next((p for p in (os.path.join(casa, 'Documents'), os.path.join(casa, 'Documentos')) if os.path.isdir(p)), os.path.join(casa, 'Documents'))


def pasta_dos_comprovantes(criar=False):
    """Onde a OSC salva os comprovantes emitidos na Receita: a pasta "Orça.AI", em Documentos. criar=True: cria a pasta se ainda não existir."""
    p = os.environ.get('ORCAMENTO_COMPROVANTES') or os.path.join(pasta_documentos(), PASTA)
    if criar:
        try:
            os.makedirs(p, exist_ok=True)
        except OSError:
            pass
    return p


_LIDOS = {}   # (caminho, data, tamanho) → o que o PDF é: não relê o mesmo arquivo a cada consulta da tela


def baixados(pasta=None, dias=None):
    """Comprovantes oficiais que JÁ ESTÃO na pasta dos comprovantes, ainda não importados: {CNPJ: dict(arquivo, situacao, emitido_em)}.
    Serve para a tela mostrar, antes de importar, quais empresas já tiveram o comprovante salvo (pedido da OSC, 05/10/2026)."""
    out = {}
    for a in pdfs_recentes(pasta, dias):
        try:
            chave = (a, os.path.getmtime(a), os.path.getsize(a))
            if chave not in _LIDOS:
                with open(a, 'rb') as fh:
                    _LIDOS[chave] = ler(fh.read())
            info = _LIDOS[chave]
        except OSError:
            continue
        if info and (info['cnpj'] not in out or (info['emitido_em'] or '') > (out[info['cnpj']]['emitido_em'] or '')):
            out[info['cnpj']] = dict(arquivo=os.path.basename(a), situacao=info['situacao'], emitido_em=info['emitido_em'])
    return out


def pdfs_recentes(pasta=None, dias=None):
    """PDFs da pasta dos comprovantes ("Orça.AI", em Documentos), ou de outra pasta. dias: só os salvos nos últimos dias (padrão: todos — a
    pasta é só dos comprovantes, e a validade de cada um é conferida pela data de emissão)."""
    pasta = pasta or pasta_dos_comprovantes()
    arquivos = glob.glob(os.path.join(glob.escape(pasta), '*.pdf'))
    if dias is None:
        return arquivos
    limite = dt.datetime.now().timestamp() - dias * 86400
    return [a for a in arquivos if os.path.getmtime(a) >= limite]
