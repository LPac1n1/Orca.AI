import { useState } from "react";
import { api } from "../api";
import { Aviso, BotaoAcao, Campo, Carregando, Formulario } from "../componentes";
import { useDados } from "../ganchos";
import type { EstadoOpcionais } from "../tipos";

// Opcionais (Fase 2, etapa 15; D-50 a D-52): o Orça.AI funciona sem nada disto.

function Buscador({ estado, aoMudar }: { estado: EstadoOpcionais; aoMudar: (e: EstadoOpcionais) => void }) {
  const [chave, setChave] = useState("");
  return (
    <section className="bloco">
      <h2>Buscador pela internet (SerpApi) <span className="discreto">· {estado.serpapi.chave ? "ligado" : "desligado"}</span></h2>
      <p className="explicacao">
        Procura o produto na busca do Google para achar lojas fora do catálogo. Só aponta links: <strong>você escolhe</strong> quais
        páginas o sistema lê, e cada uma é conferida como se você tivesse colado o link (prova, preço, CNPJ, mesmo produto).
        Para usar, crie uma conta grátis em serpapi.com e copie a chave (“API key”) do painel. O plano grátis tem poucas buscas
        por mês; cada item pesquisado gasta uma.
      </p>
      <Formulario rotulo={estado.serpapi.chave ? "Trocar a chave" : "Guardar a chave"} aoEnviar={async () => {
        if (!chave.trim()) throw new Error("Cole a chave.");
        aoMudar(await api.trocar<EstadoOpcionais>("/api/opcionais", { chave_serpapi: chave.trim() }));
        setChave("");
      }}>
        <Campo rotulo="Chave da SerpApi" ajuda="Fica no Gerenciador de Credenciais do Windows, neste computador.">
          <input type="password" autoComplete="off" value={chave} onChange={(e) => setChave(e.target.value)}
            placeholder={estado.serpapi.chave ? "chave guardada (cole outra para trocar)" : ""} />
        </Campo>
      </Formulario>
      {estado.serpapi.chave && (
        <BotaoAcao classe="secundario pequeno" confirmar="Remover a chave da SerpApi deste computador?"
          aoClicar={async () => aoMudar(await api.trocar<EstadoOpcionais>("/api/opcionais", { chave_serpapi: "" }))}>
          Remover a chave
        </BotaoAcao>
      )}
    </section>
  );
}

const PROVEDORES: [EstadoOpcionais["ia"]["provedor"], string][] = [
  ["nenhum", "Desligada (padrão)"], ["gemini", "Gemini (plano grátis)"], ["local", "Modelo no próprio computador (Ollama)"],
];

