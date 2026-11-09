#!/usr/bin/env bash
# E10a: run one offline or replayed evaluation and compare it with the baseline.
# No step calls a model: replay fails closed on a missing recording, and the
# retrieval models are local and loaded offline.
#
#   scripts/evaluation/behavior_gate.sh routing    # no database (Settings still needs placeholder passwords)
#   scripts/evaluation/behavior_gate.sh sql        # needs the acme demo database
#   scripts/evaluation/behavior_gate.sh retrieval  # needs agent_platform_test and HF_HOME
#
# Reports go to ${GATE_OUT:-gate-reports}; run from backend/.
set -euo pipefail

out="${GATE_OUT:-gate-reports}"
mkdir -p "$out"
export PYTHONPATH="${PYTHONPATH:-.}"
fixtures=tests/fixtures
gate=scripts/evaluation/check_behavior_gate.py

case "${1:-}" in
  routing)
    python scripts/evaluation/run_planner_route_evaluation.py --mode replay \
      --cassette-dir "$fixtures/evaluation_routing/cassettes_heldout_v1" \
      --cases "$fixtures/evaluation_routing/plan_rules_heldout_v1.json" \
      > "$out/planner_route.json"
    python scripts/evaluation/run_plan_rules_evaluation.py \
      --planner-results "$out/planner_route.json" > "$out/plan_rules.json"
    python "$gate" planner_route "$out/planner_route.json"
    python "$gate" plan_rules "$out/plan_rules.json"
    ;;
  sql)
    python scripts/evaluation/run_sql_result_evaluation.py --mode replay \
      --cassette-dir "$fixtures/evaluation_sql/cassettes_v2" \
      --report "$out/sql_results.json" > /dev/null
    python "$gate" sql_results "$out/sql_results.json"
    ;;
  retrieval)
    # Only the policy the main chain uses (settings.rag_retrieval_policy); the
    # eight-policy comparison stays a manual experiment (about 25 minutes).
    HF_HUB_OFFLINE=1 python scripts/evaluation/run_retrieval_evaluation.py \
      --policies paragraph_jieba_rrf_rerank_v1 > "$out/retrieval.json"
    python "$gate" retrieval "$out/retrieval.json"
    ;;
  *)
    echo "usage: $0 routing|sql|retrieval" >&2
    exit 2
    ;;
esac
