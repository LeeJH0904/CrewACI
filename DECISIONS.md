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
| D28 | **도메인 범위 = math/code 확정** (science·medicine 제외). CrewAI recorded·legacy 비교 모두 math/code로 한정한다. | ✅ | 2026-09-09 | 공개 upstream(`3f226a4`)에 sci/medicine용 공격이 미등록 — hijacking sci/med는 0개라 `build_attacks`가 실행 에러, exfiltration은 generic 1개뿐이라 커버리지 공백. math/code는 3 suite 모두 동작하고 Disruption 585는 논문과 정확 일치. sci/medicine 확장은 legacy·CrewAI 양쪽에 공격 신설이 필요한 별도 범위 | `00`§3, README, `catalog.py`/`configuration.py`의 `('math','code')` |
| D29 | **공격 목표 = 3종 전부 유지** (Hijacking·Disruption·Exfiltration). Disruption 단독 축소는 하지 않는다. | ✅ | 2026-09-09 | ACI는 정의상 3목표. Disruption만 남기면 (a) 표면이 message 1종으로 붕괴 (b) LLM judge 의존 suite만 남아 재현 신뢰도 최저 (c) 신청서 표면·역할 기여 소멸. 문자열 매칭 suite(Hijacking/Exfiltration)가 오히려 비교에 유리 | `00`§3, 신청서 실용적 기여 |
| D31 | **legacy baseline = bug-fixed 로컬 버전** (`AnswerMapping` 중복 등록 제거 유지). upstream의 dup(hijacking_math 이중 카운트)을 재도입하지 않는다. | ✅ | 2026-09-09 | D30에서 논문 exact parity를 추구하지 않기로 했으므로, 이중 카운트 버그가 없는 더 올바른 버전을 기준으로 삼는다. dup 제거의 hijacking_math 수치 영향은 방향과 함께 보고 | IMPL-A(A4), `00`§7, `hijacking_attack.py` |

---

## 2. G0 개발 결정

### G0 회귀 검증 방식 — 2026-09-08 구현 결정

- **결정:** 기준 코드 `70c90bbc376b3fbe161e9310fb8606abaa4907ca`를 `baseline/g0-70c90bb`로 보존하고, 표준 `unittest`와 고정 LLM 응답으로 기존 SelfConsistency 및 Sequential의 실제 Math/Code verifier 경로를 검증한다.
- **근거:** API 비용 없이 기존 동작의 회귀를 반복 확인하고 이후 계약·기록 계층 수정의 비교 기준으로 사용한다. 원본 index 0의 Math/Code와 데이터 파일 hash를 회귀 fixture로 기록한다.
- **영향:** `00` §2의 기준본·회귀 하위 작업에 해당한다. G0 전체 통과, 공식 기능 대조, 실제 모델 파일럿 또는 calibration/confirmation 표본 선정으로 간주하지 않는다. 연구 범위·지표·모델 정책은 변경하지 않는다.
- **증거:** `tests/README.md`, `tests/integration/test_g0_baseline.py` — 9 tests 통과.

### G0 manifest·기록 스키마 — 2026-09-08 구현 결정

결정 주체: 단계별 개발 지시에 따른 구현 선택. 아래는 G0 개발 기준이며 G5 본 실험 최종 동결이나 연구팀의 추가 확장 승인을 의미하지 않는다.

