export type HeadlineMetrics = {
  internal_declarations: number;
  external_targets: number;
  source_pairs: number;
  source_occurrences: number;
  repeated_pairs: number;
  self_loop_pairs: number;
  unparented_usages: number;
  unresolved_parent_usages: number;
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
  path_indegree: {
    metric: string;
    semantics: string;
    storage: string;
    cycle_boundary_node_count: number;
    maximum_exact: string;
    maximum_log10: number | null;
  };
  graph_schema_version: string;
  domain_algorithm: Record<string, string>;
  sampling_policy: Record<string, string>;
  claims: Claim[];
  domains: DomainMetric[];
  domain_matrix: DomainMatrixRow[];
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
  in_degree_source: number;
  in_occurrences_source: number;
  in_paths_source: string;
  in_paths_source_log10: number | null;
  is_path_cycle_boundary: boolean;
  out_degree_source: number;
  out_occurrences_source: number;
  sample_reason: string;
};

export type ExternalTargetSample = {
  dst_id: number;
  name: string;
  unique_consumer_count: number;
  source_pair_count: number;
  source_occurrence_count: number;
  target_module_hints: string[];
  target_module_hint_count: number;
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
  edge_type: "SOURCE";
  multiplicity: number;
  cell_rank: number;
  is_cross_domain: boolean;
  sample_reason: string;
};

export type SourceEdgeSample = {
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
  edge_type: "SOURCE";
  multiplicity: number;
  group_rank: number;
  is_external_target: boolean;
  is_self_loop: boolean;
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
  edge_type: "SOURCE";
  multiplicity: number;
  is_self_loop: boolean;
};

export type ExprBreakdownNode = {
  index: number;
  depth: number;
  constructor: string;
  meaning: string;
};

export type ExprBreakdownLayer = {
  surface: string;
  raw: string;
  nodes: ExprBreakdownNode[];
};

export type ExprEvidence = {
  kind: string;
  title: string;
  url: string;
  supports: string;
  detail: string;
  code: string | null;
};

export type ExprBreakdown = {
  verification: string;
  type_expr: ExprBreakdownLayer;
  value_expr: ExprBreakdownLayer;
  notation: string;
  evidence: ExprEvidence[];
  inference: string;
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
  source_locations?: { line: number; start_character: number; end_character: number }[];
  published_location_count?: number;
  aggregate?: {
    target_source_occurrences: number;
    target_unique_consumers: number;
    source_modules: number;
    excluded_private_context_locations: number;
  } | null;
  expr_breakdown?: ExprBreakdown;
  interpretation?: string;
};

export type ConstructionCases = {
  schema_version: string;
  snapshot_id: string;
  edge_direction: string;
  occurrence_unit: string;
  edge_extraction: {
    mechanism: string;
    steps: {
      step: string;
      code: string;
      detail: string;
      evidence: string;
      url: string;
    }[];
    module_hint: string;
  };
  attribution_boundary: {
    primary_graph_rule: string;
    target_endpoint: string;
    source_endpoint: string;
    unparented: {
      total: number;
      outside_declaration_range: number;
      unique_declaration_range: number;
      unique_environment_declaration: number;
      overlapping_declaration_ranges: number;
    };
    outside_declaration_profile: {
      population: number;
      variable_context_count: number;
      variable_context_share: number;
      classification_note: string;
      categories: {
        explicit_variable: number;
        probable_variable_continuation: number;
        option_or_attribute_header: number;
        attribute_command: number;
        alias_command: number;
        namespace_syntax_or_scope_command: number;
        other_command_or_continuation: number;
      };
    };
    parent_not_in_environment: {
      total: number;
      example_context: number;
      private_or_eval_context: number;
      metaprogram_or_external_context: number;
    };
    context_policy: string;
    examples: {
      kind: string;
      title: string;
      code: string;
      explanation: string;
      url: string;
    }[];
  };
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

export type PathRankPoint = {
  rank: number;
  log10_rank: number;
  empirical_log10: number;
  zipf_log10: number;
  reciprocal_prime_log10: number;
  free_rank_fit_log10: number;
};

export type PathRankModel = {
  formula: string;
  fixed_intercept_log10: number;
  fixed_rmse_log10: number;
  fixed_mae_log10: number;
  fixed_r_squared_log10: number;
  free_exponent_beta: number;
  free_intercept_log10: number;
  free_rmse_log10: number;
  free_r_squared_log10: number;
};

export type PathRankRange = {
  range_id: "all_positive" | "top_1pct";
  observation_count: number;
  maximum_log10: number;
  minimum_log10: number;
  models: {
    zipf: PathRankModel;
    reciprocal_prime: PathRankModel;
  };
  display_point_count: number;
  points: PathRankPoint[];
};

export type PathRankComparison = {
  schema_version: string;
  snapshot_id: string;
  metric: string;
  metric_definition: string;
  positive_observation_count: number;
  comparison_space: string;
  amplitude_policy: string;
  prime_transform: string;
  references: {
    zipf_reuse: string;
    nth_prime_asymptotic: string;
  };
  ranges: PathRankRange[];
};

export type ExplorerKind = "nodes" | "external" | "source" | "edges" | null;
