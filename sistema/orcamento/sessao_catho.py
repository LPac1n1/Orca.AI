"""Sessão da Catho feita pela própria OSC (pedido de 02/10/2026).

A SEJC pede que a página da vaga mostre as informações da empresa, e a Catho só as mostra para quem está logado. A pessoa entra com a conta
dela numa janela do navegador do sistema (o sistema não digita e-mail nem senha, e não resolve verificações: tudo é feito pela pessoa).
A sessão fica num perfil de navegador só deste computador, fora do OneDrive (%LOCALAPPDATA%\\OrcamentoOSC\\navegador\\catho), e é usada
só para guardar o PDF das vagas escolhidas, poucas páginas por cargo; a busca de vagas continua sem login. "Sair da Catho" apaga o perfil.
"""
import asyncio
import json
import os
import shutil
import threading
import time

from . import db

LOGIN = 'https://www.catho.com.br/signin/'
PRAZO_LOGIN = 15 * 60          # segundos que a janela fica esperando a pessoa entrar e fechar
_trava = threading.Lock()      # um navegador por vez no perfil (o Chromium não abre o mesmo perfil duas vezes)


def perfil():
    return os.path.join(db.PASTA_LOCAL, 'navegador', 'catho')


def _arquivo_estado():
    return os.path.join(db.PASTA_LOCAL, 'navegador', 'catho_estado.json')


def estado():
    """dict(ok, conectada_em, conferida_em, expirou_em, mensagem). ok=True: a última conferência viu as informações da empresa."""
    try:
        with open(_arquivo_estado(), encoding='utf-8') as f:
            e = json.load(f)
    except (OSError, ValueError):
        e = {}
    e['ok'] = bool(e.get('ok')) and os.path.isdir(perfil())
    return e


def _gravar(**k):
    e = estado(); e.update(k)
    os.makedirs(os.path.dirname(_arquivo_estado()), exist_ok=True)
    with open(_arquivo_estado(), 'w', encoding='utf-8') as f:
        json.dump(e, f, ensure_ascii=False)


def tem_sessao():
    return estado()['ok']


def marcar_expirada():
    _gravar(ok=False, expirou_em=db.agora(), mensagem='a sessão da Catho expirou: entre de novo')


def sair():
    """Apaga o perfil do navegador da Catho (a sessão e os cookies ficam só nele)."""
    with _trava:
        shutil.rmtree(perfil(), ignore_errors=True)
    _gravar(ok=False, saiu_em=db.agora(), mensagem='você saiu da Catho neste computador')


def eh_catho(url):
    return 'catho.com.br' in (url or '')


async def _abrir(pw, visivel):
    from .vagas import UA
    os.makedirs(perfil(), exist_ok=True)
    return await pw.chromium.launch_persistent_context(perfil(), headless=not visivel, locale='pt-BR', user_agent=UA,
                                                       viewport=None if visivel else {'width': 1280, 'height': 1000})


async def entrar(ctx, prazo=PRAZO_LOGIN):
    """Abre a janela do navegador do sistema na página de login da Catho e espera a pessoa entrar e FECHAR a janela."""
    from playwright.async_api import async_playwright
    if not _trava.acquire(timeout=10):
        raise ValueError('o navegador da Catho já está aberto por outra tarefa: espere ela terminar')
    try:
        async with async_playwright() as pw:
            c = await _abrir(pw, visivel=True)
            fechou = asyncio.Event()
            c.on('close', lambda *_: fechou.set())
            try:
                pg = c.pages[0] if c.pages else await c.new_page()
                await pg.goto(LOGIN, timeout=60000, wait_until='domcontentloaded')
                await pg.bring_to_front()
                ctx.progresso(10, 'Janela da Catho aberta: entre com a sua conta e, quando terminar, feche a janela')
                fim = time.monotonic() + prazo
                while not fechou.is_set() and time.monotonic() < fim:
                    ctx.verificar_cancelamento()          # "Cancelar a tarefa" fecha a janela
                    await asyncio.sleep(2)
            finally:
                if not fechou.is_set():
                    await c.close()
    finally:
        _trava.release()
    _gravar(conectada_em=db.agora())


async def capturar(url, rotulo, empresa=None):
    """PDF da página da vaga com a sessão da OSC (as informações da empresa aparecem). Devolve (pdf, capturado_em)."""
    from playwright.async_api import async_playwright
    from .vagas import capturar_no_contexto
    if not await asyncio.to_thread(_trava.acquire, True, 300):
        raise ValueError('o navegador da Catho ficou ocupado por mais de 5 minutos')
    try:
        async with async_playwright() as pw:
            c = await _abrir(pw, visivel=False)
            try:
                return await capturar_no_contexto(c, url, rotulo, empresa)
            finally:
                await c.close()
    finally:
        _trava.release()


async def conferir(urls, ctx=None):
    """Confere a sessão abrindo uma vaga da Catho: as informações da empresa aparecem? Devolve True/False (None = nenhuma vaga para conferir)."""
    from .vagas import empresa_oculta, VAGA_ENCERRADA, _texto_pdf
    for url in urls[:4]:
        if ctx:
            ctx.progresso(60, 'Conferindo a sessão numa vaga da Catho')
        try:
            pdf, _ = await asyncio.wait_for(capturar(url, 'conferência da sessão'), 120)
        except Exception:
            continue
        t = _texto_pdf(pdf)
        if VAGA_ENCERRADA.search(t) or 'Sobre a empresa' not in t:
            continue                                   # vaga encerrada ou página diferente: tenta outra
        ok = not empresa_oculta(pdf)
        _gravar(ok=ok, conferida_em=db.agora(), mensagem=None if ok else 'a Catho não reconheceu o login (a página ainda esconde a empresa)')
        return ok
    return None
