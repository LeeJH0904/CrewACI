# DECISIONS — CrewAI × ACIArena 연구 결정 기록

이 문서는 연구 진행에 필요한 주요 결정을 한곳에 기록한다. 각 결정은 결정일·근거·영향(연구 질문/문서)을 남기며, 범위·지표·구성 변경은 여기서 추적한다. 상세 기준은 `CrewAI_ACIArena_연구계획/`의 가이드(`00_구현_가이드.md`, `archive/01~06`)를 따른다.

**개발·검증 중 새로 확정이 필요한 사항이 생기면 그 즉시 이 문서에 추가한다** — G4 Hierarchical·모델 배정 같은 예정된 결정뿐 아니라, 개발 도중 발생하는 모든 범위·지표·구성·설정 결정을 대상으로 한다.

- 상태 표기: ✅ 확정 · 🔲 대기 · ⏭ 예정(스케줄된 결정)
- 결정자 기본값은 "연구팀 합의"이며, 필요 시 개별 확정자를 적는다.

---

## 1. 확정된 결정

| ID | 결정 | 상태 | 결정일 | 근거 | 영향 |
|---|---|---|---|---|---|
| D10 | **작업 공간 = 현 저장소 `CrewACI/`**. 별도 `Agent_field/…` 작업공간을 두지 않고, 안정화 기준본은 Git 브랜치·태그로 보존한다. | ✅ | 2026-09-07 | 이미 `CrewACI/`에서 진행 중이라 이동 비용 0. 물리적 분리 대신 브랜치 전략으로 기준본 보존 가능 | `00`§4, `03`§1 (재현성 서술) |
| D1/D2(부분) | **모델 사용 정책**: 개발·검증 등 실험 중 단계는 **Bionic 로컬 LLM API**로 수행(API 비용 0), **GPT-4o-mini는 최종 벤치(G5 본 matrix)에만** 사용. 로컬 실험 수치를 최종 벤치 결과로 간주하지 않는다. temp 0.0 / max 1024 / seed 42 요청은 공통. | ✅ | 2026-09-07 | 실험 중 비용 발생 차단, 로컬로 반복 개발·검증 | 예산, 재현성, RQ1. `00`§2·§3, `02`§5 |
| D15 | **참조 문서 정리**: 선행연구조사·논문_구현_비교·ACIARENA 원논문·MASLab 논문을 `ACIArena_관련_문서/`에 확보하고 가이드 링크 정정. `ACIArena_요약`·`CrewAI_통합_평가`·`CrewAI_대표성_및_재구현_설계`는 내용 중복으로 별도 파일 미유지(통합_정리로 병합). | ✅ | 2026-09-07 | 깨진 참조 해소, 자료 중복 제거 | `01`§2, `06`§2, `통합_정리`§6 |
| SCOPE-1 | **완료 기준 우선순위**: `통합_정리`(2026-08-05) §4.8의 광의 완료 기준(seq+hier·delegation·manager 포함)이 아니라, `archive/`(특히 05)·`00`의 축소 기준을 확정 기준으로 한다. delegation·hierarchical·manager는 G4 승인 시에만 적용. | ✅ | 2026-09-07 | 신청서 대비 범위 축소 결정 반영 | `05`, `00`§7, `통합_정리`§4.8 |
| IMPL-A | **G0 기준본 수정 방침**: A1(mutable default)·A4(중복 `AnswerMappingAgent`)는 즉시 수정 완료. A2(공유 attack 경합)는 run별 `deepcopy` **최소 수정**으로 경합만 차단하고 catalog/factory 정공법은 개발 단계로 이월. A3(로거 격리)·A5(오류 RunRecord)는 C절(기록 계층) 구축 시 함께 처리. | ✅ | 2026-09-07 | 동기화 단계는 정합·안전 확보에 집중, 큰 구현은 개발 단계로 분리 | `00`§2, 코드(`base_agent`/`base_mas`/`task_executor`/`hijacking_attack`) |

---

## 2. 대기 중 결정 (개발 착수 전/중 확정)

| ID | 질문 | 선택지·비고 | 막는 것 | 목표 시점 |
|---|---|---|---|---|
| D2(잔여) | GPT-4o-mini의 seed 42 실제 지원 여부와 적용 설정 | provider 실측 후 기록, 완전 결정성 주장 금지 | 최종 벤치 재현성 | G5 직전 |
| D2(잔여) | G3 calibration·G4 pilot의 모델 배정 (로컬 vs GPT-4o-mini) | 비용·대조 목적에 따라 선택 | 공식 대조·파일럿 설계 | G3/G4 |
| D5 | PVI 산출 여부 | 산출 시 전파 위반·거리·coverage·집계식 사전 정의 / 미산출 시 사유 기록. Solver 단일·Sequential에선 관측 불가 가능 | 지표 목록, 신청서 대비 범위 | G0/G5 |
| D6 | 8개 범주 **대표 `attack_id`/class/surface** 선택 | 범주당 대표 구현 1개, `attacks.json` 동결. import 순서 의존 금지 | manifest, 실행 규모 | G0 |
| D7 | calibration/confirmation 표본 | Math 5 / Code 5 + domain별 대표 공격 3종 사전 지정 | 파일럿·확인 반복 | G0 |
| D8 | task manifest 고정 | Math 39 / Code 30의 task_id·원본 index·출처·hash | 재현성, 분모 | G0 |
| D9 | Judge·verifier 동결 | Debug_log의 `json_schema` 전환·판정 분류(attempted_answer/refusal/unrelated)를 확정하고 `verifier_version` 기록 | 보안 판정 신뢰성 | G0 |
| D11 | config 단일 출처 | `configs/experiments/core.yaml`이 `model.yaml`을 **참조**(복제 금지), 하드코딩 경로 배선 정리 | 설정 진입점 | 개발 단계 |
| D12 | 기록 스키마 채택 | `04`의 `runs.jsonl`/`messages.jsonl` 필드안 확정 (A3·A5 포함) | 감사·지표 재계산 | 개발 단계 |
| D13 | 공식 CrewAI 버전 pin | `native_reference/`용 crewai 정확한 버전 + lockfile + 기준 Crew 구성(role/goal/backstory·Task) | 공식 대조 | G3 |

---

## 3. Hierarchical 진행 결정 (G4)

⏭ **예정된 결정.** Sequential의 계약·공격·저장 검증과 공식 대조·소규모 파일럿을 마친 **G4**(본 matrix 시작 전)에서 진행/미진행/보류를 결정한다.

- 판단 근거: 안정성, 남은 구현·검증·분석 시간, 승인된 비용, 비교의 연구적 필요성.
- 보류는 자동 승인이 아니며, 본 matrix 동결 전 활성 구성 목록을 확정한다.
- 미진행 시 RQ2를 수행하지 않고 Sequential 단독으로 범위를 확정한다(신청서 대비 미수행 범위 명시).
- 결정 시 결정일·근거·예상 비용·영향 RQ를 이 문서에 추가한다.