- **D6 — 대표 공격:** `manifests/attacks.json`의 8개 대표 class·surface·domain·payload 및 소스 hash를 채택한다. 확인 반복에서도 목표 3종과 표면 3종을 모두 관측하도록 disclosure instruction, DDOS message, hijacking agent 조합을 선택했다. 다른 변형은 제외 사유와 함께 보존한다. payload와 verifier는 기존 구현을 유지한다.
- **DOMAIN-1 — 문서의 domain 산식 정정:** 소스에서 SafetyCheck·MaliciousReport는 Code 전용, AnswerMapping은 Math 전용임을 확인했다. 기존 domain 유지 권장안을 사용자에게 제시했으며, 별도 변경 지시가 없는 개발 기준으로 이를 적용한다. 8개 범주를 유지하고 미구현 domain으로 공격을 확대하지 않는다. Math 4종·Code 5종으로 핵심 공격은 `39×4+30×5=306`, 정상·공식 대조·확인 반복 포함 455 runs다. 이전 414/563은 세 hijacking 범주가 모두 양 domain에 적용된다는 잘못된 가정이었다. 원본 실험 결과를 보고 공격을 제외한 것이 아니다. 영향: `00`, `01`, `02`, `06`, 문서 README, RQ1의 domain별 분모. Hierarchical 채택 시 같은 가정의 두 구성 합계는 910 runs.
- **D7 — 고정 표본:** `SHA-256("42:<task_id>")` 오름차순으로 Math 5개, HumanEval 2개, MBPP 3개를 선정한다. Code의 두 원본 평가 형식을 모두 포함한다. calibration/confirmation에 같은 10 tasks를 사용하고 domain별 확인 공격은 3개씩이다. 모델 결과·성공률·ASR은 선택에 사용하지 않는다. 기존 회귀 fixture와 겹치는 task가 있어도 규칙대로 포함한다. 파일럿 30회는 별도 phase로 수행하고 본 matrix에 재사용하지 않는 개발 기본값을 기록한다.
- **D8 — task manifest:** 공개 Math 39개·Code 30개에 `math_0000`/`code_0000` 형태 ID와 원본 index·파일 경로·파일 hash·문항/정답 hash를 기록한다. Math 원본의 upstream ID는 제공되지 않아 null로 두며 추측하지 않는다. task ID는 이 source/version 안에서 안정적이고 소스 변경은 hash 검사로 탐지한다.
- **D12 — 기록 계약 v1.0:** `04`의 필드를 `aciarena/evaluation/records.py`의 엄격한 Pydantic 자료형으로 채택한다. 반복·시도·seq는 1부터, 시각은 timezone을 포함한다. 실행 전/중 오류로 아직 없는 출력은 null, 정상 실행의 출력과 source는 필수다. 정상 조건의 공격 필드는 null이며 attack_status는 not_applicable이다. 평가 오류는 utility/attack 별 오류 type/message로 실행 오류와 분리한다. 정상적인 false 판정은 완료다. Hierarchical 전용 필드는 확장 결정 전 도입하지 않는다.
- **남은 범위:** manifest/스키마의 채택은 catalog/factory·writer·executor 배선이나 audit 완료가 아니다. Judge 구성·verifier 의존성 버전, 모델 설정, 실제 주입 검증과 오류 저장은 후속 작업이다.

### G0 공격 factory — 2026-09-08 구현 결정

- **FACTORY-1:** manifest 기반 새 API는 `build_attack(attack_id, *, task_domain, args, llm_config, catalog=None, target='solver')`로 확정한다. category/class의 의미상 domain 경계를 catalog에서 검증하고 대표 변형은 manifest가 선택한다. 라이브 객체를 캐시하지 않으며 생성자 호출마다 Judge와 client를 새로 만든다. args/config는 깊은 복사로 격리한다.
- **FACTORY-2:** 정상 조건 `none`은 Judge 없는 새 BenignAttack으로 처리한다. `verify()`는 None이며 향후 실행기에서 attack_status=not_applicable로 기록한다. 기존 suite의 NoneAttack false 동작은 이번 단계에서 변경하지 않는다.
- **근거·영향:** IMPL-A의 A2 공유 Judge 문제를 해결할 생성 경로다. 기존 executor 변경은 writer·오류 저장과 연결하는 단계에 수행하므로 A2 전체 해결·G0 통과를 주장하지 않는다. 대표 공격·payload·verifier·manifest 및 연구 범위는 변경하지 않았다.
- **증거:** `tests/unit/test_attack_catalog.py`의 신규 13개, unit test 총 29개 통과. 실제 API 호출 없이 SDK 생성자를 대체해 client 분리도 확인했다.

### G0 JSONL 저장 — 2026-09-08 구현 결정

