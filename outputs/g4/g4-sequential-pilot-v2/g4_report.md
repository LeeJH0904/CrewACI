# G4 Sequential pilot report

- Experiment: `g4-sequential-pilot-v2`
- Gate: **FAIL**
- Report version: `g4-pilot-report-v1`
- Report hash: `72a9a00caf1d08a3c328366d00821931c04d6016f1ad6d37050dad74976a2aa9`
- Model policy: local Bionic (`paid API cost = $0`)

## Gate counts

| Item | Result |
|---|---:|
| Planned / observed logical runs | 30 / 30 |
| Completed runs | 29 (96.67%) |
| Execution failures | 0 |
| Result row storage | 100.00% |
| Activation flags recorded | 30 (100.00%) |
| Target invoked | 30 (100.00%) |
| Payload injected | 30 (100.00%) |
| Math parse/evaluation valid | 14 / 15 (93.33%) |
| Code parse/evaluation valid | 15 / 15 (100.00%) |
| Attempt rows | 30 |
| LLM calls (known rows) | 90 / 30 rows |
| Prompt tokens (known rows) | 55934 / 30 rows |
| Completion tokens (known rows) | 21261 / 30 rows |
| Cumulative latency | 645.821s |

## Checks

- [x] `audit_ok`
- [x] `completion_at_least_95pct`
- [x] `result_rows_100pct`
- [x] `activation_recorded_100pct`
- [x] `target_invoked_100pct`
- [x] `payload_injected_100pct`
- [x] `unexplained_non_injection_zero`
- [ ] `math_parse_at_least_98pct`
- [x] `code_parse_at_least_98pct`
- [x] `duplicate_or_state_contamination_zero`
- [x] `paid_api_cost_within_approved_budget`

## Scope decision boundary

Technical status: `not_eligible_gate_failed`. This report does not
fabricate research-team consensus. Hierarchical remains unapproved until the team records
its proceed / do-not-proceed / defer decision in `DECISIONS.md` with schedule, resource,
research-need, expected-cost, and RQ2 impacts.
