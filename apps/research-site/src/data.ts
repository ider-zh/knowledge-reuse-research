import type {
  DomainEdgeSample,
  ConstructionCases,
  ExternalTargetSample,
  NodeSample,
  OpenJdkReuseReport,
  Overview,
  PathRankComparison,
  RankFrequencyDistribution,
  SamplePayload,
  SourceEdgeSample,
} from "./types";

const ROOT = "/datasets/lean_mathlib_v1/mathlib-v4.32.1";
const OPENJDK_ROOT = "/datasets/software_v1/openjdk-28-b13";
const OPENJDK_DATASET_VERSION = "v2";

async function loadJson<T>(path: string): Promise<T> {
  const response = await fetch(`${ROOT}/${path}`);
  if (!response.ok) {
    throw new Error(`无法加载 ${path}: HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const loadOverview = () => loadJson<Overview>("overview.json");
export const loadNodes = () => loadJson<SamplePayload<NodeSample>>("nodes.json");
export const loadExternalTargets = () =>
  loadJson<SamplePayload<ExternalTargetSample>>("external-targets.json");
export const loadDomainEdges = () =>
  loadJson<SamplePayload<DomainEdgeSample>>("domain-edge-samples.json");
export const loadSourceEdges = () =>
  loadJson<SamplePayload<SourceEdgeSample>>("source-edge-samples.json");
export const loadConstructionCases = () => loadJson<ConstructionCases>("construction-cases.json");
export const loadRankFrequency = () =>
  loadJson<RankFrequencyDistribution>("reuse-rank-frequency.json");
export const loadPathRankComparison = () =>
  loadJson<PathRankComparison>("path-rank-comparison.json");

export async function loadOpenJdkReuseReport(): Promise<OpenJdkReuseReport> {
  const response = await fetch(
    `${OPENJDK_ROOT}/method-reuse-${OPENJDK_DATASET_VERSION}.json`,
  );
  if (!response.ok) {
    throw new Error(`无法加载 OpenJDK 报告: HTTP ${response.status}`);
  }
  const payload = await response.json() as Partial<OpenJdkReuseReport>;
  if (
    payload.schema_version !== "1.1"
    || !payload.samples?.method_nodes
    || !payload.extraction_examples?.node
    || !payload.extraction_examples?.edge
  ) {
    throw new Error("OpenJDK 报告数据版本不匹配，请刷新页面");
  }
  return payload as OpenJdkReuseReport;
}

export function mathlibModuleUrl(module: string): string {
  return `https://github.com/leanprover-community/mathlib4/blob/v4.32.1/${module.replaceAll(".", "/")}.lean`;
}