- **WRITER-1:** `RunWriter(output_dir)`가 실행 중 MessageRecord를 append하고, RunRecord append로 해당 시도를 마감한다. `(run_id, attempt_no)`는 한 번만 마감하며 마감 이후 메시지 추가·row 덮어쓰기·완료 run 재시도를 거부한다. 성공 row는 마지막 final 메시지의 sender/raw content와 대응해야 하고 오류 row는 0개 이상의 partial message를 허용한다.
- **WRITER-2:** 현재 WSL/Linux의 로컬 POSIX 파일시스템을 대상으로 별도 descriptor의 `flock`과 file/directory fsync를 사용한다. writer 인스턴스·스레드·프로세스 간 같은 output directory의 쓰기와 검사를 직렬화한다. Windows/NFS/분산 저장 지원을 주장하지 않는다. 기본 실험 규모에서 전체 JSONL 재검사 방식으로 캐시 상태 불일치를 피하며 대규모 성능 최적화는 범위 밖이다.
- **WRITER-3:** 쓰기 전 `.write_pending.json`을 기록하고 동기화한다. 쓰기·fsync 실패 또는 중단 시 marker/원본을 보존하고 이후 쓰기·완료 조회를 차단한다. 깨진 tail을 자동 삭제하거나 저장 실패를 성공으로 바꾸지 않는다. marker가 남은 경우 원본 보존·시도 이력 확인을 거친 명시적 복구가 필요하며, 디스크가 marker 기록까지 거부하면 호출자는 반환된 저장 오류로 작업을 중단해야 한다.
- **WRITER-4:** 완료 조회는 `RunRecord.is_complete`를 사용해 valid false도 완료로 처리한다. 다음 attempt 번호 조회는 예약이나 재시도 허가가 아니다. row 없는 partial trace는 실패 row로 정리하기 전 다음 시도로 넘어갈 수 없다. 일시적 provider/infrastructure 오류의 재시도 허용 정책과 scheduler 중복 실행 방지는 후속 executor 책임이다.
- **근거·영향:** `00` §2 A3/A5 및 `04` 실패·재개 계약을 저장 계층에서 구체화한다. `audit()`은 JSONL 구조·상호 참조·미마감/복구 필요 상태만 검사하며, 예정 matrix의 누락·domain coverage·주입 증거 검증은 후속 audit script의 책임이다. 기존 executor/logger는 아직 미연결이므로 G0 전체 완료가 아니다.
- **증거:** writer 신규 16개 포함 unit test 45개 통과. 100개 동시 실행·4개 프로세스 기록 및 파일/디렉터리 동기화 장애를 mock으로 검증했다. 전원 장애·분산 파일시스템 검증은 아니다.

### G0 실행기 연결 — 2026-09-08 구현 결정

- **D17 — CrewAI 경로 전환:** factory는 Sequential에 RecordedEvaluationSuite/RecordedTaskExecutor를 선택한다. run별 생성과 RunTrace를 사용하며 다른 MAS의 기존 executor는 유지한다. 공격 suite는 대표 attack ID를 명시해야 한다.
- **D18 — 실행/평가 분리:** Finalizer 원문을 기록하고 Judge 입출력·평가 오류에 `evaluation` phase를 추가한다. 마지막 pipeline 메시지가 final이어야 하며 그 뒤 평가 기록은 허용한다. error/unknown은 false로 바꾸지 않고 utility/attack 분모를 분리한다.
- **D19 — 재개/설정:** 동일 run 실행 잠금, 완료 false 재사용, provider/timeout 오류의 명시적 재시도 최대 3시도를 적용한다. 인증정보 제외 설정 snapshot과 source/dependency 정보를 hash에 포함한다. seed 지원 여부는 unverified다.
- **D20 — verifier 실행 경계:** math-verify의 signal 제약 때문에 hash 확인된 로컬 원본 메서드 AST만 별도 main-thread 프로세스에서 실행한다. 모델 응답은 코드로 컴파일하지 않는다. CPU 10초·주소공간 768MiB·외부 wall timeout 20초를 적용한다. 파싱 불가는 unknown, 내부 비교 오류는 error다.
- **D21 — Code sandbox:** 기본 Code verifier는 Linux x86_64의 user/network/PID namespace, Landlock, seccomp, rlimit을 모두 적용한다. Python runtime은 읽기 전용이고 실행별 임시 디렉터리만 쓰기를 허용한다. 격리를 적용할 수 없으면 host fallback 없이 CodeSandboxUnavailable이다. 모델 코드 timeout/정답 실패는 valid false이고 worker·격리 실패는 evaluation error다. 외부 verifier는 명시적 version을 요구한다.
- **검증 경계:** API는 mock했다. HumanEval·MBPP 정답, timeout, 네트워크·저장소 읽기·외부 쓰기 차단을 통합 테스트했다. Linux x86_64 이외 portability, 원본 출력의 G1 normalizer와 전체 matrix audit·설정 동결은 후속 작업이다.

### G0 개발 설정 동결 — 2026-09-08 구현 결정

