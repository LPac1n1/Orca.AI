import { useState } from "react";
import { api, evidencia } from "../api";
import { Aviso, BotaoAcao, Campo, Carregando, Formulario, Modal, Selo, useDecisao } from "../componentes";
import { centavosDeTexto, cnpj, dataHora, FORMAS_DE_PAGAMENTO, horas, reais, REGIMES } from "../formatos";
import { useDados } from "../ganchos";
import type {
  CargoRevisao, ItemRevisao, LojaDoLote, LoteRevisao, Observacao, Oferta, OrcamentoRevisao, Revisao, Status,
} from "../tipos";
import type { PropsDaAba } from "./Projeto";

const SITUACAO_DA_LOJA: Record<LojaDoLote["situacao"], string> = {
  trio: "no trio", elegivel: "completa, fora do trio", descartada: "fora", retirada: "retirada por você",
  completa: "completa", incompleta: "faltam itens",
};

const ORIGEM: Record<string, string> = { ean: "código de barras", atributos: "atributos", ia: "IA", humano: "decisão sua" };

function SeloDaOferta({ oferta }: { oferta: Oferta }) {
  const c = oferta.correspondencia;
  if (!c) return <span className="selo neutro pequeno">sem conferência</span>;
  if (c.precisa_confirmar) return <span className="selo amarelo pequeno">confirmar</span>;
  const texto = { verde: "mesmo produto", amarelo: "revisar", vermelho: "outro produto" }[c.status];
  return <span className={`selo ${c.status} pequeno`}>{texto}</span>;
}

// --- Colar link -------------------------------------------------------------------------------

type Modo = "sistema" | "janela" | "pdf";

const MODOS: { id: Modo; rotulo: string }[] = [
  { id: "sistema", rotulo: "O sistema lê a página" },
  { id: "janela", rotulo: "Abrir numa janela para eu navegar" },
  { id: "pdf", rotulo: "Enviar o PDF que eu salvei" },
];

