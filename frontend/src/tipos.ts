// Formatos devolvidos pela API (backend/orca/api/apresentacao.py). Dinheiro em centavos.

export type Status = "verde" | "amarelo" | "vermelho";

export interface Situacao {
  sistema: string;
  versao: string;
  usuario: string;
  pasta_dados: string;
  hoje: string;
}

export interface Organizacao {
  id: string;
  nome: string;
  cnpj: string | null;
}

export interface Item {
  id: string;
  lote_id: string;
  descricao: string;
  categoria: string | null;
  marca: string | null;
  modelo: string | null;
  apresentacao: string | null;
  atributos: Record<string, unknown>;
  ean: string | null;
  unidade: string;
  qtd_planejada: number;
  mes_inicio: number;
  mes_fim: number;
  margem_min_percentual: number | null;
  margem_max_percentual: number | null;
  travado: boolean;
  substitui_item_id: string | null;
}

export interface Cargo {
  id: string;
  orcamento_id: string;
  nome: string;
  cbo: string | null;
  postos: number;
  regime: "mei" | "recibo" | "clt";
  jornada_id: string;
  horas_planejadas_centesimos: number;
  mes_inicio: number;
  mes_fim: number;
  margem_min_percentual: number | null;
  margem_max_percentual: number | null;
  travado: boolean;
}

export interface Lote {
  id: string;
  orcamento_id: string;
  nome: string;
  itens: Item[];
}

export interface Orcamento {
  id: string;
  projeto_id: string;
  nome: string;
  descricao: string | null;
  tipo: "materiais" | "mao_de_obra" | "servicos";
  arquivado: boolean;
  lotes: Lote[];
  cargos: Cargo[];
}

export interface Projeto {
  id: string;
  nome: string;
  organizacao: Organizacao;
  orgao: string | null;
  instrumento: string | null;
  processo: string | null;
  teto_centavos: number;
  duracao_meses: number;
  cep: string | null;
  data_entrega: string | null;
  arquivado: boolean;
  criado_em: string;
  orcamentos?: Orcamento[];
}

export interface EstadoOpcionais {
  serpapi: { chave: boolean };
  ia: {
    provedor: "nenhum" | "gemini" | "local";
    modelo: string;
    endereco: string;
    chave_gemini: boolean;
    ligada: boolean;
    modelo_padrao: string;
    endereco_padrao: string;
  };
  erro_cofre: string | null;
}

export interface Correspondencia {
  id: string;
  status: Status;
  origem: "ean" | "atributos" | "ia" | "humano";
  motivos: string[];
  autor: string;
  vale: boolean;
  precisa_confirmar: boolean;
}

export interface Oferta {
  preco_centavos: number;
  observacao_id: string;
  utilizavel: boolean;
  evidencia_valida: boolean;
  evidencia_id: string | null;
  url: string | null;
  titulo: string | null;
  correspondencia: Correspondencia | null;
  imagem: string | null;  // D-73
  ean: string | null;
}

/** Produto de referência do item (D-71): a página que uma pessoa confirmou. */
export interface Referencia {
  observacao_id: string;
  titulo: string | null;
  loja: string;
  url: string;
  imagem: string | null;
  ean: string | null;
}

export interface LojaDoLote {
  id: string;
  nome: string;
  cnpj: string | null;
  cnpj_ativo: boolean;
  cnpj_consultado: boolean;
  posicao: number | null;
  total_centavos: number | null;
  situacao: "trio" | "elegivel" | "descartada" | "retirada" | "completa" | "incompleta";
  motivo: string | null;
}

export interface ItemRevisao extends Item {
  meses: number;
  status: Status | null;
  motivos: string[];
  ofertas: Record<string, Oferta>;
  media_centavos: number | null;
  media_exata: string | null;
  preco_final_centavos: number | null;
  dentro_da_media: boolean | null;
  referencia: Referencia | null;
}