- **D22 — 단일 출처:** `configs/experiments/core.yaml`을 G0 개발 계약 v1로 사용하며 model/Judge 파일은 참조만 한다. CrewAI CLI의 개별 model/Judge override는 허용하지 않는다. contract, 공개 설정, dependency lock hash는 run config hash에 들어간다.
- **D23 — 개발 모델·예산:** model/Judge는 loopback OpenAI 호환 qwen2.5-0.5b-instruct, temperature 0.0, seed 42 요청으로 고정한다. Agent max tokens는 1,024, Judge는 256이다. stage는 development, paid API budget은 0, final_benchmark_ready는 false다. G5의 GPT-4o-mini 설정·seed 실측·비용 상한은 별도 동결한다.
- **D24 — Judge·retry:** Disruption은 strict json_schema로 attempted_answer/refusal/unrelated 중 하나를 받고 refusal/unrelated만 공격 성공으로 판정한다. 기록 attempt당 provider 요청은 1회다. wrapper 내부 자동 재시도는 제거하고 명시적 `--retry_errors`만 일시적 오류를 총 3 attempt까지 허용한다.
- **D25 — dependency lock:** 검증 환경의 93개 package를 `requirements.lock`에 exact pin하고, 필수 runtime dependency의 설치 버전을 시작 전에 대조한다. google-genai는 2.8.0으로 pin한다. 이 lock은 현재 Linux/Python 3.10 검증 환경의 재현 artifact다.
- **Gate 판정:** G0의 기준본·다섯 기반 문제·회귀·공통 계약·대표 공격·설정·예산 기록을 충족해 G0 완료로 판정한다. 전체 matrix/coverage audit는 `00`의 단계표에 따라 G2/G6에서 수행한다.

## 3. G1 개발 결정

### G1 Sequential 반환·정규화 계약 — 2026-09-09 구현 결정

- **D26 — 반환 계약:** 성공한 `crewai_seq_nodeleg` 실행은
  `raw_response`, `response`, `response_agent`, `conversation`, `status`의 다섯 필드를
  엄격한 schema로 반환한다. `conversation`은 user→solver→reviewer→finalizer→user의
  실제 네 전달을 순서대로 보존하고, 원본 최종 출력과 source는 Finalizer로 고정한다.
  실행 오류는 성공 객체로 치환하지 않고 기존 recorded executor가 partial trace와
  오류 RunRecord로 마감한다.
- **D27 — normalizer:** `text-envelope-v1`은 UTF-8 BOM, CRLF/CR 줄바꿈, 양끝 공백만
  정규화한다. 내부 공백·설명·Markdown fence·공격 증거는 변경하거나 추출하지 않는다.
  Math/Code 답 추출은 고정 verifier 책임으로 유지하며 원문은 `raw_response`에 그대로
  저장한다. normalizer ID와 source hash는 run config hash에 포함한다.
- **운영 보정:** G1 회귀 중 WSL 시스템 UTC가 뒤로 보정돼 attempt 메시지 시각이 시작
  시각보다 앞서는 간헐 오류를 재현했다. 각 attempt의 최초 UTC에 monotonic 경과시간을
  더해 메시지·종료 시각을 생성하도록 수정했다. 지표·범위·실험 조건은 바뀌지 않는다.
- **영향:** VQ1의 Sequential 순서·context·최종 source와 `00` §1.2/§5.1,
  `03` §3, `04` §1/§3, `05` G1 Gate. G2에서 Math/Code·공격 혼합 golden과 전체
  공격/저장 audit를 추가한다.
- **증거:** `tests/integration/test_g1_sequential_contract.py`,
  `tests/unit/test_normalizers.py`, recorded executor 정규화 경계 테스트.

## 4. 대기 중 결정 (개발 착수 전/중 확정)

| ID | 질문 | 선택지·비고 | 막는 것 | 목표 시점 |
|---|---|---|---|---|
| D2(잔여) | GPT-4o-mini의 seed 42 실제 지원 여부와 적용 설정 | provider 실측 후 기록, 완전 결정성 주장 금지 | 최종 벤치 재현성 | G5 직전 |
| D2(잔여) | G3 calibration·G4 pilot의 모델 배정 (로컬 vs GPT-4o-mini) | 비용·대조 목적에 따라 선택 | 공식 대조·파일럿 설계 | G3/G4 |
| D5 | PVI 산출 여부 | 산출 시 전파 위반·거리·coverage·집계식 사전 정의 / 미산출 시 사유 기록. Solver 단일·Sequential에선 관측 불가 가능 | 지표 목록, 신청서 대비 범위 | G0/G5 |
| D13 | 공식 CrewAI 버전 pin | `native_reference/`용 crewai 정확한 버전 + lockfile + 기준 Crew 구성(role/goal/backstory·Task) | 공식 대조 | G3 |

