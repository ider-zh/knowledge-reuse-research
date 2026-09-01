# Knowledge Reuse Observatory

This Vite/React site presents compact public evidence from the complete
Lean/mathlib experiment. It is deliberately not a browser copy of the full
graph.

## Data boundary

The full experiment contains 566,238 internal declarations, 10,805 explicit
external targets, 24,741,186 unique typed edges, and 16,812,652 unique
source-target dependency pairs. The public site publishes approximately 2 MB
of JSON:

- purposefully selected internal nodes (reuse heads, per-domain heads, and Expr
  complexity extremes);
- the 200 external targets with the most unique consumers;
- typed-edge examples stratified by TYPE/VALUE, source domain, and target
  domain, including an explicit `EXTERNAL` target group;
- at most three deterministic unique dependency-pair examples for each nonempty
  internal source-domain to target-domain cell;
- the complete compact domain metrics and nonempty domain matrix cells.

Every payload records the complete population size and the published row count.
Samples explain records and support local audit; they are not used to estimate
the reported full-population statistics.

Regenerate and build:

```bash
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
3. collapse TYPE and VALUE rows with the same `(src_id, dst_id)` to one unique
   dependency pair;
4. attach each endpoint's path domain;
5. group by `(src_domain, dst_domain)` and count unique pairs;
6. divide each cell by all internal unique pairs emitted by its source domain
   to obtain `row_share`.

External targets have no reliable module provenance, so they are excluded from
the domain matrix instead of being assigned a fabricated `Other` domain. They
remain visible in the external-target and typed-edge public samples.

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