export interface LoteRevisao {
  id: string;
  nome: string;
  situacao: "ok" | "sem_trio" | "sem_pesquisa";
  mensagem: string | null;
  sugestoes: string[];
  lojas: LojaDoLote[];
  itens: ItemRevisao[];
}

export interface Vaga {
  id: string;
  empresa: string | null;
  cnpj: string | null;
  salario_min_centavos: number | null;
  salario_max_centavos: number | null;
  referencia_centavos: number | null;
  plataforma: string | null;
  grupo: string | null;
  escolhida: boolean;
  motivo_descarte: string | null;
  evidencia_id: string | null;
  url: string;
  titulo: string | null;
}

export interface CargoRevisao extends Cargo {
  status: Status | null;
  motivos: string[];
  jornada: { id: string; descricao: string; semanal_horas: number } | null;
  vagas: Vaga[];
  incertos: { a: string; b: string; motivo: string }[];
  calculo: {
    salarios_centavos: number[];
    media_centavos: number;
    divisor: number;
    valor_hora_centavos: number;
    horas_mes_centesimos: number;
    valor_mensal_centavos: number;
    meses: number;
    postos: number;
    total_centavos: number;
    memoria: string[];
  } | null;
  problema: string | null;
}

export interface OrcamentoRevisao {
  id: string;
  nome: string;
  tipo: Orcamento["tipo"];
  base_preco_final: "A" | "B";
  fontes_por_cotacao: number;
  lotes: LoteRevisao[];
  cargos: CargoRevisao[];
}

export interface Revisao {
  projeto_id: string;
  hoje: string;
  orcamentos: OrcamentoRevisao[];
}

export interface LinhaPainel {
  id: string;
  nome: string;
  tipo: "item" | "cargo";
  status: Status;
  motivos: string[];
}

export interface Painel {
  teto_centavos: number;
  total_centavos: number | null;
  diferenca_centavos: number | null;
  planejado_centavos: number;
  contagem: Record<Status, number>;
  cnpjs: number;
  cnpjs_ativos: number;
  cnpjs_sem_consulta: string[];
  aguardando_aprovacao: number;
  pendencias_teto: string[];
  alertas: string[];
  linhas: LinhaPainel[];
}

export interface Tarefa {
  id: string;
  projeto_id: string | null;
  tipo: "coletar_item" | "coletar_cargo" | "captura_assistida" | "comprovante" | "consultar_cnpj" | "fechar_teto" | "exportar" | "buscar_lote" | "buscar_alternativas"
    | "descobrir_na_web" | "julgar_amarelos" | "fechar_lote" | "descobrir_vagas" | "classificar_loja";
  estado: "pendente" | "rodando" | "esperando_usuario" | "concluida" | "falhou" | "cancelada";
  progresso: number;
  mensagem: string | null;
  parametros: Record<string, unknown>;
  resultado: Record<string, unknown> | null;
  autor: string;
  criado_em: string;
  iniciada_em: string | null;
  concluida_em: string | null;
}

export interface Execucao {
  id: string;
  status: "otima" | "viavel" | "sem_solucao";
  total_centavos: number | null;
  teto_centavos: number;
  verificacao_ok: boolean;
  versao: string;
  criado_em: string;
  vigente: boolean;
  resultado: {
    alteracoes?: { linha: string; nome: string; de: number; para: number; unidade: string }[];
    verificacao?: string[];
    mensagem?: string;
    motivo?: string;
    sugestoes?: { tipo: string; alvo: string; mensagem: string }[];
  };
}

export interface Conferencia {
  regra: string;
  situacao: "ok" | "atencao" | "problema";
  detalhes: string[];
}

export interface Exportacao {
  arquivo: string;
  bytes: number;
  total_centavos: number;
  gerado_em: string;
}

export interface Evento {
  id: number;
  criado_em: string;
  autor: string;
  entidade: string;
  entidade_id: string;
  acao: string;
  antes: Record<string, unknown> | null;
  depois: Record<string, unknown> | null;
}

