{% raw %}
/* Orça.AI — comportamento comum das telas (sem bibliotecas externas).
   Tudo aqui é melhoria progressiva: sem JavaScript os formulários continuam funcionando, só sem máscara e sem as janelas de confirmação. */
(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* ------------------------------------------------------------------ avisos rápidos (toasts) */
  function toast(msg, tipo, ms) {
    var area = $('#toasts');
    if (!area) { return; }
    var t = document.createElement('div');
    t.className = 'toast' + (tipo ? ' toast--' + tipo : '');
    t.setAttribute('role', tipo === 'erro' ? 'alert' : 'status');
    var txt = document.createElement('span'); txt.textContent = msg; t.appendChild(txt);
    var b = document.createElement('button'); b.type = 'button'; b.setAttribute('aria-label', 'Fechar aviso'); b.textContent = '✕';
    b.addEventListener('click', function () { t.remove(); });
    t.appendChild(b); area.appendChild(t);
    setTimeout(function () { t.remove(); }, ms || (tipo === 'erro' ? 9000 : 5000));
  }

  /* ------------------------------------------------------------------ máscaras */
  function soDigitos(v) { return (v || '').replace(/\D/g, ''); }
  function milhar(d) { return d.replace(/\B(?=(\d{3})+(?!\d))/g, '.'); }

  function moedaDigitando(v) {
    v = (v || '').replace(/[^\d,]/g, '');
    var i = v.indexOf(',');
    var inteiro = (i < 0 ? v : v.slice(0, i)).replace(/^0+(?=\d)/, '');
    if (i < 0) { return milhar(inteiro); }
    return milhar(inteiro || '0') + ',' + v.slice(i + 1).replace(/,/g, '').slice(0, 2);
  }
  function moedaFinal(v) {
    v = (v || '').trim().replace(/^R\$\s*/i, '');
    if (/^\d+\.\d{1,2}$/.test(v)) { v = v.replace('.', ','); }          /* valor colado no formato 1234.56 */
    v = moedaDigitando(v);
    if (!v) { return ''; }
    var p = v.split(',');
    return p[0] + ',' + ((p[1] || '') + '00').slice(0, 2);
  }
  function centavos(v) { var d = soDigitos(moedaFinal(v)); return d ? parseInt(d, 10) : NaN; }

  var MASCARAS = {
    moeda: { digitando: moedaDigitando, fim: moedaFinal },
    cnpj: { digitando: function (v) {
      var d = soDigitos(v).slice(0, 14), o = d.slice(0, 2);
      if (d.length > 2) { o += '.' + d.slice(2, 5); }
      if (d.length > 5) { o += '.' + d.slice(5, 8); }
      if (d.length > 8) { o += '/' + d.slice(8, 12); }
      if (d.length > 12) { o += '-' + d.slice(12); }
      return o;
    } },
    cep: { digitando: function (v) { var d = soDigitos(v).slice(0, 8); return d.length > 5 ? d.slice(0, 5) + '-' + d.slice(5) : d; } },
    inteiro: { digitando: function (v) { return soDigitos(v).replace(/^0+(?=\d)/, '').slice(0, 6); } },
    percentual: { digitando: function (v) {
      v = (v || '').replace('.', ',').replace(/[^\d,]/g, '');
      var i = v.indexOf(',');
      return i < 0 ? v.slice(0, 3) : v.slice(0, i).slice(0, 3) + ',' + v.slice(i + 1).replace(/,/g, '').slice(0, 1);
    } }
  };

  function cnpjValido(d) {
    if (d.length !== 14 || /^(\d)\1+$/.test(d)) { return false; }
    function dv(base, pesos) { var s = 0; for (var i = 0; i < base.length; i++) { s += parseInt(base[i], 10) * pesos[i]; } var r = s % 11; return r < 2 ? 0 : 11 - r; }
    var p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], d1 = dv(d.slice(0, 12), p1);
    return d1 === parseInt(d[12], 10) && dv(d.slice(0, 13), [6].concat(p1)) === parseInt(d[13], 10);
  }

  /* reformata sem jogar o cursor para o fim: conta os caracteres "de verdade" antes do cursor e reposiciona depois */
  function aplicarMascara(el) {
    var m = MASCARAS[el.dataset.mascara];
    if (!m) { return; }
    var antes = el.value, novo = m.digitando(antes);
    if (novo === antes) { return; }
    var pos = el.selectionStart, util = /[\d,]/;
    var vistos = antes.slice(0, pos == null ? antes.length : pos).split('').filter(function (c) { return util.test(c); }).length;
    el.value = novo;
    if (document.activeElement !== el || pos == null) { return; }
    var i = 0, n = 0;
    while (i < novo.length && n < vistos) { if (util.test(novo[i])) { n++; } i++; }
    try { el.setSelectionRange(i, i); } catch (e) { /* tipos de campo sem seleção */ }
  }
  function finalizar(el) {
    var m = MASCARAS[el.dataset.mascara];
    if (m) { el.value = (m.fim || m.digitando)(el.value); }
    else if (el.type === 'text' || el.type === 'url' || el.tagName === 'TEXTAREA') {
      if (el.tagName === 'TEXTAREA') { el.value = el.value.replace(/[ \t]+$/gm, '').replace(/^\s+|\s+$/g, ''); }
      else { el.value = el.value.replace(/\s+/g, ' ').trim(); }                    /* espaços sobrando */
    }
  }

  /* ------------------------------------------------------------------ validação com mensagem embaixo do campo */
  function nomeDoCampo(el) {
    var l = el.id ? $('label[for="' + el.id + '"]') : null;
    var t = l ? l.textContent : (el.getAttribute('aria-label') || 'este campo');
    return t.replace(/\(obrigatório\)|\(opcional\)|\*|\?/g, '').replace(/\s+/g, ' ').trim();
  }
  function mensagemDeErro(el) {
    if (el.disabled || el.type === 'hidden' || el.type === 'submit' || el.type === 'button') { return ''; }
    var v = (el.value || '').trim(), m = el.dataset.mascara, d;
    if (el.type === 'file') {
      if (el.required && !el.files.length) { return 'Escolha o arquivo antes de enviar.'; }
      for (var i = 0; i < el.files.length; i++) { if (!/\.pdf$/i.test(el.files[i].name)) { return 'O arquivo "' + el.files[i].name + '" não é um PDF. Salve ou imprima em PDF e escolha de novo.'; } }
      return '';
    }
    if (el.required && !v) { return 'Preencha o campo "' + nomeDoCampo(el) + '".'; }
    if (!v) { return ''; }
    if (m === 'cnpj') {
      d = soDigitos(v);
      if (d.length < 14) { return 'CNPJ incompleto: são 14 números (faltam ' + (14 - d.length) + ').'; }
      if (!cnpjValido(d)) { return 'CNPJ inválido — confira os dígitos.'; }
    }
    if (m === 'cep' && soDigitos(v).length !== 8) { return 'CEP incompleto: são 8 números (ex.: 01001-000).'; }
    if (m === 'moeda') {
      var c = centavos(v);
      if (isNaN(c)) { return 'Valor inválido. Digite só números (ex.: 1.234,56).'; }
      if (el.dataset.positivo !== undefined && c <= 0) { return 'O valor precisa ser maior que zero.'; }
    }
    if (m === 'inteiro' || m === 'percentual') {
      var n = parseFloat(v.replace(',', '.'));
      if (isNaN(n)) { return 'Digite um número.'; }
      if (el.dataset.min !== undefined && n < parseFloat(el.dataset.min)) { return 'O menor valor aceito é ' + el.dataset.min + '.'; }
      if (el.dataset.max !== undefined && n > parseFloat(el.dataset.max)) { return 'O maior valor aceito é ' + el.dataset.max + '.'; }
    }
    if (el.type === 'url') {                                                    /* algumas lojas publicam o endereço com espaço no meio: vira %20 (o endereço continua o mesmo) */
      if (/\s/.test(v)) { v = v.replace(/\s/g, '%20'); el.value = v; }
      if (!/^https?:\/\/[^\s.]+\.\S+$/i.test(v)) { return 'Endereço incompleto. Copie o endereço inteiro, começando por https://'; }
    }
    if (el.type === 'date') {
      if (el.validity && el.validity.badInput) { return 'Data inválida. Use dia, mês e ano (ex.: 02/10/2026).'; }
      if (el.dataset.naoFutura !== undefined && v > new Date().toISOString().slice(0, 10)) { return 'A data da pesquisa não pode ser futura.'; }
    }
    if (el.dataset.igual !== undefined && v.replace(/\s+/g, ' ').trim() !== el.dataset.igual.replace(/\s+/g, ' ').trim()) {
      return 'O texto digitado é diferente. Digite exatamente: ' + el.dataset.igual;
    }
    return '';
  }
  function mostrarErro(el, msg) {
    var id = el.id || (el.id = 'campo-' + Math.random().toString(36).slice(2, 8));
    var p = document.getElementById(id + '-erro');
    if (!p) {
      p = document.createElement('p'); p.className = 'campo__erro'; p.id = id + '-erro'; p.hidden = true;
      var alvo = el.closest('.campo__grupo') || el;
      alvo.parentNode.insertBefore(p, alvo.nextSibling);
    }
    var desc = (el.getAttribute('aria-describedby') || '').split(' ').filter(function (x) { return x && x !== p.id; });
    if (msg) {
      p.textContent = msg; p.hidden = false; el.setAttribute('aria-invalid', 'true'); desc.push(p.id);
    } else {
      p.textContent = ''; p.hidden = true; el.removeAttribute('aria-invalid');
    }
    if (desc.length) { el.setAttribute('aria-describedby', desc.join(' ')); } else { el.removeAttribute('aria-describedby'); }
    return !msg;
  }
  function validar(el) { return mostrarErro(el, mensagemDeErro(el)); }

  document.addEventListener('input', function (e) {
    var el = e.target;
    if (!el.matches || !el.matches('input, textarea, select')) { return; }
    if (el.dataset.mascara) { aplicarMascara(el); }
    if (el.getAttribute('aria-invalid') === 'true') { validar(el); }            /* some assim que o erro é corrigido */
  });
  document.addEventListener('focusout', function (e) {
    var el = e.target;
    if (!el.matches || !el.matches('input, textarea')) { return; }
    if (el.type === 'file' || el.type === 'checkbox' || el.type === 'radio') { return; }
    finalizar(el);
    if ((el.value || '').trim() || el.getAttribute('aria-invalid') === 'true') { validar(el); }
  });
  /* CNPJ válido digitado: o nome da empresa e a situação vêm da base da Receita guardada no computador */
  function consultarCnpj(el) {
    var d = soDigitos(el.value);
    if (!cnpjValido(d) || el._consultado === d) { return; }
    el._consultado = d;
    var nota = document.getElementById(el.id + '-base');
    if (!nota) {
      nota = document.createElement('p'); nota.className = 'campo__dica'; nota.id = el.id + '-base'; nota.setAttribute('role', 'status');
      (el.closest('.campo') || el.parentNode).appendChild(nota);
    }
    nota.textContent = 'Procurando na base da Receita…';
    fetch('/api/cnpj/' + d).then(function (r) { return r.json(); }).then(function (r) {
      if (el._consultado !== d) { return; }
      if (!r.ok) { nota.textContent = 'CNPJ ' + r.motivo + '. Confira o número ou preencha o nome à mão.'; return; }
      nota.textContent = 'Na base da Receita: ' + r.razao + ' · ' + (r.municipio || '') + (r.uf ? '/' + r.uf : '') + ' · situação ' + r.situacao + '.';
      var nome = el.dataset.preenche ? document.getElementById(el.dataset.preenche) : null;
      if (nome && !nome.value.trim() && r.razao) {
        nome.value = r.razao; nome.dispatchEvent(new Event('input', { bubbles: true }));
        nota.textContent += ' Nome da empresa preenchido.';
      }
      if (r.situacao !== 'ATIVA') { mostrarErro(el, 'Esta empresa não está ativa na Receita (' + r.situacao + '): a SEJC não aceita a pesquisa.'); }
    }).catch(function () { nota.textContent = ''; el._consultado = null; });
  }
  document.addEventListener('focusout', function (e) {
    var el = e.target;
    if (el.matches && el.matches('input[data-mascara="cnpj"][data-preenche]')) { consultarCnpj(el); }
  });

  document.addEventListener('change', function (e) {
    var el = e.target;
    if (el.matches && el.matches('input[type="file"]')) { validar(el); }
    if (el.matches && el.matches('[data-marca-exclusao]')) {
      var c = el.closest('.item-cartao'); if (c) { c.classList.toggle('is-excluir', el.checked); }
    }
  });

  /* ------------------------------------------------------------------ janela de confirmação (no lugar do "OK / Cancelar" do navegador) */
  function confirmar(op) {
    var dlg = $('#modal-confirmar');
    if (!dlg || typeof dlg.showModal !== 'function') { return Promise.resolve(window.confirm(op.titulo + '\n\n' + (op.texto || ''))); }
    $('#modal-titulo').textContent = op.titulo;
    $('#modal-texto').textContent = op.texto || '';
    var sim = $('#modal-sim'), nao = $('#modal-nao');
    sim.textContent = op.botao || 'Confirmar';
    nao.textContent = op.cancelar || 'Cancelar';
    sim.className = 'btn ' + (op.perigo ? 'btn--perigo-cheio' : 'btn--primario');
    return new Promise(function (resolve) {
      function fim(r) { sim.removeEventListener('click', ok); nao.removeEventListener('click', no); dlg.removeEventListener('cancel', no); if (dlg.open) { dlg.close(); } resolve(r); }
      function ok() { fim(true); }
      function no(ev) { if (ev && ev.preventDefault) { ev.preventDefault(); } fim(false); }
      sim.addEventListener('click', ok); nao.addEventListener('click', no); dlg.addEventListener('cancel', no);
      dlg.showModal();
      (op.perigo ? nao : sim).focus();                                       /* em ação perigosa, o foco começa no "Cancelar" */
    });
  }

  /* ------------------------------------------------------------------ alterações não salvas */
  function retrato(form) {
    var out = [];
    try { new FormData(form).forEach(function (v, k) { if (typeof v === 'string') { out.push(k + '=' + v); } }); } catch (e) { /* navegador antigo */ }
    return out.join('&');
  }
  var vigiados = $$('form[data-avisar-saida]');
  vigiados.forEach(function (f) {
    f._retrato = retrato(f);
    var barra = $('.barra-salvar', f), estado = barra ? $('.barra-salvar__estado', barra) : null, original = estado ? estado.textContent : '';
    function conferir() {
      f._alterado = retrato(f) !== f._retrato;
      if (barra) { barra.classList.toggle('is-alterado', f._alterado); estado.textContent = f._alterado ? 'Há alterações que ainda não foram salvas.' : original; }
    }
    f.addEventListener('input', conferir); f.addEventListener('change', conferir);
  });
  function formAlterado(menos) { return vigiados.filter(function (f) { return f !== menos && f._alterado && !f._enviando; })[0]; }
  window.addEventListener('beforeunload', function (e) { if (formAlterado()) { e.preventDefault(); e.returnValue = ''; } });

  /* ------------------------------------------------------------------ envio de formulários: validação → confirmação → "aguarde" */
  $$('form').forEach(function (f) { f.setAttribute('novalidate', ''); });
  document.addEventListener('submit', function (e) {
    var f = e.target, botao = e.submitter;
    if (f.method === 'dialog' || e.defaultPrevented) { return; }
    if (f._enviando) { e.preventDefault(); return; }                          /* clique duplo */
    var campos = Array.prototype.slice.call(f.elements), erros = [];
    campos.forEach(function (el) {
      if (!el.matches('input, textarea, select')) { return; }
      if (el.type !== 'file' && el.type !== 'checkbox' && el.type !== 'radio') { finalizar(el); }
      if (!validar(el)) { erros.push(el); }
    });
    if (erros.length) {
      e.preventDefault();
      var d = erros[0].closest('details'); while (d) { d.open = true; d = d.parentElement ? d.parentElement.closest('details') : null; }
      erros[0].focus();
      toast(erros.length === 1 ? 'Confira o campo destacado em vermelho.' : 'Confira os ' + erros.length + ' campos destacados em vermelho.', 'erro');
      return;
    }
    var outro = formAlterado(f);
    if (outro && !f._semSalvar) {
      e.preventDefault();
      confirmar({ titulo: 'Há alterações não salvas nesta tela', texto: 'Se continuar agora, o que você digitou e ainda não salvou será perdido.',
                  botao: 'Continuar sem salvar', cancelar: 'Voltar e salvar', perigo: true }).then(function (ok) {
        if (ok) { f._semSalvar = true; outro._enviando = true; reenviar(f, botao); }
      });
      return;
    }
    if (f.dataset.confirmar && !f._confirmado) {
      e.preventDefault();
      confirmar({ titulo: f.dataset.confirmar, texto: f.dataset.confirmarTexto, botao: f.dataset.confirmarBotao, perigo: f.dataset.confirmarPerigo !== undefined })
        .then(function (ok) { if (ok) { f._confirmado = true; reenviar(f, botao); } });
      return;
    }
    if (f.dataset.demonstracao !== undefined) {                              /* formulários de exemplo do guia de interface: não enviam nada */
      e.preventDefault(); f._confirmado = false; toast(f.dataset.demonstracao || 'Tudo certo.', 'ok'); return;
    }
    f._enviando = true;
    setTimeout(function () {                                                  /* depois que o navegador já montou o envio */
      $$('button').forEach(function (b) { if (b.form === f && b.type !== 'button') { b.disabled = true; } });
      if (botao) { botao.classList.add('is-carregando'); botao.dataset.textoOriginal = botao.textContent; botao.textContent = botao.dataset.aguarde || 'Aguarde…'; }
    }, 0);
  });
  function reenviar(f, botao) {
    if (typeof f.requestSubmit === 'function') { f.requestSubmit(botao && botao.form === f ? botao : undefined); } else { f.submit(); }
  }
  window.addEventListener('pageshow', function (e) {                           /* voltou pelo botão "voltar" do navegador: reativa os botões */
    if (!e.persisted) { return; }
    $$('form').forEach(function (f) { f._enviando = false; f._confirmado = false; });
    $$('button.is-carregando').forEach(function (b) { b.classList.remove('is-carregando'); if (b.dataset.textoOriginal) { b.textContent = b.dataset.textoOriginal; } });
    $$('button:disabled').forEach(function (b) { if (!b.hasAttribute('data-desabilitado')) { b.disabled = false; } });
  });

  /* ------------------------------------------------------------------ navegação por seções (página do projeto) */
  var subnav = $('[data-secoes]');
  if (subnav) {
    var secoes = $$('[data-secao]'), links = $$('a[href^="#"]', subnav);
    var mostrar = function (id, rolar) {
      var alvoSecao = secoes.filter(function (s) { return s.id === id; })[0], dentro = null;
      if (!alvoSecao && id) {
        dentro = document.getElementById(id);
        alvoSecao = dentro ? dentro.closest('[data-secao]') : null;
      }
      if (!alvoSecao) { alvoSecao = secoes[0]; }
      secoes.forEach(function (s) { s.hidden = s !== alvoSecao; });
      links.forEach(function (a) { if (a.getAttribute('href') === '#' + alvoSecao.id) { a.setAttribute('aria-current', 'true'); } else { a.removeAttribute('aria-current'); } });
      if (dentro && rolar) {
        dentro.scrollIntoView({ block: 'start' });
        if (dentro.hasAttribute('data-focar')) {                              /* quadro "Adicionar…": o cursor já vai para o primeiro campo */
          var campo = dentro.querySelector('input:not([type=hidden]), select, textarea');
          if (campo) { campo.focus({ preventScroll: true }); }
        }
      }
    };
    document.addEventListener('click', function (e) {
      var a = e.target.closest ? e.target.closest('a[href^="#"]') : null;
      if (!a) { return; }
      var id = a.getAttribute('href').slice(1);
      if (!id || !document.getElementById(id) || !document.getElementById(id).closest('[data-secao]')) { return; }
      e.preventDefault();
      history.pushState(null, '', '#' + id);
      mostrar(id, !a.closest('[data-secoes]'));
      if (a.closest('[data-secoes]')) { subnav.scrollIntoView({ block: 'nearest' }); }
    });
    window.addEventListener('popstate', function () { mostrar(location.hash.slice(1), true); });
    window.addEventListener('hashchange', function () { mostrar(location.hash.slice(1), true); });
    mostrar(location.hash.slice(1), true);
  }

  /* ------------------------------------------------------------------ ajuda (?) : fecha ao clicar fora ou com Esc; uma aberta por vez */
  document.addEventListener('toggle', function (e) {
    var d = e.target;
    if (!d.classList || !d.classList.contains('dica') || !d.open) { return; }
    $$('details.dica[open]').forEach(function (o) { if (o !== d) { o.open = false; } });
    var cx = $('.dica__texto', d);                                           /* a explicação nunca sai da tela: desloca para caber */
    if (cx) {
      cx.style.left = '0px';
      var r = cx.getBoundingClientRect(), larg = document.documentElement.clientWidth, desvio = 0;
      if (r.right > larg - 8) { desvio = larg - 8 - r.right; }
      if (r.left + desvio < 8) { desvio = 8 - r.left; }
      cx.style.left = desvio + 'px';
    }
  }, true);
  document.addEventListener('click', function (e) {
    $$('details.dica[open]').forEach(function (d) { if (!d.contains(e.target)) { d.open = false; } });
    var x = e.target.closest ? e.target.closest('[data-fechar]') : null;
    if (x) { var a = x.closest('.aviso'); if (a) { a.remove(); } }
    var disp = e.target.closest ? e.target.closest('[data-dispensar-botao]') : null;
    if (disp) {
      var bloco = disp.closest('[data-dispensar]');
      try { localStorage.setItem('osc-' + bloco.dataset.dispensar, '1'); } catch (er) { /* armazenamento bloqueado */ }
      bloco.hidden = true;
      $$('[data-mostrar="' + bloco.dataset.dispensar + '"]').forEach(function (m) { m.hidden = false; });
    }
    var most = e.target.closest ? e.target.closest('[data-mostrar]') : null;
    if (most) {
      try { localStorage.removeItem('osc-' + most.dataset.mostrar); } catch (er) { /* idem */ }
      $$('[data-dispensar="' + most.dataset.mostrar + '"]').forEach(function (b) { b.hidden = false; b.scrollIntoView({ block: 'nearest' }); });
      most.hidden = true;
    }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') { return; }
    $$('details.dica[open]').forEach(function (d) { d.open = false; var s = $('summary', d); if (s) { s.focus(); } });
  });

  /* ------------------------------------------------------------------ guia de primeiro acesso (dispensável) */
  $$('[data-dispensar]').forEach(function (b) {
    var visto = false;
    try { visto = localStorage.getItem('osc-' + b.dataset.dispensar) === '1'; } catch (e) { /* sem armazenamento: mostra sempre */ }
    b.hidden = visto;
    $$('[data-mostrar="' + b.dataset.dispensar + '"]').forEach(function (m) { m.hidden = !visto; });
  });

  /* ------------------------------------------------------------------ link "abrir" ao lado de um campo de endereço */
  $$('input[data-url]').forEach(function (i) {
    var a = document.querySelector('[data-abre="' + i.id + '"]');
    if (!a) { return; }
    var sinc = function () { var v = i.value.trim(); a.href = v || '#'; a.hidden = !/^https?:\/\//i.test(v); };
    i.addEventListener('input', sinc); sinc();
  });

  /* ------------------------------------------------------------------ verificação: marcar como revisado na própria tela do item; selecionar todos */
  document.addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('[data-revisar]') : null, f = document.getElementById('f-revisar');
    if (!b || !f) { return; }
    f.elements.uma.value = b.dataset.revisar; f.elements.acao.value = b.dataset.acao || 'marcar'; f.elements.volta.value = b.dataset.volta || '';
    b.disabled = true; b.classList.add('is-carregando');
    $$('form[data-avisar-saida]').forEach(function (x) { x._enviando = true; });   /* marcar um ponto não é "sair sem salvar": a tela volta para o mesmo lugar */
    f.submit();
  });
  document.addEventListener('change', function (e) {
    var t = e.target;
    if (!t.matches || !t.matches('[data-selecionar-todos]')) { return; }
    $$('input[type=checkbox][name=chave]', t.closest('form')).forEach(function (c) { c.checked = t.checked; });
  });

  /* ------------------------------------------------------------------ itens novos: várias linhas de uma vez (tela da rubrica) */
  var contaLinha = 0;
  function novaLinha(lista, foco, depois) {
    var modelo = document.getElementById(lista.dataset.linhasNovas);
    if (!modelo) { return null; }
    contaLinha += 1;
    var div = document.createElement('div');
    div.innerHTML = modelo.innerHTML.replace(/__N__/g, 'x' + contaLinha);
    var linha = div.firstElementChild;
    if (depois && depois.parentNode === lista) { depois.after(linha); } else { lista.appendChild(linha); }
    atualizarRemover(lista);
    if (foco) { var c = linha.querySelector('input'); if (c) { c.focus(); } }
    return linha;
  }
  function atualizarRemover(lista) {                                          /* a única linha que sobra não pode ser removida */
    var linhas = $$('.linha-nova', lista);
    linhas.forEach(function (l) { var b = $('[data-remover-linha]', l); if (b) { b.hidden = linhas.length < 2; } });
  }
  document.addEventListener('click', function (e) {
    var add = e.target.closest ? e.target.closest('[data-adicionar-linha]') : null;
    if (add) {
      var lista = document.getElementById(add.dataset.adicionarLinha);
      if (lista) { novaLinha(lista, true); }
      return;
    }
    var rem = e.target.closest ? e.target.closest('[data-remover-linha]') : null;
    if (rem) {
      var l = rem.closest('.linha-nova'), ls = l.parentNode, ant = l.previousElementSibling;
      l.remove(); atualizarRemover(ls);
      var c = ant ? ant.querySelector('input') : ls.querySelector('input'); if (c) { c.focus(); }
    }
  });
  document.addEventListener('paste', function (e) {                          /* colar uma lista (do Excel ou de um texto): uma linha por item */
    var campo = e.target;
    if (!campo.matches || !campo.matches('.linha-nova input[name="ndesc"]')) { return; }
    var texto = (e.clipboardData || window.clipboardData).getData('text') || '';
    var linhas = texto.replace(/\r/g, '').split('\n').filter(function (x) { return x.trim(); });
    if (linhas.length < 2 && texto.indexOf('\t') < 0) { return; }
    e.preventDefault();
    var lista = campo.closest('[data-linhas-novas]'), linha = campo.closest('.linha-nova');
    linhas.forEach(function (t, i) {
      if (i > 0) {                                                            /* usa a próxima linha em branco; se não houver, cria uma logo abaixo */
        var prox = linha.nextElementSibling;
        linha = prox && !prox.querySelector('input[name="ndesc"]').value.trim() ? prox : novaLinha(lista, false, linha);
      }
      var partes = t.split('\t');                                           /* colunas do Excel: descrição, [marca,] especificação, quantidade */
      var qtd = partes.length > 1 && /^\s*\d+\s*$/.test(partes[partes.length - 1]) ? partes.pop().trim() : '';
      linha.querySelector('input[name="ndesc"]').value = (partes[0] || '').trim();
      var cm = linha.querySelector('input[name="nmarca"]');
      if (cm && partes.length > 2) { cm.value = partes[1].trim(); partes.splice(1, 1); }
      if (partes.length > 1) { linha.querySelector('input[name="nesp"]').value = partes.slice(1).join(' ').trim(); }
      if (qtd) { linha.querySelector('input[name="nqtd"]').value = qtd; }
    });
    toast(linhas.length + ' item(ns) colado(s), um por linha. Confira e salve.', 'ok');
    var f = campo.form; if (f) { f.dispatchEvent(new Event('input', { bubbles: true })); }
  });
  $$('[data-linhas-novas]').forEach(atualizarRemover);

  /* ------------------------------------------------------------------ itens recolhíveis (itens de uma rubrica, pesquisas de um cargo, banco de vagas):
     abre o que o endereço aponta (#sub3, #pesquisa1, #t-banco), lembra o que estava aberto ao salvar e continuar, e "abrir todos / recolher todos" */
  var recolhiveis = $$('details[data-recolhivel]');
  function abrirAlvo(sempreRolar) {
    var id = location.hash.slice(1), el = id ? document.getElementById(id) : null;
    if (!el) { return; }
    var d = el.closest('details'), abriu = false;
    while (d) { if (!d.open) { d.open = true; abriu = true; } d = d.parentElement ? d.parentElement.closest('details') : null; }
    if (abriu || (sempreRolar === true && el.closest('details[data-recolhivel]'))) { el.scrollIntoView({ block: 'start' }); }
  }
  if (recolhiveis.length) {
    var chaveAbertos = 'orca-abertos:' + location.pathname;
    var lembrar = function () {
      var ids = recolhiveis.filter(function (d) { return d.open; }).map(function (d) { return d.id; });
      try { sessionStorage.setItem(chaveAbertos, JSON.stringify({ n: recolhiveis.length, ids: ids })); } catch (e) { /* sem armazenamento: vale só nesta página */ }
    };
    try {
      var antes = JSON.parse(sessionStorage.getItem(chaveAbertos) || 'null');           /* só vale se a lista não mudou de tamanho (item novo ou excluído muda os números) */
      if (antes && antes.n === recolhiveis.length) { recolhiveis.forEach(function (d) { if (antes.ids.indexOf(d.id) >= 0) { d.open = true; } }); }
    } catch (e) { /* idem */ }
    recolhiveis.forEach(function (d) { d.addEventListener('toggle', lembrar); });
    $$('[data-recolher]').forEach(function (b) {
      b.addEventListener('click', function () {
        var lista = document.getElementById(b.getAttribute('aria-controls')) || document;
        $$('details[data-recolhivel]', lista).forEach(function (d) { d.open = b.dataset.recolher === 'abrir'; });
      });
    });
  }
  abrirAlvo(true);
  window.addEventListener('hashchange', abrirAlvo);
  document.addEventListener('click', function (e) {                            /* link para a mesma âncora de antes (o endereço não muda): abre de novo */
    var a = e.target.closest ? e.target.closest('a[href^="#"]') : null;
    if (a && a.getAttribute('href') === location.hash) { setTimeout(abrirAlvo, 0); }
  });

  /* ------------------------------------------------------------------ Alt + clique: o Chrome BAIXA a página do link (ou o resultado do botão) em vez de
     abrir — aparecem arquivos como "6.htm" na pasta Downloads (caso real de 05/10/2026, ao passar de um cargo para o outro). Dentro do sistema isso
     nunca é o que se quer: o clique com Alt vale como um clique comum. Links que abrem em outra aba (PDFs, sites) ficam como o navegador faz. */
  document.addEventListener('click', function (e) {
    if (!e.altKey || e.ctrlKey || e.shiftKey || e.metaKey || e.button !== 0) { return; }
    var a = e.target.closest ? e.target.closest('a[href]') : null;
    if (a) {
      if (a.target === '_blank' || a.hasAttribute('download') || a.origin !== location.origin) { return; }
      e.preventDefault(); e.stopPropagation();
      setTimeout(function () {                                                /* fora do clique: o navegador não vê mais o Alt */
        if (a.getAttribute('href').charAt(0) === '#') { location.hash = a.getAttribute('href'); } else { location.assign(a.href); }
      }, 0);
      return;
    }
    var b = e.target.closest ? e.target.closest('button, input[type="submit"]') : null;
    if (b && b.form && b.type === 'submit') {
      e.preventDefault(); e.stopPropagation();
      setTimeout(function () { reenviar(b.form, b); }, 0);
    }
  }, true);

  /* ------------------------------------------------------------------ mensagem que ficaria fora da tela (a página abre lá embaixo, no item): vira um aviso flutuante */
  $$('[data-toast-se-rolar]').forEach(function (a) {
    if (location.hash && location.hash.length > 1) {
      var t = $('.aviso__corpo', a);
      if (t) { setTimeout(function () { toast(t.textContent.trim(), 'ok', 8000); }, 300); }
    }
  });

  /* ------------------------------------------------------------------ mensagem da página: tira o texto do endereço para não repetir ao recarregar */
  if (/[?&](msg|leitura)=/.test(location.search) && history.replaceState) {
    var u = new URL(location.href); u.searchParams.delete('msg'); u.searchParams.delete('leitura');
    history.replaceState(null, '', u.pathname + (u.search || '') + u.hash);
  }

  /* ------------------------------------------------------------------ modo claro / escuro */
  var botaoTema = $('#alternar-tema');
  function pintarBotaoTema() {
    if (!botaoTema) { return; }
    var escuro = document.documentElement.getAttribute('data-tema') === 'escuro';
    botaoTema.setAttribute('aria-pressed', escuro ? 'true' : 'false');
    $('#alternar-tema-texto').textContent = escuro ? 'Modo claro' : 'Modo escuro';         /* o rótulo diz o que o botão faz */
    $$('[data-tema-icone]', botaoTema).forEach(function (i) { i.hidden = i.dataset.temaIcone !== (escuro ? 'claro' : 'escuro'); });
  }
  if (botaoTema) {
    botaoTema.addEventListener('click', function () {
      var novo = document.documentElement.getAttribute('data-tema') === 'escuro' ? 'claro' : 'escuro';
      document.documentElement.setAttribute('data-tema', novo);
      try { localStorage.setItem('osc-tema', novo); } catch (e) { /* sem armazenamento: vale só nesta página */ }
      pintarBotaoTema();
    });
    pintarBotaoTema();
  }
  if (window.matchMedia) {                                                   /* sem escolha guardada: acompanha o computador */
    var mq = matchMedia('(prefers-color-scheme: dark)');
    var seguir = function () {
      var guardado = null; try { guardado = localStorage.getItem('osc-tema'); } catch (e) { /* idem */ }
      if (!guardado || guardado === 'auto') { document.documentElement.setAttribute('data-tema', mq.matches ? 'escuro' : 'claro'); pintarBotaoTema(); }
    };
    if (mq.addEventListener) { mq.addEventListener('change', seguir); }
  }

  /* ------------------------------------------------------------------ sem internet */
  var semConexao = $('#sem-conexao');
  function conexao() { if (semConexao) { semConexao.hidden = navigator.onLine !== false; } }
  window.addEventListener('online', conexao); window.addEventListener('offline', conexao); conexao();

  window.OSC = { toast: toast, confirmar: confirmar, moeda: moedaFinal, centavos: centavos, cnpjValido: cnpjValido, validar: validar };
})();
{% endraw %}
