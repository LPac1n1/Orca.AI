import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { Aviso, BotaoAcao, Campo, Carregando, Formulario, Modal, Selo } from "../componentes";
import { dataHora } from "../formatos";
import { useDados } from "../ganchos";
import type {
  AtributosDados, CatalogoDeAtributos, CatalogoDeLojas, LojaDados, Organizacao, Pares, ResultadoDoTeste, ResumoDoTeste,
  VersaoDoCatalogo,
} from "../tipos";

const nome = (chave: string) => chave.replace(/_/g, " ");
const chaveDe = (texto: string) =>
  texto.trim().toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");

function Historico({ versoes }: { versoes: VersaoDoCatalogo[] }) {
  if (versoes.length === 0) return <p className="discreto pequeno">Ainda igual ao catálogo do sistema.</p>;
  return (
    <details className="pequeno">
      <summary>Versão {versoes[0].versao} da OSC · {dataHora(versoes[0].criado_em)} · {versoes[0].autor}</summary>
      <ul>{versoes.map((v) => <li key={v.versao}>versão {v.versao} · {dataHora(v.criado_em)} · {v.autor}{v.resumo ? ` — ${v.resumo}` : ""}</li>)}</ul>
    </details>
  );
}

function Chips({ itens, aoRetirar }: { itens: string[]; aoRetirar: (i: string) => void }) {
  return (
    <span className="chips">
      {itens.map((i) => (
        <span key={i} className="chip">
          {i}
          <button type="button" aria-label={`Retirar ${i}`} title="Retirar" onClick={() => aoRetirar(i)}>×</button>
        </span>
      ))}
    </span>
  );
}

function CampoDeAcrescentar({ dica, aoAcrescentar }: { dica: string; aoAcrescentar: (texto: string) => void }) {
  const [texto, setTexto] = useState("");
  const acrescentar = () => {
    texto.split(",").map((t) => t.trim()).filter(Boolean).forEach(aoAcrescentar);
    setTexto("");
  };
  const tecla = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      acrescentar();
    }
  };
  return (
    <span className="acrescentar">
      <input value={texto} onChange={(e) => setTexto(e.target.value)} onKeyDown={tecla} placeholder={dica} />
      <button type="button" className="secundario pequeno" onClick={acrescentar} disabled={!texto.trim()}>+</button>
    </span>
  );
}

function resumoDoTeste(r: ResumoDoTeste) {
  const c = (k: string) => r.contagem[k] ?? 0;
  return `${r.total} pares · produtos diferentes aceitos como iguais (🟢 errado): ${r.falsos_verdes} · produtos iguais: ` +
    `${c("mesmo:verde")} 🟢, ${c("mesmo:amarelo")} 🟡 (pedem conferência), ${c("mesmo:vermelho")} 🔴`;
}

// --- Vocabulário e categorias (um só catálogo: atributos) -------------------------------------------------