export interface Observacao {
  id: string;
  url: string;
  loja: string;
  cnpj_vendedor: string | null;
  titulo: string | null;
  marca: string | null;
  ean: string | null;
  preco_centavos: number | null;
  salario_min_centavos: number | null;
  salario_max_centavos: number | null;
  encontrado: boolean;
  coletado_em: string;
  metodo: string;
  preco_no_html: boolean | null;
  evidencia_id: string | null;
  avisos: string[];
  correspondencia: Correspondencia | null;
  precos_da_pagina: { centavos: number; forma: FormaDePagamento | null }[];
  forma_de_pagamento: FormaDePagamento | null;
  imagem: string | null;
}

export type FormaDePagamento = "pix" | "boleto" | "pix_ou_boleto" | "parcelado";

export interface Jornada {
  id: string;
  descricao: string;
  semanal_horas: number;
  divisor: number;
  fonte_legal: string;
}

export interface Categoria {
  id: string;
  atributos: string[];
}

// --- Catálogos da OSC (D-64 a D-66) ---------------------------------------------------------------

/** atributo → grupo → valor → sinônimos */
export type VocabularioDados = Record<string, Record<string, Record<string, string[]>>>;

export interface AtributosDados {
  versao?: number;
  sempre?: string[];
  categorias: Record<string, string[]>;
  vocabulario: VocabularioDados;
}

export interface VersaoDoCatalogo {
  versao: number;
  criado_em: string;
  autor: string;
  resumo: string | null;
}

export interface CatalogoDeAtributos {
  versao: number;
  mudancas: Record<string, unknown>;
  vigente: AtributosDados;
  sistema: AtributosDados;
  leitores: string[];
  so_por_pessoa: string[];
  historico: VersaoDoCatalogo[];
}

export interface ResumoDoTeste {
  total: number;
  contagem: Record<string, number>;
  falsos_verdes: number;
  iguais_recusados: number;
}

export interface ResultadoDoTeste {
  aprovada: boolean;
  antes: ResumoDoTeste;
  depois: ResumoDoTeste;
  novos_falsos_verdes: { titulo_a: string; titulo_b: string }[];
  pares_que_mudaram: { titulo_a: string; titulo_b: string; rotulo: string; origem: string; antes: Status; depois: Status }[];
}

export interface LojaDados {
  id: string;
  nome: string;
  dominio: string;
  coleta: string;
  marketplace?: boolean;
  cep?: string | null;
  preco_a_usar?: string | null;
  observacoes?: string | null;
  [outro: string]: unknown;
}

export interface CatalogoDeLojas {
  versao: number;
  mudancas: Record<string, unknown>;
  tipos: Record<string, string>;  // D-74: tipo de loja → nome
  aprendidas: Record<string, string[]>;  // domínio → tipos aprendidos nas pesquisas
  classificando: string[];
  vigente: { lojas: LojaDados[]; fornecedores_servico: LojaDados[]; [outro: string]: unknown };
  coletas: string[];
  historico: VersaoDoCatalogo[];
}

export interface Par {
  id: string;
  titulo_a: string;
  marca_a: string | null;
  titulo_b: string;
  marca_b: string | null;
  categoria: string | null;
  rotulo: "mesmo" | "diferente";
  origem: "decisao" | "ean" | "usuario";
  motivo: string | null;
  status_atual: Status | null;
  erro: boolean;
}

export interface Pares {
  pares: Par[];
  resumo_osc: ResumoDoTeste;
  resumo_sistema: ResumoDoTeste;
}

// --- Regras -----------------------------------------------------------------------------------------

export type Arvore = { [chave: string]: unknown };

export interface RegrasDoProjeto {
  impressao: string;
  camadas: string[];
  cadeia: { nome: string; nivel: string; versao: number }[];
  regras: Arvore;
  origem: Record<string, string>;
  proprias: Arvore;
  orcamentos: { id: string; nome: string; proprias: Arvore; impressao: string }[];
}