function ColarLink({ alvo, aoTerminar }: { alvo: { tipo: "item" | "cargo"; id: string; nome: string }; aoTerminar: () => void }) {
  const [modo, setModo] = useState<Modo>("sistema");
  const [url, setUrl] = useState("");
  const [cnpjTexto, setCnpj] = useState("");
  const [preco, setPreco] = useState("");
  const [salMin, setSalMin] = useState("");
  const [salMax, setSalMax] = useState("");
  const [arquivoPdf, setArquivoPdf] = useState<File | null>(null);
  const [titulo, setTitulo] = useState("");
  const [resultado, setResultado] = useState<{ mensagem: string; avisos: string[] } | null>(null);
  const item = alvo.tipo === "item";

  function valor(texto: string, nome: string): number | null {
    if (!texto) return null;
    const centavos = centavosDeTexto(texto);
    if (!centavos) throw new Error(`${nome} em formato inválido (ex.: 34,50).`);
    return centavos;
  }

  async function enviar() {
    const endereco = url.trim();
    const preco_centavos = valor(preco, "Preço");
    const min = valor(salMin, "Salário mínimo");
    const max = valor(salMax, "Salário máximo");
    const rota = `/api/${item ? "itens" : "cargos"}/${alvo.id}`;
    if (modo === "pdf") {
      if (!arquivoPdf) throw new Error("Escolha o arquivo PDF.");
      if (item && !preco_centavos) throw new Error("Informe o preço que aparece no PDF.");
      if (!item && !min && !max) throw new Error("Informe o salário que aparece no PDF.");
      const dados = new FormData();
      dados.append("arquivo", arquivoPdf);
      dados.append("url", endereco);
      const campos: Record<string, string | number | null> = item
        ? { preco_centavos, cnpj_vendedor: cnpjTexto || null, titulo: titulo || null }
        : { salario_min_centavos: min, salario_max_centavos: max, cnpj_empresa: cnpjTexto || null, titulo: titulo || null };
      Object.entries(campos).forEach(([k, v]) => v !== null && dados.append(k, String(v)));
      setResultado(await api.enviar(`${rota}/pdf`, dados));
      return;
    }
    const corpo = item
      ? { url: endereco, cnpj_vendedor: cnpjTexto || null, preco_centavos }
      : { url: endereco, cnpj_empresa: cnpjTexto || null, salario_min_centavos: min, salario_max_centavos: max };
    await api.criar(`${rota}/${modo === "janela" ? "captura-assistida" : "coletas"}`, corpo);
    aoTerminar();
  }

  if (resultado) {
    return (
      <Modal titulo={`PDF recebido — ${alvo.nome}`} aoFechar={aoTerminar}>
        <Aviso tipo="ok">{resultado.mensagem}</Aviso>
        {resultado.avisos.length > 0 && <Aviso tipo="atencao"><ul>{resultado.avisos.map((a) => <li key={a}>{a}</li>)}</ul></Aviso>}
        <div className="acoes"><button onClick={aoTerminar}>Fechar</button></div>
      </Modal>
    );
  }

  const campoValor = item ? (
    <Campo rotulo="Preço que aparece na página"><input value={preco} onChange={(e) => setPreco(e.target.value)} placeholder="34,50" inputMode="decimal" /></Campo>
  ) : (
    <div className="linha-campos">
      <Campo rotulo="Salário (mínimo da faixa)"><input value={salMin} onChange={(e) => setSalMin(e.target.value)} inputMode="decimal" /></Campo>
      <Campo rotulo="Salário (máximo da faixa)"><input value={salMax} onChange={(e) => setSalMax(e.target.value)} inputMode="decimal" /></Campo>
    </div>
  );

  return (
    <Modal titulo={`Colar link — ${alvo.nome}`} aoFechar={aoTerminar}>
      <div className="modos" role="radiogroup" aria-label="Como ler a página">
        {MODOS.map((m) => (
          <label key={m.id} className={modo === m.id ? "ativo" : ""}>
            <input type="radio" name="modo" checked={modo === m.id} onChange={() => setModo(m.id)} />
            {m.rotulo}
          </label>
        ))}
      </div>
      <p className="explicacao">
        {modo === "sistema" && <>O sistema abre a página sem mostrar janela, guarda a prova (PDF, imagem e página salva, com data e hora), lê {item ? "o preço, a marca e o código de barras" : "o salário e a empresa"} e confere se o valor aparece mesmo na página.</>}
        {modo === "janela" && <>Para lojas que recusam programas (como Carrefour e Extra) ou que pedem CEP ou verificação. O sistema abre uma janela do navegador nesta página. <strong>Você navega nela</strong>, na mesma aba, até a página certa (resolva o CEP ou a verificação, se aparecer; não entre com a sua conta para ver preço de cliente) e clica em <strong>“Capturar agora”</strong> no quadro Tarefas, ao lado. A prova é guardada do mesmo jeito.</>}
        {modo === "pdf" && <>Se nem a janela funcionar: abra a página no seu navegador, aperte <strong>Ctrl+P</strong>, escolha <strong>Salvar como PDF</strong> com <strong>cabeçalhos e rodapés</strong> ligados (para sair o endereço e a data) e envie o arquivo aqui. Fica registrado que o PDF foi enviado por você, e o sistema confere se o endereço, o nome e o valor aparecem nele.</>}
      </p>
      <Formulario rotulo={{ sistema: "Ler a página", janela: "Abrir a janela", pdf: "Enviar o PDF" }[modo]} aoEnviar={enviar} aoCancelar={aoTerminar}>
        <Campo rotulo={item ? "Endereço da página do produto" : "Endereço da página da vaga"}>
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" required autoFocus />
        </Campo>
        {modo === "pdf" && (
          <>
            <Campo rotulo="Arquivo PDF" ajuda="Até 20 MB.">
              <input type="file" accept="application/pdf,.pdf" onChange={(e) => setArquivoPdf(e.target.files?.[0] ?? null)} required />
            </Campo>
            <Campo rotulo={item ? "Nome do produto, como está na página" : "Título da vaga, como está na página"}
              ajuda="Usado para conferir se é o mesmo produto. Copie da página.">
              <input value={titulo} onChange={(e) => setTitulo(e.target.value)} />
            </Campo>
            {campoValor}
          </>
        )}
        <Campo rotulo={item ? "CNPJ do vendedor" : "CNPJ da empresa"}
          ajuda={item ? "Deixe em branco em loja comum: o sistema lê no rodapé. Em marketplace, informe o do vendedor." : "Se a página não mostrar, informe; sem CNPJ a vaga é descartada (D-46)."}>
          <input value={cnpjTexto} onChange={(e) => setCnpj(e.target.value)} />
        </Campo>
        {modo !== "pdf" && (
          <details>
            <summary>A página não mostra {item ? "o preço" : "o salário"} para o sistema?</summary>
            <p className="discreto pequeno">Informe o valor que você vê. O sistema ainda confere se ele aparece escrito na página.</p>
            {campoValor}
          </details>
        )}
      </Formulario>
    </Modal>
  );
}

