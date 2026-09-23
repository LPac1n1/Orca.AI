import { useState } from "react";
import { api, evidencia } from "../api";
import { Aviso, BotaoAcao, Campo, Carregando, Formulario, Modal, Selo, useDecisao } from "../componentes";
import { centavosDeTexto, cnpj, dataHora, horas, reais, REGIMES } from "../formatos";
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

function ColarLink({ alvo, aoTerminar }: { alvo: { tipo: "item" | "cargo"; id: string; nome: string }; aoTerminar: () => void }) {
  const [url, setUrl] = useState("");
  const [cnpjTexto, setCnpj] = useState("");
  const [preco, setPreco] = useState("");
  const [salMin, setSalMin] = useState("");
  const [salMax, setSalMax] = useState("");
  async function enviar() {
    if (alvo.tipo === "item") {
      const preco_centavos = preco ? centavosDeTexto(preco) : null;
      if (preco && !preco_centavos) throw new Error("Preço em formato inválido (ex.: 34,50).");
      await api.criar(`/api/itens/${alvo.id}/coletas`, { url: url.trim(), cnpj_vendedor: cnpjTexto || null, preco_centavos });
    } else {
      const min = salMin ? centavosDeTexto(salMin) : null;
      const max = salMax ? centavosDeTexto(salMax) : null;
      await api.criar(`/api/cargos/${alvo.id}/coletas`, {
        url: url.trim(), cnpj_empresa: cnpjTexto || null, salario_min_centavos: min, salario_max_centavos: max,
      });
    }
    aoTerminar();
  }
  return (
    <Modal titulo={`Colar link — ${alvo.nome}`} aoFechar={aoTerminar}>
      <p className="explicacao">
        O sistema abre a página, guarda a prova (PDF, imagem e página salva, com data e hora), lê {alvo.tipo === "item" ? "o preço, a marca e o código de barras" : "o salário e a empresa"} e confere se o valor aparece mesmo na página.
      </p>
      <Formulario rotulo="Ler a página" aoEnviar={enviar} aoCancelar={aoTerminar}>
        <Campo rotulo={alvo.tipo === "item" ? "Endereço da página do produto" : "Endereço da página da vaga"}>
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" required autoFocus />
        </Campo>
        <Campo rotulo={alvo.tipo === "item" ? "CNPJ do vendedor" : "CNPJ da empresa"}
          ajuda={alvo.tipo === "item" ? "Deixe em branco em loja comum: o sistema lê no rodapé. Em marketplace, informe o do vendedor." : "Se a página não mostrar, informe; sem CNPJ a vaga é descartada (D-46)."}>
          <input value={cnpjTexto} onChange={(e) => setCnpj(e.target.value)} />
        </Campo>
        <details>
          <summary>A página não mostra {alvo.tipo === "item" ? "o preço" : "o salário"} para o sistema?</summary>
          <p className="discreto pequeno">Informe o valor que você vê. O sistema ainda confere se ele aparece escrito na página.</p>
          {alvo.tipo === "item" ? (
            <Campo rotulo="Preço que aparece na página"><input value={preco} onChange={(e) => setPreco(e.target.value)} placeholder="34,50" inputMode="decimal" /></Campo>
          ) : (
            <div className="linha-campos">
              <Campo rotulo="Salário (mínimo da faixa)"><input value={salMin} onChange={(e) => setSalMin(e.target.value)} inputMode="decimal" /></Campo>
              <Campo rotulo="Salário (máximo da faixa)"><input value={salMax} onChange={(e) => setSalMax(e.target.value)} inputMode="decimal" /></Campo>
            </div>
          )}
        </details>
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
  const c = oferta.correspondencia;
  return (
    <Modal titulo={`${item.descricao} — ${loja.nome}`} aoFechar={aoFechar}>
      <div className="detalhe">
        <p className="grande">{reais(oferta.preco_centavos)}</p>
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
                  <div className="discreto pequeno">{cnpj(l.cnpj)}{!l.cnpj_ativo && l.cnpj ? " · CNPJ não confirmado" : ""}</div>
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