function Ia({ estado, aoMudar }: { estado: EstadoOpcionais; aoMudar: (e: EstadoOpcionais) => void }) {
  const [provedor, setProvedor] = useState(estado.ia.provedor);
  const [modelo, setModelo] = useState(estado.ia.modelo);
  const [endereco, setEndereco] = useState(estado.ia.endereco);
  const [chave, setChave] = useState("");
  const [teste, setTeste] = useState<string | null>(null);
  return (
    <section className="bloco">
      <h2>IA <span className="discreto">· {PROVEDORES.find(([id]) => id === estado.ia.provedor)?.[1]}</span></h2>
      <p className="explicacao">
        Hoje a IA faz uma coisa: confere os produtos 🟡 (quando o sistema não tem certeza se a página é o mesmo produto). Ela
        <strong> só pode rebaixar para 🔴</strong>, com o motivo; nunca aprova um 🟢 e nunca dá um preço (D-52). Recebe só o nome, a
        marca e a descrição dos produtos e dos anúncios; nada sobre a OSC ou pessoas (D-51). Você pode desfazer qualquer 🔴 dela.
      </p>
      <Formulario rotulo="Salvar" aoEnviar={async () => {
        if (provedor === "gemini" && !estado.ia.chave_gemini && !chave.trim()) throw new Error("Cole a chave do Gemini.");
        if (provedor === "local" && !modelo.trim()) throw new Error("Informe o nome do modelo local.");
        const corpo: Record<string, string> = { ia_provedor: provedor, ia_modelo: modelo.trim(), ia_endereco: endereco.trim() };
        if (chave.trim()) corpo.chave_gemini = chave.trim();
        aoMudar(await api.trocar<EstadoOpcionais>("/api/opcionais", corpo));
        setChave("");
        setTeste(null);
      }}>
        <div className="modos" role="radiogroup" aria-label="Provedor de IA">
          {PROVEDORES.map(([id, rotulo]) => (
            <label key={id} className={provedor === id ? "ativo" : ""}>
              <input type="radio" name="provedor" checked={provedor === id} onChange={() => { setProvedor(id); setModelo(""); }} />
              {rotulo}
            </label>
          ))}
        </div>
        {provedor === "gemini" && (
          <>
            <p className="discreto pequeno">
              Pegue uma chave grátis no Google AI Studio (aistudio.google.com, “Get API key”). No plano grátis, o Google pode usar o
              que recebe para melhorar os serviços dele; por isso só vão dados públicos de produtos.
            </p>
            <Campo rotulo="Chave do Gemini" ajuda="Fica no Gerenciador de Credenciais do Windows, neste computador.">
              <input type="password" autoComplete="off" value={chave} onChange={(e) => setChave(e.target.value)}
                placeholder={estado.ia.chave_gemini ? "chave guardada (cole outra para trocar)" : ""} />
            </Campo>
            <Campo rotulo="Modelo" ajuda="Em branco: o padrão. Troque se o Google mudar o nome dos modelos grátis.">
              <input value={modelo} onChange={(e) => setModelo(e.target.value)} placeholder={estado.ia.modelo_padrao} />
            </Campo>
          </>
        )}
        {provedor === "local" && (
          <>
            <p className="discreto pequeno">
              Instale o Ollama (ollama.com), baixe um modelo (por exemplo, no terminal: <code>ollama pull qwen2.5:7b</code>) e informe o
              nome aqui. Nada sai do computador, mas ele precisa ter memória suficiente para o modelo.
            </p>
            <div className="linha-campos">
              <Campo rotulo="Modelo"><input value={modelo} onChange={(e) => setModelo(e.target.value)} placeholder="qwen2.5:7b" /></Campo>
              <Campo rotulo="Endereço" ajuda="Em branco: o padrão do Ollama.">
                <input value={endereco} onChange={(e) => setEndereco(e.target.value)} placeholder={estado.ia.endereco_padrao} />
              </Campo>
            </div>
          </>
        )}
      </Formulario>
      {estado.ia.ligada && (
        <div className="acoes">
          <BotaoAcao classe="secundario" aoClicar={async () => setTeste((await api.criar<{ mensagem: string }>("/api/opcionais/testar-ia")).mensagem)}>
            Testar a IA
          </BotaoAcao>
          {estado.ia.chave_gemini && (
            <BotaoAcao classe="secundario" confirmar="Remover a chave do Gemini deste computador? A IA fica desligada."
              aoClicar={async () => aoMudar(await api.trocar<EstadoOpcionais>("/api/opcionais", { chave_gemini: "", ia_provedor: "nenhum" }))}>
              Remover a chave
            </BotaoAcao>
          )}
        </div>
      )}
      {teste && <Aviso tipo="ok">{teste}</Aviso>}
    </section>
  );
}

export function PaginaOpcionais() {
  const { dados, erro } = useDados<EstadoOpcionais>("/api/opcionais");
  const [estado, setEstado] = useState<EstadoOpcionais | null>(null);
  const atual = estado ?? dados;
  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!atual) return <Carregando />;
  return (
    <div>
      <h1>Opcionais</h1>
      <p className="explicacao">
        O Orça.AI funciona sem nada disto. São ajudas gratuitas que você liga se quiser. As chaves ficam guardadas no
        Gerenciador de Credenciais do Windows, neste computador: nunca na pasta de dados, no banco ou nos documentos.
      </p>
      {atual.erro_cofre && <Aviso tipo="erro">{atual.erro_cofre}</Aviso>}
      <Buscador estado={atual} aoMudar={setEstado} />
      <Ia key={atual.ia.provedor} estado={atual} aoMudar={setEstado} />
    </div>
  );
}