// --- Detalhe de uma oferta ------------------------------------------------------------------------

function DetalheDaOferta({ item, loja, aoFechar, atualizar }: {
  item: ItemRevisao; loja: LojaDoLote; aoFechar: () => void; atualizar: () => void;
}) {
  const oferta = item.ofertas[loja.id];
  const { dados: observacoes } = useDados<Observacao[]>(`/api/itens/${item.id}/observacoes`);
  const obs = observacoes?.find((o) => o.id === oferta.observacao_id);
  const [janela, pedir] = useDecisao();
  const decidir = (status: Status, rotulo: string) =>
    pedir({
      titulo: rotulo,
      explicacao: <p>Item <strong>{item.descricao}</strong> · página de <strong>{loja.nome}</strong>. Só uma pessoa confirma que é o mesmo produto.</p>,
      rotulo,
      sugestao: status === "verde" ? "Conferi a página: mesma marca, modelo e apresentação." : "",
      aoConfirmar: async (justificativa) => {
        await api.criar("/api/correspondencias", { item_id: item.id, observacao_id: oferta.observacao_id, status, justificativa });
        atualizar();
        aoFechar();
      },
    });
  const corrigir = (centavos: number, forma: string | null) =>
    pedir({
      titulo: `Usar ${reais(centavos)} como preço desta loja`,
      explicacao: (
        <p>
          O valor {reais(centavos)}{forma ? ` (${forma})` : ""} está escrito na mesma página salva, então a prova continua
          a mesma e a loja não é acessada de novo. A leitura anterior ({reais(oferta.preco_centavos)}) fica no histórico.
        </p>
      ),
      rotulo: "Corrigir o preço",
      sugestao: forma && forma !== "parcelado" ? `Preço ${forma} (D-60).` : "",
      aoConfirmar: async (justificativa) => {
        await api.criar(`/api/observacoes/${oferta.observacao_id}/corrigir-preco`, { preco_centavos: centavos, justificativa });
        atualizar();
        aoFechar();
      },
    });
  const outros = (obs?.precos_da_pagina ?? []).filter((p) => p.centavos !== oferta.preco_centavos);
  const c = oferta.correspondencia;
  return (
    <Modal titulo={`${item.descricao} — ${loja.nome}`} aoFechar={aoFechar}>
      <div className="detalhe">
        <p className="grande">
          {reais(oferta.preco_centavos)}
          {obs?.forma_de_pagamento && <span className="discreto pequeno"> {FORMAS_DE_PAGAMENTO[obs.forma_de_pagamento]}</span>}
        </p>
        {obs && (
          <>
            <p><strong>Na página:</strong> {obs.titulo ?? "—"}{obs.marca ? ` · marca ${obs.marca}` : ""}{obs.ean ? ` · EAN ${obs.ean}` : ""}</p>
            <p className="url"><a href={obs.url} target="_blank" rel="noreferrer noopener">{obs.url}</a></p>
            <p className="discreto">Capturada em {dataHora(obs.coletado_em)} ({obs.metodo}) · vendedor {cnpj(obs.cnpj_vendedor)} ·
              preço {obs.preco_no_html ? "conferido na página" : "NÃO conferido na página"}</p>
            {obs.avisos.length > 0 && <Aviso tipo="atencao"><ul>{obs.avisos.map((a) => <li key={a}>{a}</li>)}</ul></Aviso>}
          </>
        )}
        {oferta.evidencia_id && (
          <p className="botoes">
            <a className="botao secundario" href={evidencia(oferta.evidencia_id, "pdf")} target="_blank" rel="noreferrer">Ver a prova (PDF)</a>
            <a className="botao secundario" href={evidencia(oferta.evidencia_id, "png")} target="_blank" rel="noreferrer">Imagem</a>
            <a className="botao secundario" href={evidencia(oferta.evidencia_id, "mhtml")} download>Página salva</a>
          </p>
        )}
        <details className="corrigir-preco">
          <summary>O preço está errado?</summary>
          <p className="discreto pequeno">
            Pela regra D-60, vale o preço no Pix; sem Pix, o do boleto; nunca o parcelado. Escolha outro valor que aparece
            nesta página:
          </p>
          <div className="botoes">
            {outros.map((p) => (
              <button key={p.centavos} className="secundario pequeno" disabled={p.forma === "parcelado"}
                title={p.forma === "parcelado" ? "preço parcelado: não vale (D-60)" : undefined}
                onClick={() => corrigir(p.centavos, p.forma ? FORMAS_DE_PAGAMENTO[p.forma] : null)}>
                {reais(p.centavos)}{p.forma ? ` · ${FORMAS_DE_PAGAMENTO[p.forma]}` : ""}
              </button>
            ))}
          </div>
          <OutroValor aoEscolher={(centavos) => corrigir(centavos, null)} />
        </details>
        <h3>É o mesmo produto?</h3>
        {c ? (
          <div>
            <p><SeloDaOferta oferta={oferta} /> <span className="discreto">por {ORIGEM[c.origem]} · {c.autor}</span></p>
            <ul className="motivos">{c.motivos.map((m) => <li key={m}>{m}</li>)}</ul>
          </div>
        ) : <p className="discreto">Ainda não conferido.</p>}
        {!oferta.evidencia_valida && <Aviso tipo="atencao">A prova não vale: sem PDF, preço não encontrado na página ou pesquisa vencida. Cole o link de novo.</Aviso>}
        <div className="botoes">
          <button onClick={() => decidir("verde", "Confirmar: é o mesmo produto")}>Confirmar 🟢</button>
          <button className="secundario" onClick={() => decidir("vermelho", "Recusar: é outro produto")}>Recusar 🔴</button>
        </div>
      </div>
      {janela}
    </Modal>
  );
}