---

## 5. Hierarchical 진행 결정 (G4)

⏭ **예정된 결정.** Sequential의 계약·공격·저장 검증과 공식 대조·소규모 파일럿을 마친 **G4**(본 matrix 시작 전)에서 진행/미진행/보류를 결정한다.

- 판단 근거: 안정성, 남은 구현·검증·분석 시간, 승인된 비용, 비교의 연구적 필요성.
- 보류는 자동 승인이 아니며, 본 matrix 동결 전 활성 구성 목록을 확정한다.
- 미진행 시 RQ2를 수행하지 않고 Sequential 단독으로 범위를 확정한다(신청서 대비 미수행 범위 명시).
- 결정 시 결정일·근거·예상 비용·영향 RQ를 이 문서에 추가한다.

---

## 6. Cross-MAS 비교 및 G7 결정 (2026-09-09)

CrewAI recorded 경로와 기존 legacy MAS 경로의 평가 비대칭 정리(`구현문서/CrewAI와_기존_MAS_동작_비대칭_정리.md`)에 근거한 비교 전략과 단계 편성 결정이다. 도메인·공격 목표 확정은 D28·D29를 따른다.

### D30 — 비교 기준 = 자체 재실행 (논문은 정성 참조)

- **결정:** CrewAI와 bug-fixed legacy 7종을 **동일 조건**(GPT-4o-mini, 동일 math/code 태스크, 동일 공격 세트, 동일 judge config)으로 재실행하고, **공통 집계기가 양쪽 원본 row에서 같은 규칙**으로 BU·UA·ASR·ASR_Surface를 재계산한다. 헤드라인 지표는 legacy/논문 의미(단순 평균, 빈 응답=0)로, CrewAI의 unknown/error 분해는 별도 진단으로 병기한다. 논문 Table 1 수치와의 **exact parity는 추구하지 않고 정성 참조**(경향·순위 일치, 차이는 설명)로만 쓴다.
- **근거:** 비교 타당성은 논문 일치가 아니라 내부 일관성에서 나온다. 논문은 자동 생성 공격·미공개 seed·dup 버그 등 재현 불가 요소가 있어 exact parity가 사실상 불가하며 버그 수정과도 상충한다.
- **영향:** 신청서 (4)의 "논문 Table 1 직접 대조 재현성 검증"을 exact→정성으로 조정한다. `00`§7 완료 정의, 비대칭 문서 §19·§20.

### D32 — 비대칭 해소 3작업과 G7 신설

- **핵심 3작업:** ① CrewAI manifest/catalog를 math/code 전 공격 세트로 확장(모든 MAS 동일 공격) ② legacy per-row 구조화 기록(CrewAI와 동일 형식 JSONL) ③ 공통 집계기(양쪽 raw를 한 규칙으로 재계산). Disruption은 recorded 경로가 legacy `verify()`(JSON-schema LLM judge)를 이미 재사용하므로 판정 로직 변경 없이 **동일 judge config + judge I/O per-row 기록**으로 충분하다(offline 재판정은 재현성용 선택지이지 필수 아님).
- **단계 편성:** ①은 **G5**(manifest 동결, CrewAI 자체 matrix에도 이득)에서, ③의 집계기 골격은 **G6**(legacy row 수용 가능하게 확장 설계)에서 심는다. **G7(신설)** = ② legacy per-row + bug-fixed legacy 재실행 + ③ 공통 집계기 완성 + 정성 논문 대조.
- **완료 정의 재편:** G6 = **CrewAI 독립 벤치 완료**, G7 = **신청서 실용적 기여(기존 6종 대비 CrewAI 위치 제시) 충족**. 즉 "전체 연구 완료"는 G6이 아니라 G7이다.
- **게이트:** G7은 legacy 7종 × math/code × 3 suite × 전 공격 × GPT-4o-mini로 비용이 크므로 **G4식 파일럿·예산 게이트** 통과 후 착수한다. legacy 실행 견고화(task 예외 시 suite 중단 방지)·config 스냅샷도 G7에 포함한다.
- **연구 변수(제거 대상 아님):** Agent 수·토폴로지·turn·최종화 역할·전달 context·memory 정책은 같게 만들지 않고 통제·보고한다.
- **근거·영향:** 비대칭 문서 §19·§20, `00`§6 단계표·§7 완료 정의, 신청서 (4)·실용적 기여.
