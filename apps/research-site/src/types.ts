export type HeadlineMetrics = {
  internal_declarations: number;
  external_targets: number;
  source_pairs: number;
  source_occurrences: number;
  repeated_pairs: number;
  self_loop_pairs: number;
  unparented_usages: number;
  unresolved_parent_usages: number;
  parent_module_mismatch_usages: number;
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
    parent_module_mismatch: {
      total: number;
      unique_parent_declarations: number;
      policy: string;
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

export type OpenJdkTopMethod = {
  rank: number;
  node_id: string;
  label: string;
  module: string;
  direct_unique_callers: number;
  direct_call_occurrences: number;
  indirect_incoming_paths: string;
  all_incoming_paths: string;
  all_incoming_paths_log10: number;
  is_cycle_boundary: boolean;
};

export type OpenJdkMetricSample = {
  node_id: string;
  label: string;
  module: string;
  direct_unique_callers: number;
  direct_call_occurrences: number;
  indirect_incoming_paths: string;
  all_incoming_paths: string;
  is_cycle_boundary: boolean;
};

export type OpenJdkCallOccurrenceSample = {
  caller: string;
  callee: string;
  invoke_kind: string;
  instruction_ordinal: number;
  source_line: number;
  declared_target: string;
  resolution: string;
};

export type OpenJdkMethodNodeSample = OpenJdkMetricSample & {
  method_key: string;
  source_file: string;
  first_line: number | null;
  last_line: number | null;
  flags: string[];
};

export type OpenJdkReuseReport = {
  schema_version: string;
  snapshot_id: string;
  graph_id: string;
  corpus: {
    jdk_release: string;
    source_tag: string;
    source_commit: string;
    node_unit: string;
    edge_unit: string;
  };
  semantics: Record<string, string>;
  population: {
    nodes: number;
    links: number;
    call_occurrences: number;
    positive_path_nodes: number;
    zero_path_nodes: number;
    cycle_boundary_nodes: number;
  };
  path_counts: {
    maximum: string;
    maximum_log10: number;
    median_positive_log10: number;
  };
  paper_reuse: {
    paper: {
      title: string;
      section: string;
      url: string;
    };
    method_alignment: {
      paper_component: string;
      openjdk_component: string;
      paper_use: string;
      openjdk_use: string;
      ranking: string;
      plot: string;
      rank_offset: string;
    };
    population: {
      all_methods: number;
      referenced_methods: number;
      unreferenced_methods: number;
      references: number;
      singleton_methods: number;
      maximum_references: number;
    };
    rank_shape: Omit<PathRankComparison, "schema_version" | "snapshot_id" | "metric_definition" | "references">;
  };
  rank_shape: Omit<PathRankComparison, "schema_version" | "snapshot_id" | "metric_definition" | "amplitude_policy" | "prime_transform" | "references">;
  top_nodes: OpenJdkTopMethod[];
  samples: {
    method_nodes: OpenJdkMethodNodeSample[];
    call_pairs: Array<{
      caller: string;
      callee: string;
      multiplicity: number;
      relation: string;
    }>;
    call_occurrences: OpenJdkCallOccurrenceSample[];
    positive_path_nodes: OpenJdkMetricSample[];
    zero_path_nodes: OpenJdkMetricSample[];
    cycle_boundary_nodes: OpenJdkMetricSample[];
  };
  extraction_examples: {
    node: {
      source_path: string;
      source_lines: [number, number];
      source_excerpt: string;
      classfile_fields: {
        module: string;
        internal_class: string;
        name: string;
        descriptor: string;
        access_flags: number;
      };
      output: OpenJdkMethodNodeSample;
    };
    edge: {
      source_path: string;
      source_lines: [number, number];
      source_excerpt: string;
      bytecode_reference: {
        invoke_kind: string;
        instruction_ordinal: number;
        source_line: number;
        declared_owner: string;
        declared_name: string;
        declared_descriptor: string;
        resolution: string;
      };
      output: {
        caller_method_key: string;
        callee_method_key: string;
        invoke_kind: string;
        multiplicity: number;
      };
    };
  };
  interpretation: {
    primary: string;
    prime: string;
    scope: string;
  };
  references: {
    paper: string;
    zipf: string;
    nth_prime: string;
  };
};

export type ReuseTheoremReport = {
  schema_version: string;
  snapshot_id: string;
  phase_1: { status: "superseded"; reason: string };
  phase_2: {
    status: string;
    methods: number;
    classes: number;
    methods_with_code: number;
    total_bytecode_bytes: number;
    total_classfile_bytes: number;
  };
  phase_3_erdos_kac: {
    definition: Record<string, string>;
    primary_scope: string;
    scopes: Record<string, {
      program_count: number;
      mean_distinct_components: number;
      spearman_log_size_vs_components: number;
      skewness: number;
      excess_kurtosis: number;
      qq_r_squared: number;
      pre_registered_shape_consistent: boolean;
      histogram: Array<{ z_left: number; z_right: number; count: number }>;
      qq_points: Array<{ normal_quantile: number; observed_z: number }>;
      size_bins: Array<{
        size_median: number;
        program_count: number;
        component_mean: number;
        component_stddev: number;
      }>;
    }>;
  };
  phase_4_component_size: {
    population: number;
    call_sites: number;
    spearman_log_use_vs_log_size: number;
    spearman_p_value: number;
    gross_savings_meets_log2_rank_fraction: number;
    global_component_identifier_min_bits: number;
    binned_points: Array<{
      rank_geometric_mean: number;
      median_uses: number;
      median_bytecode_length: number;
      theoretical_min_identifier_bits: number;
    }>;
    display_points: Array<{
      rank: number;
      uses: number;
      bytecode_length: number;
      gross_savings_bytes_per_use: number;
      method: string;
    }>;
  };
  phase_4_mdl_incompleteness: {
    status: string;
    definition: Record<string, string>;
    eligible_method_count: number;
    folds_with_positive_candidate: number;
    median_best_heldout_net_savings_bytes: number;
    folds: Array<{
      fold: number;
      train_methods: number;
      test_methods: number;
      selected_candidates: number;
      positive_heldout_candidates: number;
      best_heldout_net_savings_bytes: number;
      top_candidates: Array<{
        opcodes: string[];
        length: number;
        train_occurrences: number;
        train_packages: number;
        test_occurrences: number;
        test_classes: number;
        heldout_net_savings_bytes: number;
      }>;
    }>;
  };
  phase_5_cross_version: {
    status: string;
    definition: Record<string, string>;
    snapshots: Array<{
      label: string;
      classes: number;
      methods: number;
      bytecode_bytes: number;
      resolved_call_sites: number;
      reuse_rank_beta: number;
      reuse_rank_r_squared: number;
    }>;
    delta: {
      classes_percent: number;
      methods_percent: number;
      bytecode_bytes_percent: number;
      retained_methods: number;
      added_methods: number;
      removed_methods: number;
      net_methods: number;
    };
    new_component_adoption: {
      added_methods_referenced_anywhere: number;
      calls_to_added_methods: number;
      added_methods_referenced_from_retained_callers: number;
      retained_caller_calls_to_added_methods: number;
      gross_savings_proxy_bytes: number;
      top_added_components: Array<{
        method_key: string;
        uses: number;
        bytecode_length: number | null;
        gross_bytes: number | null;
      }>;
    };
    interpretation: Record<string, string>;
  };
};
