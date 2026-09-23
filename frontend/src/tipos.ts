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
}

export interface LojaDoLote {
  id: string;
  nome: string;
  cnpj: string | null;
  cnpj_ativo: boolean;
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
  tipo: "coletar_item" | "coletar_cargo" | "consultar_cnpj" | "fechar_teto" | "exportar";
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
}

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
