import { useState } from "react";
import { api, evidencia } from "../api";
import { Aviso, BotaoAcao, Campo, Carregando, Formulario, Modal, Selo, useDecisao } from "../componentes";
import { centavosDeTexto, cnpj, dataHora, FORMAS_DE_PAGAMENTO, horas, reais, REGIMES } from "../formatos";
import { ativa, useDados, useTarefa } from "../ganchos";
import type {
  CargoRevisao, EstadoOpcionais, ItemRevisao, LojaDoLote, LoteRevisao, Observacao, Oferta, OrcamentoRevisao, Revisao, Status,
  Tarefa,
} from "../tipos";

/** Foto do produto na página (D-73). Só ajuda a pessoa a decidir. */
function Foto({ src, alt }: { src: string | null | undefined; alt: string }) {
  const [erro, setErro] = useState(false);
  if (!src || erro) return <div className="foto vazia">sem foto</div>;
  return <img className="foto" src={src} alt={alt} loading="lazy" referrerPolicy="no-referrer" onError={() => setErro(true)} />;
}
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
  const [foiParaJanela, setFoiParaJanela] = useState(false);
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
    const tarefa = await api.criar<{ tipo: string }>(`${rota}/${modo === "janela" ? "captura-assistida" : "coletas"}`, corpo);
    if (modo === "sistema" && tarefa.tipo === "captura_assistida") {
      setFoiParaJanela(true);  // D-69: a plataforma não permite programas
      return;
    }
    aoTerminar();
  }

  if (foiParaJanela) {
    return (
      <Modal titulo={`Colar link — ${alvo.nome}`} aoFechar={aoTerminar}>
        <Aviso tipo="info">
          Esta plataforma não permite que programas abram as vagas (termos de uso). Abri uma janela na página: confira a
          vaga e clique em <strong>“Capturar agora”</strong>, no quadro Tarefas, ao lado.
        </Aviso>
        <div className="acoes"><button onClick={aoTerminar}>Entendi</button></div>
      </Modal>
    );
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
  const usarComoReferencia = () =>
    pedir({
      titulo: "Usar como produto de referência",
      explicacao: (
        <p>
          Esta página passa a ser o produto de <strong>{item.descricao}</strong>. As outras lojas são comparadas com ela:
          mesmo código de barras vira 🟢 sozinho; tamanho, gramatura ou quantidade diferente vira 🔴 (D-71).
        </p>
      ),
      rotulo: "Usar como referência",
      sugestao: "Conferi a página: é o produto do item (D-71).",
      aoConfirmar: async (justificativa) => {
        await api.criar(`/api/itens/${item.id}/referencia`, { observacao_id: oferta.observacao_id, justificativa });
        atualizar();
        aoFechar();
      },
    });
  const ehReferencia = item.referencia?.url === oferta.url;
  const outros = (obs?.precos_da_pagina ?? []).filter((p) => p.centavos !== oferta.preco_centavos);
  const c = oferta.correspondencia;
  return (
    <Modal titulo={`${item.descricao} — ${loja.nome}`} aoFechar={aoFechar}>
      <div className="detalhe">
        <p className="grande">
          {reais(oferta.preco_centavos)}
          {obs?.forma_de_pagamento && <span className="discreto pequeno"> {FORMAS_DE_PAGAMENTO[obs.forma_de_pagamento]}</span>}
        </p>
        <div className="fotos-lado-a-lado">
          <figure>
            <Foto src={obs?.imagem ?? oferta.imagem} alt={oferta.titulo ?? ""} />
            <figcaption className="pequeno">esta página ({loja.nome})</figcaption>
          </figure>
          {item.referencia && !ehReferencia && (
            <figure>
              <Foto src={item.referencia.imagem} alt={item.referencia.titulo ?? ""} />
              <figcaption className="pequeno">produto de referência ({item.referencia.loja}): {item.referencia.titulo}</figcaption>
            </figure>
          )}
        </div>
        {ehReferencia && <Aviso tipo="info">Esta página é o produto de referência do item (D-71).</Aviso>}
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
          {!ehReferencia && <button className="secundario" onClick={usarComoReferencia}>Usar como produto de referência</button>}
        </div>
        {!item.referencia && (
          <p className="discreto pequeno">
            A primeira página que você confirma vira o produto de referência: as outras lojas passam a ser comparadas com ela.
          </p>
        )}
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

// --- Busca automática nas lojas (Fase 2, etapa 10; D-68) ------------------------------------------

interface LojaDeBusca {
  id: string;
  nome: string;
  modo: "api_vtex" | "api_vtex_is" | "api_woocommerce" | "pagina" | "assistida";
  sugerida: boolean;
  faltam: number;
  // D-74: o que a loja vende em relação a este lote
  situacao: "todas" | "parte" | "nenhuma" | "desconhecida" | "itens_sem_categoria";
  tipos: string[];
  do_lote: string[];
  aprendido: string[];
  classificando: boolean;
}

interface LojasDoLote {
  itens: number;
  itens_sem_categoria: number;
  tipos_do_lote: string[];
  lojas: LojaDeBusca[];
}

function BuscarNasLojas({ lote, aoFechar, aoIniciar, aoDescobrir, fechar = false }: {
  lote: LoteRevisao; aoFechar: () => void; aoIniciar: () => void; aoDescobrir: (tarefaId: string) => void; fechar?: boolean;
}) {
  const { dados, erro } = useDados<LojasDoLote>(`/api/lotes/${lote.id}/lojas-de-busca`);
  const { dados: opcionais } = useDados<EstadoOpcionais>("/api/opcionais");
  const [marcadas, setMarcadas] = useState<Set<string> | null>(null);
  // D-74: já vêm marcadas as lojas que o sistema pesquisa sozinho e que vendem tudo o que o lote tem
  const escolhidas = marcadas ?? new Set((dados?.lojas ?? []).filter((l) => l.modo !== "assistida" && l.situacao === "todas" && l.faltam > 0).map((l) => l.id));
  const alternar = (id: string) => {
    const nova = new Set(escolhidas);
    if (nova.has(id)) nova.delete(id);
    else nova.add(id);
    setMarcadas(nova);
  };
  const lojas = dados?.lojas ?? [];
  const automaticas = lojas.filter((l) => l.modo !== "assistida");
  const assistidas = lojas.filter((l) => l.modo === "assistida");
  const buscas = automaticas.filter((l) => escolhidas.has(l.id)).reduce((n, l) => n + l.faltam, 0);
  const janelas = assistidas.filter((l) => escolhidas.has(l.id)).reduce((n, l) => n + l.faltam, 0);
  const linha = (l: LojaDeBusca) => (
    <label key={l.id} className="marcador quebra">
      <input type="checkbox" checked={escolhidas.has(l.id)} onChange={() => alternar(l.id)} disabled={l.faltam === 0} />
      <strong>{l.nome}</strong>
      <span className="discreto pequeno">
        {l.tipos.length > 0 ? ` · ${l.tipos.join(", ")}` : ""}
        {l.situacao === "parte" ? ` · deste lote, só: ${l.do_lote.join(", ")}` : ""}
        {l.aprendido.length > 0 ? " · aprendido nas suas pesquisas" : ""}
        {l.modo === "assistida" ? " · com janela: você escolhe o produto" : ""}
        {l.faltam === 0 ? " · todos os itens já têm página" : ` · ${l.faltam} item(ns) a pesquisar`}
      </span>
    </label>
  );
  const grupo = (situacao: LojaDeBusca["situacao"]) => lojas.filter((l) => l.situacao === situacao);
  const [indicadas, parte, desconhecidas, outras, semCategoria] =
    [grupo("todas"), grupo("parte"), grupo("desconhecida"), grupo("nenhuma"), grupo("itens_sem_categoria")];
  return (
    <Modal titulo={`${fechar ? "Fechar o lote" : "Pesquisar nas lojas"} — ${lote.nome}`} aoFechar={aoFechar}>
      {fechar ? (
        <p className="explicacao">
          O sistema pesquisa <strong>todos os itens</strong> nas lojas escolhidas e guarda a página de cada um como prova. No fim,
          mostra o que falta: os produtos para você confirmar (um por item, com as fotos lado a lado) e, para cada item que falta
          nas 3 lojas mais completas, produtos de outra marca que existem nas 3. Nada é trocado sem você (D-72).
        </p>
      ) : (
        <p className="explicacao">
          O sistema pesquisa cada item na loja, escolhe o produto mais parecido e guarda a página dele como prova, como se você
          tivesse colado o link. Começa pelo item mais difícil; se a loja não tiver um item, fica registrado e a busca segue nos
          outros. Vai devagar (alguns segundos entre um pedido e outro, na mesma loja). No fim, confira os resultados na tabela.
        </p>
      )}
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {!dados && !erro && <Carregando />}
      {dados && (
        <Formulario rotulo={fechar ? "Fechar o lote" : "Pesquisar"} aoCancelar={aoFechar} aoEnviar={async () => {
          if (escolhidas.size === 0) throw new Error("Escolha ao menos uma loja.");
          await api.criar(`/api/lotes/${lote.id}/${fechar ? "fechar" : "busca"}`, { lojas: [...escolhidas] });
          aoIniciar();
        }}>
          {dados.tipos_do_lote.length > 0 && <p>Este lote tem: <strong>{dados.tipos_do_lote.join(", ")}</strong>.</p>}
          {dados.itens_sem_categoria > 0 && (
            <Aviso tipo="atencao">
              {dados.itens_sem_categoria} item(ns) sem categoria: informe a categoria em “Itens e cargos” para o sistema indicar
              as lojas certas.
            </Aviso>
          )}
          {indicadas.length > 0 && (
            <>
              <h3>Indicadas para este lote</h3>
              <p className="discreto pequeno">Vendem tudo o que o lote tem. Já vêm marcadas as que o sistema pesquisa sozinho.</p>
              <div className="lista-lojas">{indicadas.map(linha)}</div>
            </>
          )}
          {semCategoria.length > 0 && <div className="lista-lojas">{semCategoria.map(linha)}</div>}
          {parte.length > 0 && (
            <>
              <h3>Vendem só parte dos itens</h3>
              <div className="lista-lojas">{parte.map(linha)}</div>
            </>
          )}
          {desconhecidas.length > 0 && (
            <>
              <h3>Ainda sem tipo</h3>
              <p className="discreto pequeno">
                {desconhecidas.some((l) => l.classificando)
                  ? "O sistema está descobrindo o que estas lojas vendem (veja o quadro Tarefas)."
                  : "O sistema ainda não sabe o que estas lojas vendem: aprende com as páginas que você confirmar."}
              </p>
              <div className="lista-lojas">{desconhecidas.map(linha)}</div>
            </>
          )}
          {outras.length > 0 && (
            <details>
              <summary>Outras lojas ({outras.length}): não vendem o que este lote tem</summary>
              <div className="lista-lojas">{outras.map(linha)}</div>
            </details>
          )}
          {assistidas.some((l) => escolhidas.has(l.id)) && (
            <p className="discreto pequeno">
              Lojas com janela recusam programas (D-67): para cada item, abre uma janela na busca da loja; você clica no
              produto certo e depois em “Capturar agora”, no quadro Tarefas.
            </p>
          )}
          <Aviso tipo="info">
            Até <strong>{buscas}</strong> busca(s) automática(s)
            {buscas > 0 ? ` (cerca de ${Math.max(1, Math.round((buscas * 20) / 60))} min)` : ""} e{" "}
            <strong>{janelas}</strong> captura(s) com janela, que vão esperar por você.
          </Aviso>
          <p className="discreto pequeno">Mercado Livre, Shopee e Amazon não entram aqui: cole o link da página do produto.</p>
        </Formulario>
      )}
      <h3>Pela internet, em outras lojas (opcional)</h3>
      {opcionais?.serpapi.chave ? (
        <p className="discreto pequeno">
          A busca do Google (SerpApi) procura cada item e mostra as páginas parecidas; você escolhe quais o sistema lê. Gasta{" "}
          {lote.itens.length} busca(s) do seu plano grátis.{" "}
          <BotaoAcao classe="secundario pequeno" aoClicar={async () => {
            aoDescobrir((await api.criar<Tarefa>(`/api/lotes/${lote.id}/descobrir`, {})).id);
          }}>Procurar pela internet</BotaoAcao>
        </p>
      ) : (
        <p className="discreto pequeno">Com uma chave grátis da SerpApi (em Opcionais, no alto da página), dá para procurar também em lojas fora do catálogo.</p>
      )}
    </Modal>
  );
}

// --- Descoberta pela internet (SerpApi, C2; Fase 2, etapa 15) --------------------------------------

interface LinkDescoberto {
  url: string;
  titulo: string;
  dominio: string;
  loja: string | null;
  status: Status;
  preco_centavos: number | null;
  ja_pesquisada: boolean;
}

interface ResultadoDescoberta {
  itens: { item_id: string; item: string; termo: string; links: LinkDescoberto[] }[];
  avisos: string[];
  mensagem: string;
}

function DescobertaNaWeb({ tarefaId, aoFechar, aoColetar }: { tarefaId: string; aoFechar: () => void; aoColetar: () => void }) {
  const tarefa = useTarefa(tarefaId);
  const resultado = tarefa?.estado === "concluida" ? (tarefa.resultado as unknown as ResultadoDescoberta) : null;
  const [marcados, setMarcados] = useState<Set<string> | null>(null);
  const chave = (itemId: string, url: string) => `${itemId}|${url}`;
  const escolhidos = marcados ?? new Set((resultado?.itens ?? []).flatMap((i) =>
    i.links.filter((l) => l.status === "verde" && !l.ja_pesquisada).map((l) => chave(i.item_id, l.url))));
  const alternar = (k: string) => {
    const novo = new Set(escolhidos);
    if (novo.has(k)) novo.delete(k);
    else novo.add(k);
    setMarcados(novo);
  };
  return (
    <Modal titulo="Procurar pela internet" aoFechar={aoFechar}>
      <p className="explicacao">
        Resultados da busca do Google, só como ponto de partida: não são prova. Marque as páginas que o sistema deve ler; cada uma
        é conferida como se você tivesse colado o link (prova, preço, CNPJ do vendedor e se é o mesmo produto).
      </p>
      {(!tarefa || ativa(tarefa)) && <Aviso tipo="info">Procurando… {tarefa?.mensagem ?? ""}</Aviso>}
      {tarefa && (tarefa.estado === "falhou" || tarefa.estado === "cancelada") && <Aviso tipo="erro">{tarefa.mensagem ?? "A busca não terminou."}</Aviso>}
      {resultado && (
        <Formulario rotulo={`Ler ${escolhidos.size} página(s)`} aoCancelar={aoFechar} aoEnviar={async () => {
          if (escolhidos.size === 0) throw new Error("Marque ao menos uma página.");
          for (const k of escolhidos) {
            const [itemId, ...resto] = k.split("|");
            await api.criar(`/api/itens/${itemId}/coletas`, { url: resto.join("|") });
          }
          aoColetar();
        }}>
          <Aviso tipo={resultado.avisos.length ? "atencao" : "info"}>{resultado.mensagem}</Aviso>
          {resultado.itens.map((i) => (
            <div key={i.item_id}>
              <h3>{i.item} <span className="discreto pequeno">· busca por “{i.termo}”</span></h3>
              {i.links.length === 0 && <p className="discreto pequeno">Nenhuma página parecida.</p>}
              {i.links.map((l) => (
                <label key={l.url} className="marcador quebra">
                  <input type="checkbox" checked={escolhidos.has(chave(i.item_id, l.url))} onChange={() => alternar(chave(i.item_id, l.url))} />
                  <Selo status={l.status} />
                  <a href={l.url} target="_blank" rel="noreferrer">{l.titulo || l.url}</a>
                  <span className="discreto pequeno">
                    · {l.loja ?? l.dominio}{l.preco_centavos ? ` · prévia ${reais(l.preco_centavos)}` : ""}
                    {l.ja_pesquisada ? " · já tem página desta loja" : ""}
                  </span>
                </label>
              ))}
            </div>
          ))}
        </Formulario>
      )}
    </Modal>
  );
}

// --- Saída 1 com busca: produto de outra marca nas 3 lojas (D-23; Fase 2, etapa 14) -----------------

interface OpcaoAlternativa {
  titulo: string;
  marca: string | null;
  situacao: "resolve" | "nao_resolve" | "sem_preco" | "incompleta";
  motivo: string;
  lojas: { loja_id: string; loja: string; url: string | null; preco_centavos: number | null }[];
  media: string | null;
  impacto_centavos: number | null;
}

interface ResultadoAlternativas {
  termo: string;
  escolhida: string;
  lojas: { loja_id: string; loja: string; busca: string | null }[];
  opcoes: OpcaoAlternativa[];
  avisos: string[];
  mensagem: string;
}

const SITUACAO_DA_ALTERNATIVA: Record<OpcaoAlternativa["situacao"], Status> = {
  resolve: "verde", nao_resolve: "vermelho", sem_preco: "amarelo", incompleta: "amarelo",
};

/** A marca que o título tem a mais que a descrição genérica (só uma sugestão; a pessoa confere). */
const PALAVRAS_VAZIAS = new Set(["de", "da", "do", "das", "dos", "e", "com", "para", "até", "ate", "em", "sem", "c/", "-", "|"]);

/** Palpite da marca: a primeira palavra do título que não está na descrição ("Grampeador de Mesa Spiral…" → Spiral). */
function marcaDoTitulo(titulo: string, termo: string): string {
  const base = new Set(termo.toLowerCase().split(/\s+/));
  return titulo.split(/\s+/).find((p) => !base.has(p.toLowerCase()) && !PALAVRAS_VAZIAS.has(p.toLowerCase()) && !/\d/.test(p)) ?? "";
}

function UsarAlternativa({ item, tarefaId, resultado, indice, aoCancelar, aoTrocar }: {
  item: ItemRevisao; tarefaId: string; resultado: ResultadoAlternativas; indice: number;
  aoCancelar: () => void; aoTrocar: () => void;
}) {
  const opcao = resultado.opcoes[indice];
  const [descricao, setDescricao] = useState(resultado.termo);
  const [marca, setMarca] = useState(opcao.marca ?? marcaDoTitulo(opcao.titulo, resultado.termo));
  const [justificativa, setJustificativa] = useState(
    `Saída 1 (D-23): ${item.descricao}${item.marca ? ` (${item.marca})` : ""} passa da média na loja escolhida; ` +
    `troca por ${opcao.titulo}, que aparece nas 3 lojas do orçamento.`);
  return (
    <Formulario rotulo="Trocar o produto e capturar as provas" aoCancelar={aoCancelar} aoEnviar={async () => {
      await api.criar(`/api/itens/${item.id}/usar-alternativa`, { tarefa_id: tarefaId, indice, descricao, marca, justificativa });
      aoTrocar();
    }}>
      <p>Novo produto: <strong>{opcao.titulo}</strong></p>
      <div className="linha-campos">
        <Campo rotulo="Descrição"><input value={descricao} onChange={(e) => setDescricao(e.target.value)} /></Campo>
        <Campo rotulo="Marca" ajuda="Confira: o sistema tirou do título do produto."><input value={marca} onChange={(e) => setMarca(e.target.value)} /></Campo>
      </div>
      <Campo rotulo="Justificativa"><textarea value={justificativa} onChange={(e) => setJustificativa(e.target.value)} rows={3} /></Campo>
      <p className="discreto pequeno">
        O item antigo sai do orçamento e fica no histórico, com as pesquisas dele. As 3 páginas entram na fila para virar
        prova; confira depois, na tabela, se cada uma é o mesmo produto (🟢) e se o preço ficou dentro da média.
      </p>
    </Formulario>
  );
}

function AlternativasDoItem({ item, tarefaId, aoIniciar, aoFechar, aoTrocar }: {
  item: ItemRevisao; tarefaId: string | null; aoIniciar: (tarefaId: string) => void; aoFechar: () => void; aoTrocar: () => void;
}) {
  const tarefa = useTarefa(tarefaId);
  const [escolhida, setEscolhida] = useState<number | null>(null);
  const resultado = tarefa?.estado === "concluida" ? (tarefa.resultado as unknown as ResultadoAlternativas) : null;
  const procurar = async () => {
    setEscolhida(null);
    aoIniciar((await api.criar<Tarefa>(`/api/itens/${item.id}/alternativas`)).id);
  };
  return (
    <Modal titulo={`Procurar outra marca — ${item.descricao}`} aoFechar={aoFechar}>
      <p className="explicacao">
        O sistema procura o item <strong>sem a marca</strong>{item.marca ? ` (${item.marca})` : ""} nas 3 lojas do orçamento,
        junta os produtos que aparecem nas três e faz a conta com os preços que a busca mostra. É uma <strong>prévia, sem
        prova</strong>: nada muda até você escolher. Aí o produto é trocado (o antigo fica no histórico) e as páginas dele
        nas 3 lojas são capturadas como prova (Saída 1, D-23).
      </p>
      {!tarefaId && <div className="acoes"><BotaoAcao aoClicar={procurar}>Procurar</BotaoAcao></div>}
      {tarefaId && (!tarefa || ativa(tarefa)) && (
        <Aviso tipo="info">Procurando… {tarefa?.mensagem ?? ""} {tarefa ? `(${tarefa.progresso}%)` : ""}</Aviso>
      )}
      {tarefa && (tarefa.estado === "falhou" || tarefa.estado === "cancelada") && (
        <>
          <Aviso tipo="erro">{tarefa.mensagem ?? "A busca não terminou."}</Aviso>
          <div className="acoes"><BotaoAcao classe="secundario" aoClicar={procurar}>Procurar de novo</BotaoAcao></div>
        </>
      )}
      {resultado && tarefaId && escolhida === null && (
        <>
          <Aviso tipo={resultado.opcoes.some((o) => o.situacao === "resolve") ? "ok" : "atencao"}>
            {resultado.mensagem}. Busca por “{resultado.termo}”.
          </Aviso>
          {resultado.avisos.length > 0 && <ul className="pequeno">{resultado.avisos.map((a) => <li key={a}>{a}</li>)}</ul>}
          {resultado.opcoes.length > 0 && (
            <div className="rolagem">
              <table className="tabela">
                <thead>
                  <tr>
                    <th>Produto</th>
                    {resultado.lojas.map((l) => <th key={l.loja_id} className="n">{l.loja}</th>)}
                    <th className="n">Média</th>
                    <th>Resultado pela prévia</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {resultado.opcoes.map((o, n) => (
                    <tr key={n}>
                      <td>{o.titulo}</td>
                      {o.lojas.map((l) => (
                        <td key={l.loja_id} className="n">
                          {l.url ? <a href={l.url} target="_blank" rel="noreferrer">{l.preco_centavos ? reais(l.preco_centavos) : "ver"}</a> : <span className="discreto">—</span>}
                        </td>
                      ))}
                      <td className="n">{o.media ?? "—"}</td>
                      <td>
                        <Selo status={SITUACAO_DA_ALTERNATIVA[o.situacao]} texto={o.situacao === "resolve" ? "resolveria" : o.situacao === "nao_resolve" ? "não resolve" : "a conferir"} />
                        <div className="pequeno">{o.motivo}</div>
                        {o.impacto_centavos !== null && (
                          <div className="discreto pequeno">total da loja escolhida {o.impacto_centavos <= 0 ? "−" : "+"}{reais(Math.abs(o.impacto_centavos))}</div>
                        )}
                      </td>
                      <td>
                        {(o.situacao === "resolve" || o.situacao === "sem_preco") && (
                          <button className="secundario pequeno" onClick={() => setEscolhida(n)}>Escolher</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="discreto pequeno">
            Nenhuma serve? Tente a Saída 2 (trocar a loja) ou cole à mão os links de um produto nas 3 lojas, depois de trocar o
            produto em Itens e cargos.
          </p>
          <div className="acoes">
            <button className="secundario" onClick={aoFechar}>Fechar</button>
            <BotaoAcao classe="secundario" aoClicar={procurar}>Procurar de novo</BotaoAcao>
          </div>
        </>
      )}
      {resultado && tarefaId && escolhida !== null && (
        <UsarAlternativa item={item} tarefaId={tarefaId} resultado={resultado} indice={escolhida}
          aoCancelar={() => setEscolhida(null)} aoTrocar={aoTrocar} />
      )}
    </Modal>
  );
}

// --- Fechar o lote (D-72): produtos a confirmar e itens que faltam nas 3 lojas ---------------------

const precisaConfirmar = (i: ItemRevisao) =>
  !i.referencia && Object.values(i.ofertas).some(
    (o) => o.correspondencia && (o.correspondencia.status === "amarelo" || o.correspondencia.precisa_confirmar));

function ConfirmarProdutos({ lote, aoFechar, atualizar }: { lote: LoteRevisao; aoFechar: () => void; atualizar: () => void }) {
  const [feitos, setFeitos] = useState<Set<string>>(new Set());
  const itens = lote.itens.filter((i) => precisaConfirmar(i) || feitos.has(i.id));
  const marcar = (id: string) => setFeitos(new Set([...feitos, id]));
  return (
    <Modal titulo={`Confirmar produtos — ${lote.nome}`} aoFechar={aoFechar}>
      <p className="explicacao">
        Para cada item, clique em <strong>É este</strong> no produto certo. Ele vira o <strong>produto de referência</strong>:
        as outras lojas passam a ser comparadas com ele — o mesmo código de barras vira 🟢 sozinho; tamanho, gramatura ou
        quantidade diferente vira 🔴 (D-71). As fotos ajudam, mas não bastam: confira o título, a marca e o tamanho.
      </p>
      {itens.length === 0 && <Aviso tipo="ok">Nada para confirmar agora.</Aviso>}
      {itens.map((i) => (
        <div key={i.id} className="bloco">
          <h3>{i.descricao} <span className="discreto">{[i.marca, i.modelo, i.apresentacao].filter(Boolean).join(" · ")}</span></h3>
          {i.referencia && (
            <Aviso tipo="ok">
              Produto de referência: {i.referencia.titulo} ({i.referencia.loja}). As outras lojas foram comparadas com ele.
            </Aviso>
          )}
          <div className="cartoes-produto">
            {lote.lojas.filter((l) => i.ofertas[l.id]).map((l) => {
              const o = i.ofertas[l.id];
              const referencia = i.referencia?.url === o.url;
              const recusado = o.correspondencia?.status === "vermelho";
              return (
                <div key={l.id} className={`cartao-produto ${referencia ? "referencia" : ""}`}>
                  <Foto src={o.imagem} alt={o.titulo ?? ""} />
                  <strong className="pequeno">{l.nome}</strong>
                  <span className="pequeno">{o.titulo ?? "—"}</span>
                  <span>{reais(o.preco_centavos)} <SeloDaOferta oferta={o} /></span>
                  {o.url && <a className="pequeno" href={o.url} target="_blank" rel="noreferrer noopener">abrir a página</a>}
                  {referencia && <span className="pequeno"><strong>produto de referência</strong></span>}
                  {!referencia && !recusado && !i.referencia && (
                    <div className="botoes">
                      <BotaoAcao classe="pequeno" aoClicar={async () => {
                        await api.criar(`/api/itens/${i.id}/referencia`, {
                          observacao_id: o.observacao_id, justificativa: "Conferi a página: é o produto do item (D-71).",
                        });
                        marcar(i.id);
                        atualizar();
                      }}>É este</BotaoAcao>
                      <BotaoAcao classe="secundario pequeno" aoClicar={async () => {
                        await api.criar("/api/correspondencias", {
                          item_id: i.id, observacao_id: o.observacao_id, status: "vermelho", justificativa: "Não é o produto do item.",
                        });
                        marcar(i.id);
                        atualizar();
                      }}>Não é</BotaoAcao>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
      <div className="acoes"><button onClick={aoFechar}>Fechar</button></div>
    </Modal>
  );
}

interface OpcaoDoFechamento {
  titulo: string;
  marca: string | null;
  soma_centavos: number | null;
  situacao: "completa" | "sem_preco";
  motivo: string;
  lojas: { loja_id: string; loja: string; url: string; preco_centavos: number | null }[];
}

interface SituacaoDoFechamento {
  itens: number;
  lojas: { id: string; nome: string; tem: number; faltam: string[] }[];
  melhores: string[];
  faltando: { item_id: string; item: string; lojas: string[] }[];
  a_confirmar: { item_id: string; item: string }[];
  ultima: null | {
    tarefa_id: string; estado: Tarefa["estado"]; mensagem: string | null; progresso: number;
    alternativas: Record<string, OpcaoDoFechamento[]>; avisos: string[];
  };
}

function TrocaDoFechamento({ item, tarefaId, indice, opcao, aoFechar, aoTrocar }: {
  item: ItemRevisao; tarefaId: string; indice: number; opcao: OpcaoDoFechamento; aoFechar: () => void; aoTrocar: () => void;
}) {
  const [descricao, setDescricao] = useState(item.descricao);
  const [marca, setMarca] = useState(opcao.marca ?? marcaDoTitulo(opcao.titulo, item.descricao));
  const [justificativa, setJustificativa] = useState(
    `D-72: ${item.descricao}${item.marca ? ` (${item.marca})` : ""} não existe nas 3 lojas mais completas; ` +
    `troca por ${opcao.titulo}, que aparece nas 3.`);
  return (
    <Modal titulo={`Trocar ${item.descricao}`} aoFechar={aoFechar}>
      <Formulario rotulo="Trocar o produto e capturar as provas" aoCancelar={aoFechar} aoEnviar={async () => {
        await api.criar(`/api/itens/${item.id}/usar-alternativa`, { tarefa_id: tarefaId, indice, descricao, marca, justificativa });
        aoTrocar();
      }}>
        <p>Novo produto: <strong>{opcao.titulo}</strong></p>
        <ul className="pequeno">
          {opcao.lojas.map((l) => (
            <li key={l.loja_id}>{l.loja}: <a href={l.url} target="_blank" rel="noreferrer noopener">
              {l.preco_centavos ? reais(l.preco_centavos) : "ver"}</a></li>
          ))}
        </ul>
        <div className="linha-campos">
          <Campo rotulo="Descrição"><input value={descricao} onChange={(e) => setDescricao(e.target.value)} /></Campo>
          <Campo rotulo="Marca" ajuda="Confira: o sistema tirou do título do produto."><input value={marca} onChange={(e) => setMarca(e.target.value)} /></Campo>
        </div>
        <Campo rotulo="Justificativa"><textarea value={justificativa} onChange={(e) => setJustificativa(e.target.value)} rows={3} /></Campo>
        <p className="discreto pequeno">
          O item antigo sai do orçamento e fica no histórico. As páginas das 3 lojas entram na fila como prova; os preços que
          valem são os delas (os da busca são só uma prévia).
        </p>
      </Formulario>
    </Modal>
  );
}

function FechamentoDoLote({ lote, versao, atualizar, aoFechar }: {
  lote: LoteRevisao; versao: number; atualizar: () => void; aoFechar: () => void;
}) {
  const { dados } = useDados<SituacaoDoFechamento>(`/api/lotes/${lote.id}/fechamento`, versao);
  const [confirmar, setConfirmar] = useState(false);
  const [troca, setTroca] = useState<{ item: ItemRevisao; indice: number; opcao: OpcaoDoFechamento } | null>(null);
  if (!dados || dados.lojas.length === 0) return null;
  const ultima = dados.ultima;
  const rodando = ultima !== null && (ultima.estado === "pendente" || ultima.estado === "rodando");
  const melhores = dados.melhores.map((id) => dados.lojas.find((l) => l.id === id)!).filter(Boolean);
  const pronto = melhores.length >= 3 && dados.faltando.length === 0 && dados.a_confirmar.length === 0;
  const itemDe = (id: string) => lote.itens.find((i) => i.id === id);
  return (
    <div className="bloco fechamento">
      <div className="cabecalho-secao">
        <strong>Fechar o lote</strong>
        <button className="pequeno" onClick={aoFechar}>{ultima ? "Fechar de novo" : "Fechar o lote"}</button>
      </div>
      {rodando && <Aviso tipo="info">Fechando o lote… {ultima?.mensagem ?? ""} ({ultima?.progresso ?? 0}%)</Aviso>}
      {pronto && <Aviso tipo="ok">As 3 lojas mais completas têm todos os itens e os produtos estão confirmados.</Aviso>}
      <ol>
        <li>
          Lojas mais completas:{" "}
          {melhores.map((l) => `${l.nome} (${l.tem} de ${dados.itens})`).join(", ") || "nenhuma ainda"}
          {melhores.length < 3 && <span className="discreto"> — faltam lojas: use “Fechar o lote” com mais lojas.</span>}
        </li>
        {dados.a_confirmar.length > 0 && (
          <li>
            <strong>Confirme o produto de {dados.a_confirmar.length} item(ns)</strong>{" "}
            <button className="secundario pequeno" onClick={() => setConfirmar(true)}>Confirmar produtos</button>
            <div className="discreto pequeno">Um por item: as outras lojas passam a ser comparadas com ele (D-71).</div>
          </li>
        )}
        {dados.faltando.length > 0 && (
          <li>
            <strong>Itens que faltam nas 3 lojas mais completas</strong>
            <ul>
              {dados.faltando.map((f) => {
                const opcoes = ultima?.alternativas[f.item_id] ?? [];
                const item = itemDe(f.item_id);
                return (
                  <li key={f.item_id}>
                    {f.item} <span className="discreto">— falta em {f.lojas.join(", ")}</span>
                    {opcoes.map((o, n) => (
                      <div key={n} className="opcao-troca pequeno">
                        <span>outra marca: <strong>{o.titulo}</strong>{o.soma_centavos ? ` · soma ${reais(o.soma_centavos)}` : ` · ${o.motivo}`}</span>
                        {item && ultima && ultima.estado === "concluida" && (
                          <button className="secundario pequeno" onClick={() => setTroca({ item, indice: n, opcao: o })}>Trocar por este</button>
                        )}
                      </div>
                    ))}
                    {opcoes.length === 0 && (
                      <div className="discreto pequeno">
                        {ultima?.estado === "concluida"
                          ? "Sem sugestão de outra marca nas 3 lojas: cole links de outro produto ou feche com outras lojas."
                          : "Use “Fechar o lote” para o sistema procurar outra marca que exista nas 3 lojas."}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </li>
        )}
      </ol>
      {ultima && ultima.avisos.length > 0 && <ul className="pequeno">{ultima.avisos.map((a) => <li key={a}>{a}</li>)}</ul>}
      {confirmar && <ConfirmarProdutos lote={lote} aoFechar={() => setConfirmar(false)} atualizar={atualizar} />}
      {troca && ultima && (
        <TrocaDoFechamento item={troca.item} tarefaId={ultima.tarefa_id} indice={troca.indice} opcao={troca.opcao}
          aoFechar={() => setTroca(null)} aoTrocar={() => { setTroca(null); atualizar(); }} />
      )}
    </div>
  );
}

// --- Lote -----------------------------------------------------------------------------------------

function Lote({ lote, orcamento, versao, atualizar }: {
  lote: LoteRevisao; orcamento: OrcamentoRevisao; versao: number; atualizar: () => void;
}) {
  const [colar, setColar] = useState<ItemRevisao | null>(null);
  const [buscar, setBuscar] = useState<"busca" | "fechar" | null>(null);
  const [detalhe, setDetalhe] = useState<{ item: ItemRevisao; loja: LojaDoLote } | null>(null);
  const [simulacao, setSimulacao] = useState<null | { sucesso: boolean; mensagem: string; tentativas: { retirada: string; motivo: string }[] }>(null);
  const [alternativas, setAlternativas] = useState<ItemRevisao | null>(null);
  const [buscasDeAlternativas, setBuscasDeAlternativas] = useState<Record<string, string>>({});  // item → tarefa
  const [descoberta, setDescoberta] = useState<string | null>(null);  // tarefa da SerpApi
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
        <h3>
          Lote {lote.nome} <button className="pequeno" onClick={() => setBuscar("fechar")}>Fechar o lote</button>
          <button className="secundario pequeno" onClick={() => setBuscar("busca")}>Pesquisar nas lojas</button>
        </h3>
        <Selo status={lote.situacao === "ok" ? (temAcima ? "vermelho" : "verde") : "amarelo"}
          texto={lote.situacao === "ok" ? (temAcima ? "item acima da média" : `${orcamento.fontes_por_cotacao} lojas escolhidas`) : lote.situacao === "sem_trio" ? "faltam lojas completas" : "sem pesquisa"} />
      </div>
      {lote.mensagem && <p className="discreto">{lote.mensagem}</p>}
      {lote.sugestoes.length > 0 && <Aviso tipo="info"><ul>{lote.sugestoes.map((s) => <li key={s}>{s}</li>)}</ul></Aviso>}
      <FechamentoDoLote lote={lote} versao={versao} atualizar={atualizar} aoFechar={() => setBuscar("fechar")} />
      {temAcima && orcamento.base_preco_final === "B" && (
        <Aviso tipo="atencao">
          <p>Na regra B, o preço da loja escolhida precisa estar dentro da média. Há duas saídas, e você escolhe (D-23):</p>
          <ul>
            <li>
              <strong>Trocar o produto</strong> (Saída 1): use “procurar outra marca” no item acima da média. O sistema procura
              nas 3 lojas do orçamento e mostra quais produtos resolveriam.
            </li>
            <li>
              <strong>Trocar a loja</strong> (Saída 2): a loja escolhida sai e a próxima da classificação entra.{" "}
              <BotaoAcao classe="secundario pequeno" aoClicar={async () => setSimulacao(await api.obter(`/api/lotes/${lote.id}/simular-troca-de-loja`))}>
                Simular a troca de loja
              </BotaoAcao>{" "}
              <button className="secundario pequeno" onClick={() => setBuscar("busca")}>Pesquisar outras lojas</button>
            </li>
          </ul>
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
                  {i.referencia && <div className="discreto pequeno">produto de referência: {i.referencia.loja}</div>}
                  <button className="link pequeno" onClick={() => setColar(i)}>+ colar link</button>
                  {i.dentro_da_media === false && orcamento.base_preco_final === "B" && (
                    <> · <button className="link pequeno" onClick={() => setAlternativas(i)}>procurar outra marca</button></>
                  )}
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
      {buscar && <BuscarNasLojas lote={lote} fechar={buscar === "fechar"} aoFechar={() => setBuscar(null)}
        aoIniciar={() => { setBuscar(null); atualizar(); }}
        aoDescobrir={(t) => { setBuscar(null); setDescoberta(t); atualizar(); }} />}
      {descoberta && <DescobertaNaWeb tarefaId={descoberta} aoFechar={() => setDescoberta(null)}
        aoColetar={() => { setDescoberta(null); atualizar(); }} />}
      {detalhe && <DetalheDaOferta item={detalhe.item} loja={detalhe.loja} aoFechar={() => setDetalhe(null)} atualizar={atualizar} />}
      {alternativas && (
        <AlternativasDoItem item={alternativas} tarefaId={buscasDeAlternativas[alternativas.id] ?? null}
          aoIniciar={(t) => { setBuscasDeAlternativas({ ...buscasDeAlternativas, [alternativas.id]: t }); atualizar(); }}
          aoFechar={() => setAlternativas(null)} aoTrocar={() => { setAlternativas(null); atualizar(); }} />
      )}
      {simulacao && (
        <Modal titulo="Simulação da troca de loja (Saída 2)" aoFechar={() => setSimulacao(null)}>
          <Aviso tipo={simulacao.sucesso ? "ok" : "atencao"}>{simulacao.mensagem}</Aviso>
          <ol>{simulacao.tentativas.map((t, n) => <li key={n}>Retirando <strong>{t.retirada}</strong>: {t.motivo}</li>)}</ol>
          <p className="discreto">
            Nada foi mudado. Para aplicar, use “retirar” na loja. Se a próxima loja ainda não tem todos os itens, use
            “Pesquisar outras lojas”.
          </p>
        </Modal>
      )}
      {janela}
    </div>
  );
}

// --- Pesquisar vagas pela janela (Fase 2, etapa 11; D-69) ---------------------------------------------

interface PlataformaDeVagas {
  id: string;
  nome: string;
  abrir_vaga: "sistema" | "janela";
  motivo: string;
}

function lerLocal(chave: string): string {
  try {
    return localStorage.getItem(chave) ?? "";
  } catch {
    return "";
  }
}

function gravarLocal(chave: string, valor: string) {
  try {
    localStorage.setItem(chave, valor);
  } catch {
    /* sem armazenamento: só não lembra da cidade */
  }
}

interface VagaDoGoogle {
  titulo: string;
  empresa: string | null;
  local: string | null;
  salario: string | null;
  publicada: string | null;
  plataforma: string | null;
  url: string | null;
  situacao: "capturada" | "ja_tinha" | "janela" | "outro_site" | "sem_link" | "erro" | "sistema";
  mensagem: string | null;
}

const SITUACAO_DA_VAGA: Record<VagaDoGoogle["situacao"], string> = {
  capturada: "capturada pelo sistema", ja_tinha: "já estava na pesquisa", janela: "abrir na janela (a plataforma proíbe programas)",
  outro_site: "site da empresa ou outro", sem_link: "sem link", erro: "não deu para capturar", sistema: "não capturada (limite de 6)",
};

/** Google Vagas (D-69 revista): o que o sistema capturou sozinho e o que fica para você abrir. */
function VagasDoGoogle({ cargo, tarefaId, aoFechar, atualizar }: {
  cargo: CargoRevisao; tarefaId: string; aoFechar: () => void; atualizar: () => void;
}) {
  const tarefa = useTarefa(tarefaId);
  const [pedidas, setPedidas] = useState<Set<string>>(new Set());
  const resultado = tarefa?.estado === "concluida" ? (tarefa.resultado as unknown as { vagas: VagaDoGoogle[]; mensagem: string }) : null;
  const abrir = async (url: string) => {
    await api.criar(`/api/cargos/${cargo.id}/coletas`, { url });  // Indeed e LinkedIn vão para a janela (D-69)
    setPedidas(new Set([...pedidas, url]));
    atualizar();
  };
  return (
    <Modal titulo={`Google Vagas — ${cargo.nome}`} aoFechar={aoFechar}>
      <p className="explicacao">
        O Google junta as vagas de várias plataformas. As da Catho, da InfoJobs e da Vagas.com o sistema captura sozinho
        (até 6, primeiro as que mostram salário). As do Indeed e do LinkedIn abrem na janela, e você clica em “Capturar agora”.
        O salário que o Google mostra não é prova: vale o que está na página da vaga.
      </p>
      {(!tarefa || ativa(tarefa)) && <Aviso tipo="info">Procurando… {tarefa?.mensagem ?? ""} {tarefa ? `(${tarefa.progresso}%)` : ""}</Aviso>}
      {tarefa && (tarefa.estado === "falhou" || tarefa.estado === "cancelada") && <Aviso tipo="erro">{tarefa.mensagem ?? "A busca não terminou."}</Aviso>}
      {resultado && (
        <>
          <Aviso tipo="ok">{resultado.mensagem}</Aviso>
          <table className="tabela">
            <thead><tr><th>Empresa</th><th>Vaga</th><th>Salário no Google</th><th>Onde</th><th>Situação</th></tr></thead>
            <tbody>
              {resultado.vagas.map((v, n) => (
                <tr key={n}>
                  <td>{v.empresa ?? "—"}<div className="discreto pequeno">{v.local}</div></td>
                  <td>{v.titulo}<div className="discreto pequeno">{v.publicada}</div></td>
                  <td>{v.salario ?? "—"}</td>
                  <td>{v.url ? <a href={v.url} target="_blank" rel="noreferrer noopener">{v.plataforma ?? "site"}</a> : "—"}</td>
                  <td>
                    <span className="pequeno">{SITUACAO_DA_VAGA[v.situacao]}</span>
                    {v.mensagem && <div className="discreto pequeno">{v.mensagem}</div>}
                    {v.url && (v.situacao === "janela" || v.situacao === "outro_site" || v.situacao === "sistema") && (
                      pedidas.has(v.url)
                        ? <div className="pequeno">pedido: veja o quadro Tarefas</div>
                        : <BotaoAcao classe="secundario pequeno" aoClicar={() => abrir(v.url!)}>
                            {v.situacao === "janela" ? "Abrir na janela" : "Ler a página"}
                          </BotaoAcao>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      <div className="acoes"><button onClick={aoFechar}>Fechar</button></div>
    </Modal>
  );
}

function PesquisarVagas({ cargo, aoFechar, aoIniciar, aoGoogle }: {
  cargo: CargoRevisao; aoFechar: () => void; aoIniciar: () => void; aoGoogle: (tarefaId: string) => void;
}) {
  const { dados: plataformas, erro } = useDados<PlataformaDeVagas[]>("/api/plataformas-de-vagas");
  const { dados: opcionais } = useDados<EstadoOpcionais>("/api/opcionais");
  const [marcadas, setMarcadas] = useState<Set<string>>(new Set(["catho", "infojobs", "vagas_com"]));
  const [cidade, setCidade] = useState(() => lerLocal("orca.vagas.cidade"));
  const [uf, setUf] = useState(() => lerLocal("orca.vagas.uf"));
  const alternar = (id: string) => {
    const nova = new Set(marcadas);
    if (nova.has(id)) nova.delete(id);
    else nova.add(id);
    setMarcadas(nova);
  };
  return (
    <Modal titulo={`Pesquisar vagas — ${cargo.nome}`} aoFechar={aoFechar}>
      <p className="explicacao">
        As plataformas de vagas não permitem que programas façam buscas (termos de uso ou regras para robôs, conferidos em
        24/09/2026). Então <strong>quem pesquisa é você</strong>: para cada plataforma, abre uma janela na busca já preenchida
        com o cargo e a cidade. Clique numa vaga com salário e empresa, e depois em <strong>“Capturar agora”</strong>, no
        quadro Tarefas. O sistema guarda a prova e lê o salário e a empresa. Repita até ter as vagas válidas que as regras pedem (normalmente 3, D-40).
      </p>
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {!plataformas && !erro && <Carregando />}
      {plataformas && (
        <Formulario rotulo="Abrir as janelas" aoCancelar={aoFechar} aoEnviar={async () => {
          if (marcadas.size === 0) throw new Error("Escolha ao menos uma plataforma.");
          gravarLocal("orca.vagas.cidade", cidade);
          gravarLocal("orca.vagas.uf", uf);
          await api.criar(`/api/cargos/${cargo.id}/busca-de-vagas`, {
            plataformas: [...marcadas], cidade: cidade.trim() || null, uf: uf.trim() || null,
          });
          aoIniciar();
        }}>
          <div className="lista-lojas">
            {plataformas.map((p) => (
              <label key={p.id} className="marcador" title={p.motivo}>
                <input type="checkbox" checked={marcadas.has(p.id)} onChange={() => alternar(p.id)} />
                {p.nome}
                {p.id === "linkedin" && <span className="discreto pequeno"> · pede login: entre com a sua conta só se quiser</span>}
              </label>
            ))}
          </div>
          <div className="linha-campos">
            <Campo rotulo="Cidade" ajuda="Em branco: vagas de todo o Brasil."><input value={cidade} onChange={(e) => setCidade(e.target.value)} placeholder="São Paulo" /></Campo>
            <Campo rotulo="UF"><input value={uf} onChange={(e) => setUf(e.target.value.toUpperCase().slice(0, 2))} placeholder="SP" /></Campo>
          </div>
          <p className="discreto pequeno">As janelas abrem uma de cada vez, na ordem; o quadro Tarefas mostra qual está esperando você.</p>
        </Formulario>
      )}
      <h3>Google Vagas (opcional)</h3>
      {opcionais?.serpapi.chave ? (
        <p className="discreto pequeno">
          O sistema procura “{cargo.nome}” no Google Vagas, na cidade acima, e captura sozinho as vagas das plataformas que
          permitem (gasta 1 busca do seu plano grátis da SerpApi).{" "}
          <BotaoAcao classe="secundario pequeno" aoClicar={async () => {
            gravarLocal("orca.vagas.cidade", cidade);
            gravarLocal("orca.vagas.uf", uf);
            const t = await api.criar<Tarefa>(`/api/cargos/${cargo.id}/vagas-google`, { cidade: cidade.trim() || null, uf: uf.trim() || null });
            aoGoogle(t.id);
          }}>Procurar no Google Vagas</BotaoAcao>
        </p>
      ) : (
        <p className="discreto pequeno">Com uma chave grátis da SerpApi (em Opcionais, no alto da página), o sistema procura no Google Vagas sozinho.</p>
      )}
    </Modal>
  );
}

// --- Cargo ------------------------------------------------------------------------------------------

function CargoPesquisa({ cargo, atualizar }: { cargo: CargoRevisao; atualizar: () => void }) {
  const [colar, setColar] = useState(false);
  const [pesquisar, setPesquisar] = useState(false);
  const [google, setGoogle] = useState<string | null>(null);  // tarefa do Google Vagas
  const [janela, pedir] = useDecisao();
  const nomeDaVaga = (id: string) => {
    const v = cargo.vagas.find((x) => x.id === id);
    return v ? `${v.empresa ?? "empresa?"} (${v.plataforma})` : id;
  };
  return (
    <div className="lote">
      <div className="cabecalho-secao">
        <h3><Selo status={cargo.status} /> {cargo.nome} <span className="discreto">· {REGIMES[cargo.regime]} · {horas(cargo.horas_planejadas_centesimos)} h/mês · {cargo.postos} posto(s)</span></h3>
        <span className="botoes">
          <button className="secundario pequeno" onClick={() => setPesquisar(true)}>Pesquisar vagas</button>
          <button className="secundario pequeno" onClick={() => setColar(true)}>+ colar link de vaga</button>
        </span>
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
      {pesquisar && <PesquisarVagas cargo={cargo} aoFechar={() => setPesquisar(false)} aoIniciar={() => { setPesquisar(false); atualizar(); }}
        aoGoogle={(t) => { setPesquisar(false); setGoogle(t); atualizar(); }} />}
      {google && <VagasDoGoogle cargo={cargo} tarefaId={google} aoFechar={() => setGoogle(null)} atualizar={atualizar} />}
      {janela}
    </div>
  );
}

// --- Validade das pesquisas (D-12; Fase 2, etapa 12) ---------------------------------------------------

interface PesquisaVencendo {
  observacao_id: string;
  nome: string;
  loja: string;
  url: string;
  valida_ate: string;
  situacao: "vencida" | "vence_antes_da_entrega" | "vence_em_breve";
  como: "coletar_item" | "coletar_cargo" | "captura_assistida" | "pdf";
}

const SITUACAO_DA_VALIDADE = {
  vencida: "venceu", vence_antes_da_entrega: "vence antes da entrega", vence_em_breve: "vence em breve",
} as const;

function ValidadeDasPesquisas({ projetoId, versao, atualizar }: { projetoId: string; versao: number; atualizar: () => void }) {
  const { dados } = useDados<{ pesquisas: PesquisaVencendo[] }>(`/api/projetos/${projetoId}/validade`, versao);
  const [aviso, setAviso] = useState<string | null>(null);
  if (!dados || dados.pesquisas.length === 0) return null;
  const refazer = async (observacoes?: string[]) => {
    const r = await api.criar<{ tarefas: unknown[]; so_pela_pessoa: string[] }>(`/api/projetos/${projetoId}/pesquisar-de-novo`,
      observacoes ? { observacoes } : {});
    setAviso(r.so_pela_pessoa.length > 0
      ? `Estas provas foram PDFs enviados por você; salve e envie o PDF de novo: ${r.so_pela_pessoa.join("; ")}.`
      : null);
    atualizar();
  };
  const data = (iso: string) => iso.split("-").reverse().join("/");
  return (
    <div className="bloco">
      <div className="cabecalho-secao">
        <h2>Pesquisas vencidas ou vencendo</h2>
        <BotaoAcao aoClicar={() => refazer()}>Pesquisar todas de novo</BotaoAcao>
      </div>
      <p className="discreto pequeno">
        Cada pesquisa vale pelo prazo das regras (D-12). Pesquisar de novo abre a mesma página e guarda uma prova nova; a
        antiga fica no histórico. Páginas capturadas na janela abrem a janela de novo.
      </p>
      {aviso && <Aviso tipo="atencao">{aviso}</Aviso>}
      <table className="tabela">
        <tbody>
          {dados.pesquisas.map((p) => (
            <tr key={p.observacao_id}>
              <td><Selo status={p.situacao === "vence_em_breve" ? "amarelo" : "vermelho"} texto={SITUACAO_DA_VALIDADE[p.situacao]} /></td>
              <td>{p.nome}<div className="discreto pequeno">{p.loja} · vale até {data(p.valida_ate)}</div></td>
              <td>
                {p.como === "pdf"
                  ? <span className="discreto pequeno">PDF enviado por você: salve e envie de novo (colar link → PDF)</span>
                  : <BotaoAcao classe="secundario pequeno" aoClicar={() => refazer([p.observacao_id])}>
                      {p.como === "captura_assistida" ? "Pesquisar de novo (janela)" : "Pesquisar de novo"}
                    </BotaoAcao>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function IaConfereAmarelos({ projetoId, revisao, atualizar }: { projetoId: string; revisao: Revisao; atualizar: () => void }) {
  const { dados: opcionais } = useDados<EstadoOpcionais>("/api/opcionais");
  const amarelos = revisao.orcamentos.flatMap((o) => o.lotes).flatMap((l) => l.itens).flatMap((i) => Object.values(i.ofertas))
    .filter((o) => o.correspondencia?.status === "amarelo" && o.correspondencia.origem !== "humano" && o.correspondencia.origem !== "ia").length;
  if (!opcionais?.ia.ligada || amarelos === 0) return null;
  return (
    <Aviso tipo="info">
      {amarelos} preço(s) 🟡 esperando conferência. A IA pode olhar primeiro: ela só rebaixa para 🔴 o que for claramente outro
      produto, com o motivo; os outros continuam 🟡 para você decidir (D-52).{" "}
      <BotaoAcao classe="secundario pequeno" aoClicar={async () => { await api.criar(`/api/projetos/${projetoId}/julgar-amarelos`); atualizar(); }}>
        Pedir à IA para conferir
      </BotaoAcao>
    </Aviso>
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
      <ValidadeDasPesquisas projetoId={projeto.id} versao={versao} atualizar={atualizar} />
      <IaConfereAmarelos projetoId={projeto.id} revisao={dados} atualizar={atualizar} />
      {dados.orcamentos.map((o) => (
        <div key={o.id} className="bloco">
          <h2>{o.nome} <span className="discreto">· regra {o.base_preco_final} {o.base_preco_final === "B" ? "(preço da loja de menor total)" : "(média)"}</span></h2>
          {o.lotes.map((l) => <Lote key={l.id} lote={l} orcamento={o} versao={versao} atualizar={atualizar} />)}
          {o.cargos.map((c) => <CargoPesquisa key={c.id} cargo={c} atualizar={atualizar} />)}
          {o.lotes.length === 0 && o.cargos.length === 0 && <p className="discreto">Nada cadastrado neste orçamento.</p>}
        </div>
      ))}
    </div>
  );
}
