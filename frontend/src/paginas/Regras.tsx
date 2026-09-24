import { useEffect, useState } from "react";
import { api } from "../api";
import { Aviso, BotaoAcao, Carregando } from "../componentes";
import { useDados } from "../ganchos";
import type { Arvore, RegrasDoProjeto } from "../tipos";
import type { PropsDaAba } from "./Projeto";

// As regras que mais mudam de um edital para outro. As demais aparecem na lista completa, só para consulta.

type Tipo = "numero" | "numero_ou_vazio" | "sim_nao" | "opcoes" | "texto";

interface Regra {
  caminho: string;
  rotulo: string;
  tipo: Tipo;
  ajuda?: string;
  opcoes?: [string, string][];
}

const SECOES: { titulo: string; regras: Regra[] }[] = [
  {
    titulo: "Pesquisa de preços",
    regras: [
      { caminho: "fontes.fontes_por_cotacao", rotulo: "Lojas por cotação", tipo: "numero", ajuda: "Quantas lojas com todos os itens do lote (D-10)." },
      { caminho: "fontes.validade_dias", rotulo: "Validade da pesquisa (dias)", tipo: "numero", ajuda: "Depois disso a pesquisa vence e precisa ser refeita (D-12)." },
      { caminho: "fontes.lojas_virtuais", rotulo: "Lojas virtuais", tipo: "opcoes", opcoes: [["permitidas", "permitidas"], ["proibidas", "proibidas"]] },
      { caminho: "fontes.marketplace.permitido", rotulo: "Aceitar marketplace", tipo: "sim_nao", ajuda: "Vale o CNPJ do vendedor, não o da plataforma (D-16)." },
      { caminho: "preco_referencia.desconto_pix", rotulo: "Preço à vista", tipo: "opcoes", ajuda: "D-60 (revista no piloto, 24/09/2026).",
        opcoes: [["usar", "no Pix; sem Pix, no boleto; nunca o parcelado"], ["ignorar", "o preço cheio da página"]] },
      { caminho: "preco_referencia.cep", rotulo: "CEP para o preço", tipo: "texto", ajuda: "“do_projeto” usa o CEP do projeto; ou escreva um CEP como 03977-015." },
      { caminho: "produto.exige_ean_igual", rotulo: "Só aceitar 🟢 com código de barras igual", tipo: "sim_nao" },
    ],
  },
  {
    titulo: "Cálculo",
    regras: [
      { caminho: "calculo.base_preco_final", rotulo: "Preço final", tipo: "opcoes", ajuda: "D-20. Cada orçamento pode ter a sua, logo abaixo.",
        opcoes: [["A", "A — média arredondada das lojas"], ["B", "B — preço da loja de menor total"]] },
      { caminho: "calculo.comparar_com", rotulo: "Comparar o preço com", tipo: "opcoes",
        opcoes: [["media_exata", "a média exata"], ["media_exibida", "a média arredondada (a que aparece)"]], ajuda: "P-02." },
    ],
  },
  {
    titulo: "Fechar o teto",
    regras: [
      { caminho: "otimizacao.margem_quantidade.min_percentual", rotulo: "Quantidades: pode diminuir até (%)", tipo: "numero", ajuda: "Número negativo, ex.: -20 (D-32)." },
      { caminho: "otimizacao.margem_quantidade.max_percentual", rotulo: "Quantidades: pode aumentar até (%)", tipo: "numero" },
      { caminho: "otimizacao.margem_horas.min_percentual", rotulo: "Horas: pode diminuir até (%)", tipo: "numero" },
      { caminho: "otimizacao.margem_horas.max_percentual", rotulo: "Horas: pode aumentar até (%)", tipo: "numero" },
    ],
  },
  {
    titulo: "Mão de obra",
    regras: [
      { caminho: "mao_de_obra.fontes_por_cotacao", rotulo: "Vagas por cotação", tipo: "numero", ajuda: "D-40." },
      { caminho: "mao_de_obra.mesmo_municipio", rotulo: "Só vagas do mesmo município", tipo: "sim_nao", ajuda: "D-47." },
      { caminho: "mao_de_obra.idade_maxima_vaga_dias", rotulo: "Idade máxima da vaga (dias)", tipo: "numero_ou_vazio", ajuda: "Em branco: sem limite." },
    ],
  },
  {
    titulo: "Comprovantes e desembolso",
    regras: [
      { caminho: "evidencia.comprovante_receita", rotulo: "Comprovante da Receita", tipo: "opcoes", opcoes: [["obrigatorio", "obrigatório"], ["opcional", "opcional"]], ajuda: "D-13." },
      { caminho: "evidencia.reaproveitar_comprovante_dias", rotulo: "Reaproveitar comprovante por (dias)", tipo: "numero", ajuda: "D-14." },
      { caminho: "desembolso.padrao", rotulo: "Desembolso", tipo: "opcoes", opcoes: [["parcela_unica_mes_1", "parcela única no mês 1"], ["conforme_cronograma", "conforme o cronograma"]], ajuda: "P-06." },
    ],
  },
];