function SalvarAtributos({ organizacaoId, editado, aoFechar, aoSalvar }: {
  organizacaoId: string; editado: AtributosDados; aoFechar: () => void; aoSalvar: () => void;
}) {
  const [teste, setTeste] = useState<ResultadoDoTeste | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [resumo, setResumo] = useState("");
  const rota = `/api/organizacoes/${organizacaoId}/catalogos/atributos`;
  useEffect(() => {
    api.criar<ResultadoDoTeste>(`${rota}/conferir`, { conteudo: editado }).then(setTeste).catch((e: Error) => setErro(e.message));
  }, [rota, editado]);
  return (
    <Modal titulo="Conferir e salvar as mudanças" aoFechar={aoFechar}>
      <p className="explicacao">
        Antes de salvar, o sistema compara de novo todos os pares de exemplo (os que vêm com o programa e os da OSC)
        com o vocabulário novo. Se algum par de produtos <strong>diferentes</strong> virar 🟢, a mudança é recusada (D-65).
      </p>
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {!teste && !erro && <Carregando />}
      {teste && (
        <>
          <p className="pequeno"><strong>Antes:</strong> {resumoDoTeste(teste.antes)}</p>
          <p className="pequeno"><strong>Depois:</strong> {resumoDoTeste(teste.depois)}</p>
          {teste.aprovada
            ? <Aviso tipo="ok">Nenhum par de produtos diferentes vira 🟢. Pode salvar.</Aviso>
            : (
              <Aviso tipo="erro">
                A mudança faria produtos diferentes virarem 🟢:
                <ul>{teste.novos_falsos_verdes.map((p) => <li key={p.titulo_a + p.titulo_b}>“{p.titulo_a}” × “{p.titulo_b}”</li>)}</ul>
              </Aviso>
            )}
          {teste.pares_que_mudaram.length > 0 && (
            <details>
              <summary>{teste.pares_que_mudaram.length} par(es) mudam de resultado</summary>
              <table className="tabela pequeno">
                <tbody>
                  {teste.pares_que_mudaram.map((p, n) => (
                    <tr key={n}>
                      <td>{p.titulo_a}<div className="discreto">{p.titulo_b}</div></td>
                      <td>{p.rotulo === "mesmo" ? "mesmo produto" : "diferentes"}</td>
                      <td><Selo status={p.antes} texto={p.antes} /> → <Selo status={p.depois} texto={p.depois} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
          {teste.aprovada && (
            <Formulario rotulo="Salvar" aoCancelar={aoFechar} aoEnviar={async () => {
              await api.trocar(rota, { conteudo: editado, resumo: resumo.trim() || null });
              aoSalvar();
            }}>
              <Campo rotulo="O que mudou? (opcional)" ajuda="Fica no histórico do catálogo.">
                <input value={resumo} onChange={(e) => setResumo(e.target.value)} placeholder="ex.: “moidinho” como sinônimo de moído" />
              </Campo>
            </Formulario>
          )}
        </>
      )}
    </Modal>
  );
}

function NovoGrupo({ atributos, aoCriar, aoFechar }: {
  atributos: string[]; aoCriar: (atributo: string, grupo: string, valores: Record<string, string[]>) => void; aoFechar: () => void;
}) {
  const [atributo, setAtributo] = useState("");
  const [grupo, setGrupo] = useState("");
  const [valores, setValores] = useState("");
  return (
    <Modal titulo="Novo grupo de valores" aoFechar={aoFechar}>
      <p className="explicacao">
        Um grupo reúne valores que <strong>se excluem</strong>: se o item diz um e a página diz outro, são produtos diferentes.
        Ex.: atributo “tipo”, grupo “forma do café”: moído, em grãos, solúvel.
      </p>
      <Formulario rotulo="Criar grupo" aoCancelar={aoFechar} aoEnviar={async () => {
        const linhas = valores.split("\n").map((l) => l.trim()).filter(Boolean);
        if (!atributo.trim() || !grupo.trim() || linhas.length < 2) throw new Error("Preencha o atributo, o nome do grupo e pelo menos dois valores.");
        const dados: Record<string, string[]> = {};
        for (const linha of linhas) {
          const [valor, sinonimos = ""] = linha.split(":");
          const lista = [valor, ...sinonimos.split(",")].map((s) => s.trim()).filter(Boolean);
          dados[chaveDe(valor)] = [...new Set(lista)];
        }
        aoCriar(chaveDe(atributo), chaveDe(grupo), dados);
        aoFechar();
      }}>
        <Campo rotulo="Atributo" ajuda="Escolha um existente (tipo, sabor, fragrância, cor…) ou escreva um novo.">
          <input list="atributos-existentes" value={atributo} onChange={(e) => setAtributo(e.target.value)} required />
          <datalist id="atributos-existentes">{atributos.map((a) => <option key={a} value={a} />)}</datalist>
        </Campo>
        <Campo rotulo="Nome do grupo"><input value={grupo} onChange={(e) => setGrupo(e.target.value)} placeholder="ex.: sabor do suco" required /></Campo>
        <Campo rotulo="Valores, um por linha" ajuda="Depois de “:” vêm os sinônimos, separados por vírgula.">
          <textarea rows={5} value={valores} onChange={(e) => setValores(e.target.value)} placeholder={"uva: uva, de uva\nlaranja: laranja\nmaracuja: maracujá, maracuja"} />
        </Campo>
      </Formulario>
    </Modal>
  );
}

function Vocabulario({ editado, mudar }: { editado: AtributosDados; mudar: (f: (d: AtributosDados) => void) => void }) {
  const [filtro, setFiltro] = useState("");
  const [novoGrupo, setNovoGrupo] = useState(false);
  const busca = chaveDe(filtro).replace(/_/g, " ");
  const combina = (...textos: string[]) => !busca || textos.some((t) => nome(t).includes(busca));
  return (
    <div>
      <p className="explicacao">
        O vocabulário ensina ao sistema palavras que querem dizer a mesma coisa (<strong>sinônimos</strong>) e valores que
        <strong> se excluem</strong> dentro de um grupo. Ex.: “moído” e “torrado e moído” são o mesmo; “moído” e “em grãos”
        são produtos diferentes. Acentos e maiúsculas não importam.
      </p>
      <div className="linha-campos">
        <input className="busca" value={filtro} onChange={(e) => setFiltro(e.target.value)} placeholder="Procurar (ex.: café, moído, lavanda)" />
        <button className="secundario" onClick={() => setNovoGrupo(true)}>+ grupo novo</button>
      </div>
      {Object.entries(editado.vocabulario).map(([atributo, grupos]) => {
        const visiveis = Object.entries(grupos).filter(([g, valores]) =>
          combina(atributo, g, ...Object.keys(valores), ...Object.values(valores).flat()));
        if (visiveis.length === 0) return null;
        return (
          <div key={atributo} className="bloco">
            <h2>{nome(atributo)}</h2>
            {visiveis.map(([grupo, valores]) => (
              <details key={`${grupo}-${busca ? "procura" : ""}`} className="grupo-vocabulario" open={Boolean(busca)}>
                <summary>
                  <strong>{nome(grupo)}</strong>{" "}
                  <span className="discreto pequeno">· {Object.keys(valores).map(nome).join(", ")}</span>
                </summary>
                <div className="cabecalho-secao">
                  <span className="discreto pequeno">Valores que se excluem: se o item diz um e a página diz outro, são produtos diferentes.</span>
                  <button className="link pequeno" onClick={() => window.confirm(`Retirar o grupo “${nome(grupo)}”?`) &&
                    mudar((d) => { delete d.vocabulario[atributo][grupo]; })}>retirar grupo</button>
                </div>
                <table className="tabela">
                  <tbody>
                    {Object.entries(valores).map(([valor, sinonimos]) => (
                      <tr key={valor}>
                        <td className="valor"><strong>{nome(valor)}</strong></td>
                        <td>
                          <Chips itens={sinonimos} aoRetirar={(s) => mudar((d) => {
                            d.vocabulario[atributo][grupo][valor] = d.vocabulario[atributo][grupo][valor].filter((x) => x !== s);
                          })} />
                          <CampoDeAcrescentar dica="+ sinônimo" aoAcrescentar={(s) => mudar((d) => {
                            const lista = d.vocabulario[atributo][grupo][valor];
                            if (!lista.includes(s)) lista.push(s);
                          })} />
                        </td>
                        <td><button className="link pequeno" onClick={() => mudar((d) => { delete d.vocabulario[atributo][grupo][valor]; })}>retirar</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <CampoDeAcrescentar dica="+ valor novo neste grupo" aoAcrescentar={(v) => mudar((d) => {
                  const chave = chaveDe(v);
                  if (chave && !d.vocabulario[atributo][grupo][chave]) d.vocabulario[atributo][grupo][chave] = [v];
                })} />
              </details>
            ))}
          </div>
        );
      })}
      {novoGrupo && (
        <NovoGrupo atributos={Object.keys(editado.vocabulario)} aoFechar={() => setNovoGrupo(false)}
          aoCriar={(atributo, grupo, valores) => mudar((d) => {
            d.vocabulario[atributo] = { ...(d.vocabulario[atributo] ?? {}), [grupo]: valores };
          })} />
      )}
    </div>
  );
}

function Categorias({ editado, mudar, conhecidos }: {
  editado: AtributosDados; mudar: (f: (d: AtributosDados) => void) => void; conhecidos: string[];
}) {
  return (
    <div>
      <p className="explicacao">
        Para cada categoria, os atributos que precisam ser <strong>iguais</strong> para ser o mesmo produto. Além deles,
        {" "}{(editado.sempre ?? []).map(nome).join(", ")} são conferidos em todas. Medidas (peso, volume, folhas, gramatura…)
        o sistema lê sozinho; atributos de texto usam o vocabulário.
      </p>
      <table className="tabela">
        <thead><tr><th>Categoria</th><th>Atributos que precisam ser iguais</th><th /></tr></thead>
        <tbody>
          {Object.entries(editado.categorias).map(([categoria, atributos]) => (
            <tr key={categoria}>
              <td><strong>{nome(categoria)}</strong></td>
              <td>
                <Chips itens={atributos.map(nome)} aoRetirar={(a) => mudar((d) => {
                  d.categorias[categoria] = d.categorias[categoria].filter((x) => nome(x) !== a);
                })} />
                <select value="" onChange={(e) => e.target.value && mudar((d) => { d.categorias[categoria].push(e.target.value); })}>
                  <option value="">+ atributo…</option>
                  {conhecidos.filter((a) => !atributos.includes(a)).map((a) => <option key={a} value={a}>{nome(a)}</option>)}
                </select>
              </td>
              <td><button className="link pequeno" onClick={() => window.confirm(`Retirar a categoria “${nome(categoria)}”?`) &&
                mudar((d) => { delete d.categorias[categoria]; })}>retirar</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <CampoDeAcrescentar dica="+ categoria nova (ex.: brinquedo)" aoAcrescentar={(c) => mudar((d) => {
        const chave = chaveDe(c);
        if (chave && !d.categorias[chave]) d.categorias[chave] = [];
      })} />
    </div>
  );
}

// --- Lojas --------------------------------------------------------------------------------------------------

const COLETAS: Record<string, string> = {
  C0: "dados estruturados (API da loja)",
  C1: "o sistema lê a página",
  C2: "busca pelo código de barras",
  C3: "agente de IA",
  C4: "janela: você navega",
  proposta: "proposta por e-mail",
};

type Grupo = "lojas" | "fornecedores_servico";

type Busca = { modo: "api_vtex" | "pagina" | "assistida"; url: string; produto?: string };

const MODOS_DE_BUSCA: Record<string, string> = {
  "": "sem busca: só colando o link",
  pagina: "o sistema pesquisa na página de busca do site",
  assistida: "com janela: você escolhe o produto (lojas que recusam programas)",
  api_vtex: "API pública de catálogo (VTEX)",
};

function FormularioDeLoja({ inicial, grupo, aoSalvar, aoFechar }: {
  inicial: LojaDados | null; grupo: Grupo; aoSalvar: (l: LojaDados) => Promise<void>; aoFechar: () => void;
}) {
  const [l, setL] = useState<LojaDados>(inicial ?? { id: "", nome: "", dominio: "", coleta: "C1" });
  const campo = (chave: keyof LojaDados) => (e: { target: { value: string } }) => setL({ ...l, [chave]: e.target.value });
  const busca = (l.busca && typeof l.busca === "object" ? l.busca : null) as Busca | null;
  const mudarBusca = (parte: Partial<Busca>) => {
    const nova = { ...(busca ?? { modo: "pagina", url: "" }), ...parte } as Busca;
    setL({ ...l, busca: nova.modo ? nova : null });
  };
  return (
    <Modal titulo={inicial ? `Editar ${inicial.nome}` : grupo === "lojas" ? "Nova loja" : "Novo fornecedor de serviço"} aoFechar={aoFechar}>
      <Formulario aoCancelar={aoFechar} aoEnviar={async () => {
        const dominio = l.dominio.trim().replace(/^https?:\/\//, "").replace(/\/.*$/, "");
        await aoSalvar({ ...l, id: l.id || chaveDe(l.nome), nome: l.nome.trim(), dominio, busca: busca ?? null });
        aoFechar();
      }}>
        <Campo rotulo="Nome"><input value={l.nome} onChange={campo("nome")} required autoFocus /></Campo>
        <Campo rotulo="Endereço do site" ajuda="Só o domínio, ex.: www.loja.com.br"><input value={l.dominio} onChange={campo("dominio")} required /></Campo>
        <Campo rotulo="Como coletar">
          <select value={l.coleta} onChange={campo("coleta")}>
            {Object.entries(COLETAS).map(([k, v]) => <option key={k} value={k}>{k} — {v}</option>)}
          </select>
        </Campo>
        <label className="marcador">
          <input type="checkbox" checked={Boolean(l.marketplace)} onChange={(e) => setL({ ...l, marketplace: e.target.checked })} />
          É marketplace (vários vendedores: vale o CNPJ do vendedor, D-16)
        </label>
        <Campo rotulo="Preço a usar" ajuda="Se a página mostra mais de um preço (ex.: preco_por, preco_normal). D-60 a D-63.">
          <input value={String(l.preco_a_usar ?? "")} onChange={campo("preco_a_usar")} />
        </Campo>
        {grupo === "lojas" && (
          <>
            <Campo rotulo="Busca automática (Fase 2)">
              <select value={busca?.modo ?? ""} onChange={(e) => (e.target.value ? mudarBusca({ modo: e.target.value as Busca["modo"] }) : setL({ ...l, busca: null }))}>
                {Object.entries(MODOS_DE_BUSCA).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </Campo>
            {busca && (
              <div className="linha-campos">
                <Campo rotulo="Endereço da busca" ajuda="Pesquise algo no site e copie o endereço, trocando o que você digitou por {termo}.">
                  <input value={busca.url} onChange={(e) => mudarBusca({ url: e.target.value })} placeholder="https://www.loja.com.br/busca?q={termo}" />
                </Campo>
                {busca.modo === "pagina" && (
                  <Campo rotulo="Endereço de produto contém" ajuda="Um pedaço que só aparece nos links de produto, ex.: /produto/">
                    <input value={busca.produto ?? ""} onChange={(e) => mudarBusca({ produto: e.target.value })} />
                  </Campo>
                )}
              </div>
            )}
          </>
        )}
        <Campo rotulo="Observações"><textarea rows={2} value={String(l.observacoes ?? "")} onChange={campo("observacoes")} /></Campo>
      </Formulario>
    </Modal>
  );
}

function Lojas({ organizacaoId }: { organizacaoId: string }) {
  const rota = `/api/organizacoes/${organizacaoId}/catalogos/lojas`;
  const { dados, erro, recarregar } = useDados<CatalogoDeLojas>(rota);
  const [edicao, setEdicao] = useState<{ grupo: Grupo; loja: LojaDados | null } | null>(null);
  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!dados) return <Carregando />;
  const salvar = (grupo: Grupo, antiga: LojaDados | null) => async (nova: LojaDados) => {
    const conteudo = structuredClone(dados.vigente);
    conteudo[grupo] = antiga ? conteudo[grupo].map((x) => (x.id === antiga.id ? { ...x, ...nova } : x)) : [...conteudo[grupo], nova];
    await api.trocar(rota, { conteudo, resumo: `${antiga ? "editou" : "acrescentou"} ${nova.nome}` });
    recarregar();
  };
  const tabela = (grupo: Grupo, titulo: string) => (
    <div className="bloco">
      <div className="cabecalho-secao">
        <h2>{titulo}</h2>
        <button className="secundario pequeno" onClick={() => setEdicao({ grupo, loja: null })}>+ {grupo === "lojas" ? "loja" : "fornecedor"}</button>
      </div>
      <table className="tabela">
        <thead><tr><th>Nome</th><th>Site</th><th>Como coletar</th><th>Preço a usar</th><th /></tr></thead>
        <tbody>
          {dados.vigente[grupo].map((l) => (
            <tr key={l.id}>
              <td>{l.nome}{l.marketplace ? <span className="discreto pequeno"> · marketplace</span> : null}
                {l.observacoes ? <div className="discreto pequeno">{String(l.observacoes)}</div> : null}</td>
              <td className="url">{l.dominio}</td>
              <td>{COLETAS[l.coleta] ?? l.coleta}{l.busca && typeof l.busca === "object" ? <div className="discreto pequeno">busca: {MODOS_DE_BUSCA[(l.busca as Busca).modo] ?? (l.busca as Busca).modo}</div> : null}</td>
              <td>{String(l.preco_a_usar ?? "—")}</td>
              <td><button className="link pequeno" onClick={() => setEdicao({ grupo, loja: l })}>editar</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
  return (
    <div>
      <p className="explicacao">
        As lojas e fornecedores que o sistema conhece: o nome que aparece nos documentos, como a página é lida e qual preço
        vale quando a página mostra mais de um. Lojas novas também entram sozinhas quando você cola um link; aqui você ajusta.
      </p>
      <Historico versoes={dados.historico} />
      {tabela("lojas", "Lojas")}
      {tabela("fornecedores_servico", "Fornecedores de serviço")}
      {edicao && <FormularioDeLoja inicial={edicao.loja} grupo={edicao.grupo} aoFechar={() => setEdicao(null)}
        aoSalvar={salvar(edicao.grupo, edicao.loja)} />}
    </div>
  );
}

// --- Pares --------------------------------------------------------------------------------------------------

const ORIGEM_DO_PAR = { decisao: "decisão de uma pessoa", ean: "código de barras igual", usuario: "escrito à mão" };

function NovoPar({ organizacaoId, categorias, aoFechar, aoSalvar }: {
  organizacaoId: string; categorias: string[]; aoFechar: () => void; aoSalvar: () => void;
}) {
  const [p, setP] = useState({ titulo_a: "", marca_a: "", titulo_b: "", marca_b: "", categoria: "", rotulo: "diferente", motivo: "" });
  const campo = (chave: keyof typeof p) => (e: { target: { value: string } }) => setP({ ...p, [chave]: e.target.value });
  return (
    <Modal titulo="Novo par de exemplo" aoFechar={aoFechar}>
      <p className="explicacao">
        Escreva dois produtos como aparecem nas lojas e diga se são o mesmo produto. O sistema passa a usar este exemplo
        para conferir as mudanças no vocabulário. Útil quando ele confunde dois produtos.
      </p>
      <Formulario aoCancelar={aoFechar} aoEnviar={async () => {
        await api.criar(`/api/organizacoes/${organizacaoId}/pares`, { ...p, categoria: p.categoria || null,
          marca_a: p.marca_a || null, marca_b: p.marca_b || null, motivo: p.motivo || null });
        aoSalvar();
        aoFechar();
      }}>
        <div className="linha-campos">
          <Campo rotulo="Produto A"><input value={p.titulo_a} onChange={campo("titulo_a")} required placeholder="Detergente Ypê neutro 500ml" /></Campo>
          <Campo rotulo="Marca A"><input value={p.marca_a} onChange={campo("marca_a")} /></Campo>
        </div>
        <div className="linha-campos">
          <Campo rotulo="Produto B"><input value={p.titulo_b} onChange={campo("titulo_b")} required placeholder="Detergente Ypê limão 500ml" /></Campo>
          <Campo rotulo="Marca B"><input value={p.marca_b} onChange={campo("marca_b")} /></Campo>
        </div>
        <Campo rotulo="Categoria">
          <select value={p.categoria} onChange={campo("categoria")}>
            <option value="">(sem categoria)</option>
            {categorias.map((c) => <option key={c} value={c}>{nome(c)}</option>)}
          </select>
        </Campo>
        <Campo rotulo="São o mesmo produto?">
          <select value={p.rotulo} onChange={campo("rotulo")}>
            <option value="mesmo">sim, é o mesmo produto</option>
            <option value="diferente">não, são produtos diferentes</option>
          </select>
        </Campo>
        <Campo rotulo="Por quê? (opcional)"><input value={p.motivo} onChange={campo("motivo")} placeholder="fragrâncias diferentes" /></Campo>
      </Formulario>
    </Modal>
  );
}

function ParesDaOsc({ organizacaoId, categorias }: { organizacaoId: string; categorias: string[] }) {
  const rota = `/api/organizacoes/${organizacaoId}/pares`;
  const { dados, erro, recarregar } = useDados<Pares>(rota);
  const [novo, setNovo] = useState(false);
  const [soErros, setSoErros] = useState(false);
  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!dados) return <Carregando />;
  const erros = dados.pares.filter((p) => p.erro).length;
  const lista = soErros ? dados.pares.filter((p) => p.erro) : dados.pares;
  return (
    <div>
      <p className="explicacao">
        Pares são exemplos de produtos que são o mesmo ou diferentes. Os da OSC nascem das suas decisões (confirmar ou
        recusar um produto), de páginas de lojas diferentes com o mesmo código de barras, ou são escritos aqui. Toda mudança
        no vocabulário é conferida com eles e com os {dados.resumo_sistema.total} pares que vêm com o programa.
      </p>
      <p className="pequeno"><strong>Pares do programa:</strong> {resumoDoTeste(dados.resumo_sistema)}</p>
      <p className="pequeno"><strong>Pares da OSC:</strong> {resumoDoTeste(dados.resumo_osc)}</p>
      {erros > 0 && (
        <Aviso tipo="atencao">
          Hoje o sistema erra {erros} par(es) da OSC (produtos diferentes em 🟢 ou o mesmo produto em 🔴). Ajuste o vocabulário
          para ensinar a diferença.
        </Aviso>
      )}
      <div className="linha-campos">
        <button className="secundario" onClick={() => setNovo(true)}>+ par de exemplo</button>
        <label className="marcador"><input type="checkbox" checked={soErros} onChange={(e) => setSoErros(e.target.checked)} /> só os que o sistema erra</label>
      </div>
      {lista.length === 0 && <p className="discreto">Nenhum par ainda. Eles aparecem conforme você confirma ou recusa produtos na pesquisa.</p>}
      {lista.length > 0 && (
        <table className="tabela">
          <thead><tr><th>Produto A</th><th>Produto B</th><th>Rótulo</th><th>Hoje o sistema diz</th><th /></tr></thead>
          <tbody>
            {lista.map((p) => (
              <tr key={p.id} className={p.erro ? "com-erro" : ""}>
                <td>{p.titulo_a}{p.marca_a ? <div className="discreto pequeno">{p.marca_a}</div> : null}</td>
                <td>{p.titulo_b}{p.marca_b ? <div className="discreto pequeno">{p.marca_b}</div> : null}</td>
                <td>
                  {p.rotulo === "mesmo" ? "mesmo produto" : "diferentes"}
                  <div className="discreto pequeno">{ORIGEM_DO_PAR[p.origem]}{p.motivo ? ` · ${p.motivo}` : ""}</div>
                </td>
                <td><Selo status={p.status_atual} texto={p.status_atual ?? "—"} />{p.erro && <div className="erro-curto pequeno">o sistema erra</div>}</td>
                <td>
                  <BotaoAcao classe="link pequeno" confirmar="Retirar este par dos exemplos? (ele continua no histórico)"
                    aoClicar={async () => { await api.criar(`/api/pares/${p.id}/retirar`); recarregar(); }}>retirar</BotaoAcao>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {novo && <NovoPar organizacaoId={organizacaoId} categorias={categorias} aoFechar={() => setNovo(false)} aoSalvar={recarregar} />}
    </div>
  );
}

// --- Página ---------------------------------------------------------------------------------------------------

type Aba = "vocabulario" | "categorias" | "lojas" | "pares";
const ABAS: [Aba, string][] = [["vocabulario", "Vocabulário"], ["categorias", "Categorias"], ["lojas", "Lojas"], ["pares", "Pares de exemplo"]];

function CatalogosDaOrganizacao({ organizacao }: { organizacao: Organizacao }) {
  const [aba, setAba] = useState<Aba>("vocabulario");
  const rota = `/api/organizacoes/${organizacao.id}/catalogos/atributos`;
  const { dados, erro, recarregar } = useDados<CatalogoDeAtributos>(rota);
  const [editado, setEditado] = useState<AtributosDados | null>(null);
  const [salvando, setSalvando] = useState(false);
  useEffect(() => { if (dados) setEditado(structuredClone(dados.vigente)); }, [dados]);
  const mudou = useMemo(() => dados && editado && JSON.stringify(editado) !== JSON.stringify(dados.vigente), [dados, editado]);
  const conhecidos = useMemo(() => {
    if (!dados || !editado) return [];
    return [...new Set([...dados.leitores, ...Object.keys(editado.vocabulario), ...dados.so_por_pessoa])].sort();
  }, [dados, editado]);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!dados || !editado) return <Carregando />;
  const mudar = (f: (d: AtributosDados) => void) => setEditado((atual) => {
    const copia = structuredClone(atual!);
    f(copia);
    return copia;
  });
  const deAtributos = aba === "vocabulario" || aba === "categorias";
  return (
    <section>
      <div className="cabecalho-pagina">
        <div>
          <h1>Catálogos da OSC</h1>
          <p className="discreto">{organizacao.nome} · valem para todos os projetos desta OSC · o catálogo do sistema continua por baixo</p>
        </div>
      </div>
      <nav className="abas">
        {ABAS.map(([id, rotulo]) => (
          <a key={id} href="#" className={aba === id ? "active" : ""} onClick={(e) => { e.preventDefault(); setAba(id); }}>{rotulo}</a>
        ))}
      </nav>
      {deAtributos && <Historico versoes={dados.historico} />}
      {aba === "vocabulario" && <Vocabulario editado={editado} mudar={mudar} />}
      {aba === "categorias" && <Categorias editado={editado} mudar={mudar} conhecidos={conhecidos} />}
      {aba === "lojas" && <Lojas organizacaoId={organizacao.id} />}
      {aba === "pares" && <ParesDaOsc organizacaoId={organizacao.id} categorias={Object.keys(editado.categorias)} />}
      {mudou && (
        <div className="barra-salvar visivel">
          <span>Há mudanças no vocabulário ou nas categorias que ainda não foram salvas.</span>
          <span className="espaco" />
          <button className="secundario" onClick={() => setEditado(structuredClone(dados.vigente))}>Descartar</button>
          <button onClick={() => setSalvando(true)}>Conferir e salvar</button>
        </div>
      )}
      {salvando && <SalvarAtributos organizacaoId={organizacao.id} editado={editado} aoFechar={() => setSalvando(false)}
        aoSalvar={() => { setSalvando(false); recarregar(); }} />}
    </section>
  );
}

export function PaginaCatalogos() {
  const { id } = useParams();
  const navegar = useNavigate();
  const { dados: organizacoes, erro } = useDados<Organizacao[]>("/api/organizacoes");
  useEffect(() => {
    if (!id && organizacoes?.length === 1) navegar(`/catalogos/${organizacoes[0].id}`, { replace: true });
  }, [id, organizacoes, navegar]);
  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!organizacoes) return <Carregando />;
  const organizacao = organizacoes.find((o) => o.id === id);
  if (organizacao) return <CatalogosDaOrganizacao key={organizacao.id} organizacao={organizacao} />;
  return (
    <section>
      <h1>Catálogos</h1>
      {organizacoes.length === 0
        ? <p className="discreto">Crie um projeto primeiro: os catálogos são de cada OSC.</p>
        : <ul>{organizacoes.map((o) => <li key={o.id}><Link to={`/catalogos/${o.id}`}>{o.nome}</Link></li>)}</ul>}
    </section>
  );
}
