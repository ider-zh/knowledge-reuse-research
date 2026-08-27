# Agent handoffs

Each active workstream keeps one short handoff named after its experiment. It
records owner/agent, branch or commit, files in scope, current gate/evidence,
commands run, intentionally uncommitted artifacts, blockers, and next action.

Agents must not stage or commit another workstream's dirty files. Changes to
schemas/core or knowledge_reuse/analysis require tests from every affected
adapter and a note in each active handoff.