function ler(arvore: Arvore, caminho: string): unknown {
  return caminho.split(".").reduce<unknown>((no, chave) => (no && typeof no === "object" ? (no as Arvore)[chave] : undefined), arvore);
}

function gravar(arvore: Arvore, caminho: string, valor: unknown): Arvore {
  const copia: Arvore = structuredClone(arvore);
  const partes = caminho.split(".");
  let no = copia;
  for (const p of partes.slice(0, -1)) {
    if (!no[p] || typeof no[p] !== "object") no[p] = {};
    no = no[p] as Arvore;
  }
  no[partes[partes.length - 1]] = valor;
  return copia;
}

function retirar(arvore: Arvore, caminho: string): Arvore {
  const copia: Arvore = structuredClone(arvore);
  const partes = caminho.split(".");
  const pilha: Arvore[] = [copia];
  for (const p of partes.slice(0, -1)) {
    const proximo = pilha[pilha.length - 1][p];
    if (!proximo || typeof proximo !== "object") return copia;
    pilha.push(proximo as Arvore);
  }
  delete pilha[pilha.length - 1][partes[partes.length - 1]];
  for (let n = partes.length - 2; n >= 0; n--) {  // tira os grupos que ficaram vazios
    if (Object.keys(pilha[n + 1]).length === 0) delete pilha[n][partes[n]];
  }
  return copia;
}

function folhas(arvore: Arvore, prefixo = ""): [string, unknown][] {
  return Object.entries(arvore).flatMap(([k, v]) =>
    v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).length > 0
      ? folhas(v as Arvore, `${prefixo}${k}.`)
      : [[`${prefixo}${k}`, v] as [string, unknown]]);
}

const mostrar = (v: unknown) => (v === null || v === undefined ? "—" : typeof v === "boolean" ? (v ? "sim" : "não") : Array.isArray(v) ? v.join(", ") : String(v));

function Controle({ regra, valor, aoMudar }: { regra: Regra; valor: unknown; aoMudar: (v: unknown) => void }) {
  if (regra.tipo === "sim_nao") {
    return (
      <select value={valor ? "sim" : "nao"} onChange={(e) => aoMudar(e.target.value === "sim")}>
        <option value="sim">sim</option>
        <option value="nao">não</option>
      </select>
    );
  }
  if (regra.tipo === "opcoes") {
    return (
      <select value={String(valor)} onChange={(e) => aoMudar(e.target.value)}>
        {regra.opcoes!.map(([v, r]) => <option key={v} value={v}>{r}</option>)}
      </select>
    );
  }
  if (regra.tipo === "texto") return <input value={String(valor ?? "")} onChange={(e) => aoMudar(e.target.value)} />;
  return (
    <input type="number" value={valor === null || valor === undefined ? "" : String(valor)}
      onChange={(e) => aoMudar(e.target.value === "" ? (regra.tipo === "numero_ou_vazio" ? null : 0) : Number(e.target.value))} />
  );
}

