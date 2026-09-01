import type {
  DomainEdgeSample,
  ExternalTargetSample,
  NodeSample,
  Overview,
  SamplePayload,
  TypedEdgeSample,
} from "./types";

const ROOT = "/datasets/lean_mathlib_v1/mathlib-v4.32.1";

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
export const loadTypedEdges = () =>
  loadJson<SamplePayload<TypedEdgeSample>>("typed-edge-samples.json");

export function mathlibModuleUrl(module: string): string {
  return `https://github.com/leanprover-community/mathlib4/blob/v4.32.1/${module.replaceAll(".", "/")}.lean`;
}