function OutroValor({ aoEscolher }: { aoEscolher: (centavos: number) => void }) {
  const [texto, setTexto] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  return (
    <div className="linha-campos">
      <Campo rotulo="Outro valor que aparece na página" ajuda="O sistema confere na página salva.">
        <input value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="16,59" inputMode="decimal" />
      </Campo>
      <button className="secundario" onClick={() => {
        const centavos = centavosDeTexto(texto);
        setErro(centavos ? null : "Valor em formato inválido (ex.: 16,59).");
        if (centavos) aoEscolher(centavos);
      }}>Usar este valor</button>
      {erro && <span className="erro-curto">{erro}</span>}
    </div>
  );
}

// --- Lote -----------------------------------------------------------------------------------------

function Lote({ lote, orcamento, atualizar }: { lote: LoteRevisao; orcamento: OrcamentoRevisao; atualizar: () => void }) {
  const [colar, setColar] = useState<ItemRevisao | null>(null);
  const [detalhe, setDetalhe] = useState<{ item: ItemRevisao; loja: LojaDoLote } | null>(null);
  const [simulacao, setSimulacao] = useState<null | { sucesso: boolean; mensagem: string; tentativas: { retirada: string; motivo: string }[] }>(null);
  const [janela, pedir] = useDecisao();
  const lojasComPreco = lote.lojas.filter((l) => lote.itens.some((i) => i.ofertas[l.id]));
  const temAcima = lote.itens.some((i) => i.dentro_da_media === false);

  const retirar = (loja: LojaDoLote) => pedir({
    titulo: `Retirar ${loja.nome} do lote`,
    explicacao: <p>A loja sai do lote e a próxima da classificação entra (Saída 2, D-23). Dá para desfazer depois (“devolver”).</p>,
    rotulo: "Retirar a loja",
    sugestao: temAcima && loja.posicao === 1 ? "Item acima da média na loja escolhida (Saída 2)." : "",
    aoConfirmar: async (justificativa) => { await api.criar(`/api/lotes/${lote.id}/retirar-loja`, { loja: loja.id, justificativa }); atualizar(); },
  });
  const devolver = (loja: LojaDoLote) => pedir({
    titulo: `Devolver ${loja.nome} ao lote`, explicacao: <p>A loja volta para a classificação.</p>, rotulo: "Devolver",
    aoConfirmar: async (justificativa) => { await api.criar(`/api/lotes/${lote.id}/devolver-loja`, { loja: loja.id, justificativa }); atualizar(); },
  });

  return (
    <div className="lote">
      <div className="cabecalho-secao">
        <h3>Lote {lote.nome}</h3>
        <Selo status={lote.situacao === "ok" ? (temAcima ? "vermelho" : "verde") : "amarelo"}
          texto={lote.situacao === "ok" ? (temAcima ? "item acima da média" : `${orcamento.fontes_por_cotacao} lojas escolhidas`) : lote.situacao === "sem_trio" ? "faltam lojas completas" : "sem pesquisa"} />
      </div>
      {lote.mensagem && <p className="discreto">{lote.mensagem}</p>}
      {lote.sugestoes.length > 0 && <Aviso tipo="info"><ul>{lote.sugestoes.map((s) => <li key={s}>{s}</li>)}</ul></Aviso>}
      {temAcima && orcamento.base_preco_final === "B" && (
        <Aviso tipo="atencao">
          Na regra B, o preço da loja escolhida precisa estar dentro da média. Você pode <strong>trocar o produto</strong> (em Itens e cargos) ou <strong>retirar a loja escolhida</strong> para a próxima entrar.{" "}
          <BotaoAcao classe="secundario pequeno" aoClicar={async () => setSimulacao(await api.obter(`/api/lotes/${lote.id}/simular-troca-de-loja`))}>
            Simular a troca de loja
          </BotaoAcao>
        </Aviso>
      )}

      <div className="rolagem">
        <table className="tabela matriz">
          <thead>
            <tr>
              <th>Item</th>
              {lojasComPreco.map((l) => (
                <th key={l.id} className={`loja ${l.situacao}`}>
                  <div>{l.posicao ? `Orçamento ${l.posicao}` : SITUACAO_DA_LOJA[l.situacao]}</div>
                  <div className="nome-loja">{l.nome}</div>
                  <div className="discreto pequeno">{cnpj(l.cnpj)}{l.cnpj && !l.cnpj_consultado ? " · CNPJ ainda não consultado" : l.cnpj && !l.cnpj_ativo ? " · CNPJ não ativo" : ""}</div>
                  {l.total_centavos !== null && <div className="pequeno">total {reais(l.total_centavos)}</div>}
                  {l.motivo && <div className="erro-curto pequeno">{l.motivo}</div>}
                  <div>
                    {l.situacao === "retirada"
                      ? <button className="link pequeno" onClick={() => devolver(l)}>devolver</button>
                      : (l.situacao === "trio" || l.situacao === "elegivel") && <button className="link pequeno" onClick={() => retirar(l)}>retirar</button>}
                  </div>
                </th>
              ))}
              <th className="n">Média</th>
              <th className="n">Preço final</th>
            </tr>
          </thead>
          <tbody>
            {lote.itens.map((i) => (
              <tr key={i.id}>
                <td className="item">
                  <div><Selo status={i.status} /> <strong>{i.descricao}</strong></div>
                  <div className="discreto pequeno">{[i.marca, i.apresentacao].filter(Boolean).join(" · ")} · {i.qtd_planejada} {i.unidade}/mês × {i.meses}</div>
                  {i.motivos.map((m) => <div key={m} className="pequeno motivo">{m}</div>)}
                  <button className="link pequeno" onClick={() => setColar(i)}>+ colar link</button>
                </td>
                {lojasComPreco.map((l) => {
                  const o = i.ofertas[l.id];
                  return (
                    <td key={l.id} className={`oferta ${l.situacao} ${o && !o.utilizavel ? "inutil" : ""}`}>
                      {o ? (
                        <button className="celula" onClick={() => setDetalhe({ item: i, loja: l })} title="Ver detalhes e decidir">
                          <span className="preco">{reais(o.preco_centavos)}</span>
                          <SeloDaOferta oferta={o} />
                          {!o.evidencia_valida && <span className="erro-curto pequeno">prova inválida</span>}
                        </button>
                      ) : <span className="discreto">—</span>}
                    </td>
                  );
                })}
                <td className="n">{reais(i.media_centavos)}{i.media_exata && i.media_exata !== reais(i.media_centavos) && <div className="discreto pequeno">exata {i.media_exata}</div>}</td>
                <td className="n">
                  {reais(i.preco_final_centavos)}
                  {i.dentro_da_media === false && <div className="erro-curto pequeno">acima da média</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {colar && <ColarLink alvo={{ tipo: "item", id: colar.id, nome: colar.descricao }} aoTerminar={() => { setColar(null); atualizar(); }} />}
      {detalhe && <DetalheDaOferta item={detalhe.item} loja={detalhe.loja} aoFechar={() => setDetalhe(null)} atualizar={atualizar} />}
      {simulacao && (
        <Modal titulo="Simulação da troca de loja (Saída 2)" aoFechar={() => setSimulacao(null)}>
          <Aviso tipo={simulacao.sucesso ? "ok" : "atencao"}>{simulacao.mensagem}</Aviso>
          <ol>{simulacao.tentativas.map((t, n) => <li key={n}>Retirando <strong>{t.retirada}</strong>: {t.motivo}</li>)}</ol>
          <p className="discreto">Nada foi mudado. Para aplicar, use “retirar” na loja.</p>
        </Modal>
      )}
      {janela}
    </div>
  );
}

// --- Cargo ------------------------------------------------------------------------------------------

function CargoPesquisa({ cargo, atualizar }: { cargo: CargoRevisao; atualizar: () => void }) {
  const [colar, setColar] = useState(false);
  const [janela, pedir] = useDecisao();
  const nomeDaVaga = (id: string) => {
    const v = cargo.vagas.find((x) => x.id === id);
    return v ? `${v.empresa ?? "empresa?"} (${v.plataforma})` : id;
  };
  return (
    <div className="lote">
      <div className="cabecalho-secao">
        <h3><Selo status={cargo.status} /> {cargo.nome} <span className="discreto">· {REGIMES[cargo.regime]} · {horas(cargo.horas_planejadas_centesimos)} h/mês · {cargo.postos} posto(s)</span></h3>
        <button className="secundario pequeno" onClick={() => setColar(true)}>+ colar link de vaga</button>
      </div>
      {cargo.problema && <Aviso tipo="atencao">{cargo.problema}</Aviso>}
      {cargo.incertos.map((p) => (
        <Aviso key={p.a + p.b} tipo="info">
          Talvez sejam a mesma vaga: {nomeDaVaga(p.a)} e {nomeDaVaga(p.b)} ({p.motivo}).{" "}
          <button className="link" onClick={() => pedir({
            titulo: "Marcar como a mesma vaga", explicacao: <p>As duas contam como uma só (D-49).</p>, rotulo: "É a mesma vaga",
            aoConfirmar: async (justificativa) => { await api.criar(`/api/cargos/${cargo.id}/mesma-vaga`, { a: p.a, b: p.b, justificativa }); atualizar(); },
          })}>É a mesma vaga</button>
        </Aviso>
      ))}
      {cargo.vagas.length > 0 && (
        <table className="tabela">
          <thead><tr><th>Empresa</th><th>Salário</th><th>Considerado</th><th>Plataforma</th><th>Situação</th><th>Prova</th></tr></thead>
          <tbody>
            {cargo.vagas.map((v) => (
              <tr key={v.id} className={v.escolhida ? "" : "apagada"}>
                <td>{v.empresa ?? "—"}<div className="discreto pequeno">{cnpj(v.cnpj)}</div></td>
                <td>{v.salario_min_centavos ? reais(v.salario_min_centavos) : "—"}{v.salario_max_centavos && v.salario_max_centavos !== v.salario_min_centavos ? ` a ${reais(v.salario_max_centavos)}` : ""}</td>
                <td>{reais(v.referencia_centavos)}</td>
                <td>{v.plataforma}</td>
                <td>{v.escolhida ? <Selo status="verde" texto="escolhida" /> : <span className="pequeno">{v.motivo_descarte}</span>}</td>
                <td>{v.evidencia_id ? <a href={evidencia(v.evidencia_id)} target="_blank" rel="noreferrer">PDF</a> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {cargo.calculo && (
        <div className="memoria">
          <strong>Valor mensal: {reais(cargo.calculo.valor_mensal_centavos)}</strong> · total {reais(cargo.calculo.total_centavos)}
          <ul>{cargo.calculo.memoria.map((m) => <li key={m}>{m}</li>)}</ul>
        </div>
      )}
      {colar && <ColarLink alvo={{ tipo: "cargo", id: cargo.id, nome: cargo.nome }} aoTerminar={() => { setColar(false); atualizar(); }} />}
      {janela}
    </div>
  );
}

export function AbaPesquisa({ projeto, versao, atualizar }: PropsDaAba) {
  const { dados, erro } = useDados<Revisao>(`/api/projetos/${projeto.id}/revisao`, versao);
  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!dados) return <Carregando />;
  if (dados.orcamentos.length === 0) return <div className="vazio"><p>Cadastre orçamentos, itens e cargos primeiro.</p></div>;
  return (
    <div>
      <p className="discreto">
        Para cada item, cole os links das páginas de pelo menos {dados.orcamentos[0]?.fontes_por_cotacao ?? 3} lojas. Cada preço só vale com a prova completa, o produto confirmado como idêntico e o CNPJ ativo.
        Clique num preço para ver a prova e decidir.
      </p>
      {dados.orcamentos.map((o) => (
        <div key={o.id} className="bloco">
          <h2>{o.nome} <span className="discreto">· regra {o.base_preco_final} {o.base_preco_final === "B" ? "(preço da loja de menor total)" : "(média)"}</span></h2>
          {o.lotes.map((l) => <Lote key={l.id} lote={l} orcamento={o} atualizar={atualizar} />)}
          {o.cargos.map((c) => <CargoPesquisa key={c.id} cargo={c} atualizar={atualizar} />)}
          {o.lotes.length === 0 && o.cargos.length === 0 && <p className="discreto">Nada cadastrado neste orçamento.</p>}
        </div>
      ))}
    </div>
  );
}