export function AbaRegras({ projeto, versao, atualizar }: PropsDaAba) {
  const { dados, erro, recarregar } = useDados<RegrasDoProjeto>(`/api/projetos/${projeto.id}/regras`, versao);
  const [proprias, setProprias] = useState<Arvore>({});
  useEffect(() => { if (dados) setProprias(dados.proprias); }, [dados]);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!dados) return <Carregando />;
  const mudou = JSON.stringify(proprias) !== JSON.stringify(dados.proprias);
  const origem = (caminho: string) => {
    if (ler(proprias, caminho) !== undefined) return ler(dados.proprias, caminho) !== undefined && JSON.stringify(ler(proprias, caminho)) === JSON.stringify(ler(dados.proprias, caminho)) ? "este projeto" : "este projeto (falta salvar)";
    const nome = dados.origem[caminho];
    return !nome || nome === "padrao-sistema" ? "padrão do sistema" : nome;
  };
  const salvar = async () => {
    await api.trocar(`/api/projetos/${projeto.id}/regras`, { conteudo: proprias });
    recarregar();
    atualizar();
  };
  const regraDoOrcamento = async (o: RegrasDoProjeto["orcamentos"][number], valor: string) => {
    const conteudo = valor ? gravar(o.proprias, "calculo.base_preco_final", valor) : retirar(o.proprias, "calculo.base_preco_final");
    await api.trocar(`/api/orcamentos/${o.id}/regras`, { conteudo });
    recarregar();
    atualizar();
  };

  return (
    <div className="regras">
      <p className="explicacao">
        As regras vêm em camadas: o padrão do sistema, depois o que este projeto muda e, por fim, o que cada orçamento muda.
        Mude aqui o que o edital pede. Cada gravação vira uma versão nova (as anteriores ficam no histórico), e regras que
        protegem os princípios do sistema não podem ser desligadas.
      </p>
      <p className="discreto pequeno">
        Camadas em uso: {dados.cadeia.map((c) => `${c.nivel === "sistema" ? "padrão do sistema" : c.nome} (versão ${c.versao})`).join(" → ")}
        {" · "}impressão digital {dados.impressao.slice(0, 12)}
      </p>

      {SECOES.map((secao) => (
        <div key={secao.titulo} className="bloco">
          <h2>{secao.titulo}</h2>
          <table className="tabela regras-tabela">
            <tbody>
              {secao.regras.map((r) => {
                const propria = ler(proprias, r.caminho);
                const valor = propria !== undefined ? propria : ler(dados.regras, r.caminho);
                return (
                  <tr key={r.caminho}>
                    <td>
                      <div>{r.rotulo}</div>
                      {r.ajuda && <div className="discreto pequeno">{r.ajuda}</div>}
                    </td>
                    <td><Controle regra={r} valor={valor} aoMudar={(v) => setProprias(gravar(proprias, r.caminho, v))} /></td>
                    <td className="pequeno">
                      <span className={propria !== undefined ? "" : "discreto"}>{origem(r.caminho)}</span>
                      {propria !== undefined && (
                        <div><button className="link pequeno" onClick={() => setProprias(retirar(proprias, r.caminho))}>voltar ao padrão</button></div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}

      <div className={`barra-salvar ${mudou ? "visivel" : ""}`}>
        {mudou ? <span>Há mudanças nas regras do projeto que ainda não foram salvas.</span> : <span className="discreto">Regras do projeto salvas.</span>}
        <span className="espaco" />
        {mudou && <button className="secundario" onClick={() => setProprias(dados.proprias)}>Descartar</button>}
        {mudou && <BotaoAcao aoClicar={salvar}>Salvar as regras</BotaoAcao>}
      </div>

      <div className="bloco">
        <h2>Regra de cada orçamento</h2>
        <p className="discreto">Ex.: o edital pede a regra A para materiais e a regra B para serviços (T-13).</p>
        <table className="tabela">
          <tbody>
            {dados.orcamentos.map((o) => {
              const propria = ler(o.proprias, "calculo.base_preco_final") as string | undefined;
              return (
                <tr key={o.id}>
                  <td>{o.nome}</td>
                  <td>
                    <select value={propria ?? ""} onChange={(e) => void regraDoOrcamento(o, e.target.value).catch((err: Error) => window.alert(err.message))}>
                      <option value="">igual ao projeto (regra {String(ler(dados.regras, "calculo.base_preco_final"))})</option>
                      <option value="A">A — média arredondada</option>
                      <option value="B">B — loja de menor total</option>
                    </select>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {dados.orcamentos.length === 0 && <p className="discreto">Nenhum orçamento cadastrado.</p>}
      </div>

      <details className="bloco">
        <summary>Todas as regras em uso ({folhas(dados.regras).length})</summary>
        <table className="tabela pequeno">
          <tbody>
            {folhas(dados.regras).map(([caminho, v]) => (
              <tr key={caminho}>
                <td><code>{caminho}</code></td>
                <td>{mostrar(v)}</td>
                <td className="discreto">{origem(caminho)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
