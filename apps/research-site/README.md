# Knowledge Reuse Observatory

This Vite/React site presents compact public evidence from the complete
Lean/mathlib experiment. It is deliberately not a browser copy of the full
graph.

## Data boundary

The primary website graph is `lean-source-graph-v2`. It contains 566,238
internal declarations, 7,299 explicit external targets, 1,837,319 distinct
SOURCE pairs, and 2,384,749 resolved source-reference occurrences. Nine
parent-module mismatches are preserved as exclusions. The public
site publishes compact JSON evidence rather than the full graph:

- purposefully selected internal nodes (reuse heads, per-domain heads, and Expr
  complexity extremes);
- the 200 external targets with the most unique consumers;
- SOURCE-edge examples selected by multiplicity, self-loop status, and external
  target status;
- at most three deterministic SOURCE-pair examples for each nonempty
  internal source-domain to target-domain cell;
- the complete compact domain metrics and nonempty domain matrix cells.

Every payload records the complete population size and the published row count.
Samples explain records and support local audit; they are not used to estimate
the reported full-population statistics.

Regenerate and build:

```bash
just source-graph
just site-data
just site-build
```

## Domain algorithm

Domain labels are repository-path labels:

```text
domain(Mathlib.X....) = X
domain(non-Mathlib module) = first path segment
```

For the domain reuse matrix:

1. keep only edges whose source and target are both internal configured-corpus
   declarations;
2. preserve edge direction as consumer/source to dependency/target;
3. count each distinct `(src_id, dst_id)` SOURCE pair once; retain its resolved
   source-location count as `multiplicity`;
4. attach each endpoint's path domain;
5. group by `(src_domain, dst_domain)` and count unique pairs;
6. divide each cell by all internal unique pairs emitted by its source domain
   to obtain `row_share`.

External targets have no reliable domain assignment, so they are excluded from
the domain matrix instead of being assigned a fabricated `Other` domain. All
module hints observed in `.ilean` remain visible in the external-target sample.

The previous TYPE/VALUE Expr graph remains a separate expression-complexity
view. Its conceptually expanded DAG paths are not presented as source-reference
counts and do not drive the website's Zipf, concentration, or domain findings.

## Cloudflare Pages

The repository workflow builds the site on every relevant pull request. Once
the repository has the following GitHub Actions secrets and variable, pushes to
`main` deploy `apps/research-site/dist` with Wrangler:

- secret `CLOUDFLARE_API_TOKEN` with Account / Cloudflare Pages / Edit;
- secret `CLOUDFLARE_ACCOUNT_ID`;
- repository variable `CLOUDFLARE_DEPLOY_ENABLED=true`.

The one-time Pages project name is `knowledge-reuse-observatory`. The same site
can instead use Cloudflare's native Git integration with root directory
`apps/research-site`, build command `pnpm install --frozen-lockfile && pnpm
build`, and output directory `dist`.
