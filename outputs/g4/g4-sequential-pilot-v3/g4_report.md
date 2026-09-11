# G4 Sequential pilot report

- Experiment: `g4-sequential-pilot-v3`
- Gate: **PASS**
- Report version: `g4-pilot-report-v2`
- Report hash: `666cccfd33ec4c126a0be232f60a8b0dd190eb50bce305c0a49ca5dbd3ad2a46`
- Model policy: local Bionic (`paid API cost = $0`)

## Gate counts

| Item | Result |
|---|---:|
| Planned / observed logical runs | 30 / 30 |
| Completed runs | 30 (100.00%) |
| Execution failures | 0 |
| Result row storage | 100.00% |
| Activation flags recorded | 30 (100.00%) |
| Target invoked | 30 (100.00%) |
| Payload injected | 30 (100.00%) |
| Math raw parser valid | 14 / 15 (93.33%) |
| Math disruption non-answer resolved | 1 |
| Math utility evaluation valid | 15 / 15 (100.00%) |
| Code raw parser valid | 15 / 15 (100.00%) |
| Code disruption non-answer resolved | 0 |
| Code utility evaluation valid | 15 / 15 (100.00%) |
| Attempt rows | 30 |
| LLM calls (known rows) | 90 / 30 rows |
| Prompt tokens (known rows) | 55791 / 30 rows |
| Completion tokens (known rows) | 21367 / 30 rows |
| Cumulative latency | 676.647s |

## Checks

- [x] `audit_ok`
- [x] `completion_at_least_95pct`
- [x] `result_rows_100pct`
- [x] `activation_recorded_100pct`
- [x] `target_invoked_100pct`
- [x] `payload_injected_100pct`
- [x] `unexplained_non_injection_zero`
- [x] `math_evaluation_valid_at_least_98pct`
- [x] `code_evaluation_valid_at_least_98pct`
- [x] `duplicate_or_state_contamination_zero`
- [x] `paid_api_cost_within_approved_budget`

## Scope decision boundary

Technical status: `eligible_for_team_decision`. This report does not
fabricate research-team consensus. Hierarchical remains unapproved until the team records
its proceed / do-not-proceed / defer decision in `DECISIONS.md` with schedule, resource,
research-need, expected-cost, and RQ2 impacts.
