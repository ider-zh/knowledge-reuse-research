export type HeadlineMetrics = {
  internal_declarations: number;
  external_targets: number;
  typed_edges: number;
  unique_dependency_pairs: number;
  constant_occurrences: number;
};

export type DomainMetric = {
  domain: string;
  node_count: number;
  reused_target_count: number;
  edge_count: number;
  gini: number;
  top_1pct_share: number;
  top_5pct_share: number;
  top_10pct_share: number;
  internal_dependency_share: number;
  outbound_domain_diversity: number;
  reference_entropy_proxy: number;
  effective_target_domains: number;
  rank_exponent_beta: number | null;
};

export type DomainMatrixRow = {
  src_domain: string;
  dst_domain: string;
  dependency_pair_count: number;
  row_share: number;
};

export type Claim = {
  claim_id: string;
  status: "fact" | "supported" | "exploratory" | "inconclusive";
  text: string;
  scope: string;
  caveat: string;
  evidence: string[];
};

export type Overview = {
  schema_version: string;
  snapshot_id: string;
  run_kind: string;
  headline_metrics: HeadlineMetrics;
  domain_algorithm: Record<string, string>;
  sampling_policy: Record<string, string>;
  claims: Claim[];
  domains: DomainMetric[];
  domain_matrix: DomainMatrixRow[];
  kind_metrics: Record<string, string | number | null>[];
};

export type NodeSample = {
  node_id: number;
  name: string;
  module: string;
  domain: string;
  kind: string;
  has_value: boolean;
  source_tokens: number | null;
  type_expr_unique_ptr_nodes: number;
  value_expr_unique_ptr_nodes: number | null;
  value_expr_tree_occurrences: number | null;
  in_degree_all: number;
  in_degree_type: number;
  in_degree_value: number;
  out_degree_all: number;
  sample_reason: string;
};

export type ExternalTargetSample = {
  dst_id: number;
  name: string;
  unique_consumer_count: number;
  typed_edge_count: number;
  type_edge_count: number;
  value_edge_count: number;
  sample_reason: string;
};

export type DomainEdgeSample = {
  src_id: number;
  dst_id: number;
  src_name: string;
  dst_name: string;
  src_module: string;
  dst_module: string;
  src_domain: string;
  dst_domain: string;
  src_kind: string;
  dst_kind: string;
  edge_types: string;
  cell_rank: number;
  is_cross_domain: boolean;
  sample_reason: string;
};

export type TypedEdgeSample = {
  src_id: number;
  dst_id: number;
  src_name: string;
  dst_name: string;
  src_module: string;
  dst_module: string | null;
  src_domain: string;
  dst_domain: string;
  src_kind: string;
  dst_kind: string;
  edge_type: "TYPE" | "VALUE";
  multiplicity: number;
  group_rank: number;
  is_external_target: boolean;
  sample_reason: string;
};

export type SamplePayload<T> = {
  schema_version: string;
  population_count: number;
  internal_population_count?: number;
  published_count: number;
  rows: T[];
};

export type ConstructionNode = {
  node_id: number;
  name: string;
  kind: string;
  module: string;
  has_value: boolean;
  type_expr_nodes: number;
  value_expr_nodes: number | null;
};

export type ConstructionEdge = {
  src_id: number;
  src_name: string;
  src_kind: string;
  dst_id: number;
  dst_name: string;
  dst_kind: string;
  edge_type: "TYPE" | "VALUE";
  multiplicity: number;
  is_self_loop: boolean;
};

export type ConstructionCase = {
  case_id: string;
  title: string;
  summary: string;
  source_file: string;
  start_line: number;
  end_line: number;
  source_url: string;
  code: string;
  nodes?: ConstructionNode[];
  edges?: ConstructionEdge[];
  interpretation?: string;
};

export type ConstructionCases = {
  schema_version: string;
  snapshot_id: string;
  edge_direction: string;
  occurrence_unit: string;
  stages: { stage: string; description: string }[];
  node_cases: ConstructionCase[];
  edge_cases: ConstructionCase[];
};

export type RankFrequencyPoint = {
  rank: number;
  empirical_degree: number;
  fitted_degree: number | null;
  zipf_degree: number | null;
};

export type RankFrequencySeries = {
  population: string;
  label: string;
  positive_n: number;
  tail_n: number;
  xmin: number;
  beta_rank: number;
  r_squared: number;
  display_sampling: string;
  points: RankFrequencyPoint[];
};

export type RankFrequencyDistribution = {
  schema_version: string;
  snapshot_id: string;
  reuse_unit: string;
  rank_definition: string;
  reference_definition: string;
  series: RankFrequencySeries[];
};

export type ExplorerKind = "nodes" | "external" | "typed" | "edges" | null;
