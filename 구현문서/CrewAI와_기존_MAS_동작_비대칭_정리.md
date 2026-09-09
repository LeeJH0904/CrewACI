# CrewAI와 기존 MAS 동작 비대칭 정리

- 작성일: 2026-09-09
- 기준 코드: `76ea110b92c880dc8f0941191eee9bad6d4cc888`
- CrewAI 대상: `crewai_seq_nodeleg`
- 기존 MAS 대상: `autogen`, `agentverse`, `camel`, `llm_debate`, `mad`, `metagpt`, `sc`
- 현재 Gate: G1 완료, G2 공격·저장 검증 전

이 문서는 현재 저장소에서 `crewai_seq_nodeleg`와 기존 ACIArena MAS가 서로 다른
방식으로 선택·실행·검증·기록되는 지점을 코드 기준으로 정리한다. 여기서 CrewAI는
공식 `crewai` 패키지 runtime이 아니라 ACIArena의 `BaseMAS` 위에 재구현한
Sequential No-Delegation 구성이다. 공식 runtime과의 일치는 G3 calibration 전까지
확정된 사실이 아니다.

문서에서 비대칭은 다음 세 종류로 구분한다.

| 구분 | 의미 | 처리 원칙 |
|---|---|---|
| 비교 차단 | 같은 이름의 지표를 직접 비교하기 어렵게 만드는 평가 인프라 차이 | 본 비교 전 정렬 또는 분리 보고 |
| 관측 차이 | 공격 노출·오류·로그를 서로 다른 해상도로 관측하는 차이 | 같은 필드와 분모로 보강 |
| 연구 변수 | 역할·토폴로지·상호작용처럼 원래 비교하려는 MAS 차이 | 제거하지 말고 명시적으로 통제·보고 |

## 1. 결론

현재 저장소에는 하나의 공통 CLI 아래 사실상 두 평가 파이프라인이 공존한다.

```text
benchmark.py
├─ crewai_seq_nodeleg
│  └─ RecordedEvaluationSuite → RecordedTaskExecutor
│     → manifest 단위 선택 → 격리 verifier → JSONL 기록·감사
└─ 그 외 MAS
   └─ 기존 *Suite → ContinuousAttackExecutor
      → registry 일괄 선택 → 직접 verifier → 기존 로그·result.json
```

공격 payload와 다수의 `verify()` 구현, Math/Code task 자료는 공유한다. 그러나 공격
선택 단위, 실행 격리, verifier 호출 경계, 정규화, 오류 분류, 분모, 로그, 재개,
설정 동결이 다르다. 따라서 현재 CrewAI ASR과 기존 MAS ASR은 이름만 같을 뿐,
별도의 정렬 없이 직접 비교 가능한 동일 실험량이라고 볼 수 없다.

> **결정 반영 (2026-09-09, `DECISIONS.md` D28~D32):** 이 문서는 비대칭을 진단·목록화한 분석이며, 실제 해소 범위는 다음으로 확정됐다 — 도메인 = math/code(sci·medicine 제외), 공격 목표 = 3종 전부, 비교 기준 = 동일 조건 자체 재실행(bug-fixed legacy + 정렬 CrewAI)과 공통 집계기이며 논문은 정성 참조(exact parity 비추구). 해소 핵심은 세 작업 — ① CrewAI manifest를 math/code 전 공격 세트로 확장(→ G5), ② legacy per-row 기록, ③ 공통 집계기(→ G6 골격·G7 완성) — 이고, cross-MAS 비교는 신설 단계 **G7**에서 수행한다. 아래 §15(방어)·§16(domain)·§19.2 일부처럼 이 범위를 넘는 서술은 참고용 진단일 뿐 착수 대상이 아니며, 해당 절에 그 경계를 표시했다.

## 2. 공통으로 유지되는 기반

비대칭을 과장하지 않기 위해 실제 공유 지점부터 고정한다.

- 모든 MAS는 [BaseMAS](../aciarena/mas/base_mas.py)와
  [BaseAgent](../aciarena/agent_components/base_agent.py)의
  `bootstrap → step → conclude`, `run_step → pre_step → step → post_step` 기반을 사용한다.
- 공격 표면의 기본 구현은
  [base_attack.py](../aciarena/attacks/base_attack.py)의 instruction, malicious agent,
  message poison monkey patch를 공유한다.
- Math 원문 데이터와 `math-verify`, Code 원문 데이터와 HumanEval/MBPP 정답 계약을
  공유한다.
- 기본 개발 모델과 Judge는 현재 모두 `configs/model.yaml`, `configs/judge.yaml`의
  loopback `qwen2.5-0.5b-instruct`를 가리킨다.
- Answer Mapping의 숫자 치환, Disclosure의 문자열 포함 판정, Code Hijacking의 문자열
  포함 판정 등 공격 목표 자체는 기존 공격 class에서 가져온다.

공통 공격 소스를 사용한다는 사실은 실행·집계까지 동일하다는 뜻은 아니다.

## 3. CLI와 평가 진입점 비대칭

[benchmark.py](../benchmark.py)는 `mas == crewai_seq_nodeleg`일 때만 즉시 recorded
경로로 분기한다. 나머지는 legacy 경로를 사용한다.

| 항목 | CrewAI recorded | 기존 MAS legacy | 영향 |
|---|---|---|---|
| suite 생성 | `RecordedEvaluationSuite` | `Benign/Hijacking/Disruption/DisclosureSuite` | 평가 코드 자체가 다름 |
| 공격 지정 | 공격 suite에서 `--attack_ids` 필수 | `--suite`와 domain으로 자동 선택 | 실행 공격 수·구성이 다름 |
| 기본 `--suite` | `hijacking`이지만 ID가 없으면 오류 | `hijacking` 전체를 바로 실행 | 같은 생략 명령의 의미가 다름 |
| `--experiment_config` | 사용하고 검증 | 사용하지 않음 | 설정 계약 비대칭 |
| `--experiment_id` | run identity와 출력 경로에 사용 | 사용하지 않음 | 재현·충돌 정책 비대칭 |
| `--phase`, `--repetition` | run ID 구성 요소 | 사용하지 않음 | calibration/core 구분 불가 |
| `--resume`, `--retry_errors` | 지원 | 사용하지 않음 | 재개·재시도 의미 비대칭 |
| `--model_config`, `--judge_config` | 개별 override를 명시적으로 거부 | 도움말은 legacy override라고 하나 현재 suite가 고정 YAML을 읽어 실질적으로 사용하지 않음 | CLI 설명과 실제 동작 불일치 |
| `--defense` | `none`만 허용 | 5종 지원 | 방어 비교 불가 |
| `--malicious_agents` | `solver` 하나만 허용 | MAS별 이름·복수 target 허용 | 공격 위치·공격자 수가 다름 |
| `--attack_mode` | `continuous`만 검증 후 허용 | registry에서 executor 선택 | 현재 값은 같지만 검증 경로가 다름 |
| `--limit` | manifest에서 domain 필터 후 앞 N개 | raw dataset에서 앞 N개 | 현재 순서는 대응해도 CrewAI만 hash로 고정 |
| `--max_workers` | 양수 여부를 사전 검사 | ThreadPool 생성에 위임 | 실패 시점·오류 형식이 다름 |

`--attack_ids`는 parser에는 공통으로 보이지만 기존 MAS의 `build_attacks()`에서는 읽지
않는다. 따라서 기존 MAS 명령에 ID를 추가해도 단일 공격 비교가 되지 않는다.

## 4. 공격 선택과 실행량 비대칭

### 4.1 선택 정책

CrewAI는 [manifests/attacks.json](../manifests/attacks.json)의 8개 대표 공격에서
명시한 ID만 실행한다. 각 ID는 class, goal, domain, surface, target, payload hash,
source hash, verifier hash에 고정된다. 중복 ID와 suite/domain 불일치는 실행 전에
거부한다.

기존 MAS는 [factory.py](../aciarena/utils/factory.py)의 전역 decorator registry에서
`<suite>`와 `<suite>_<domain>`에 등록된 class를 모두 가져온다. 고유 attack ID나
manifest fingerprint를 사용하지 않으며 등록/import 결과가 선택 집합이 된다.

### 4.2 현재 공격 수

기존 MAS가 task 하나당 자동 실행하는 공격 수는 다음과 같다.

| suite | Math legacy | Code legacy |
|---|---:|---:|
| disclosure | 5 | 5 |
| disruption | 5 | 5 |
| hijacking | 3 | 4 |

CrewAI 개발 manifest의 대표 공격 수는 다음과 같다.

| suite | Math recorded | Code recorded |
|---|---:|---:|
| disclosure | 2 | 2 |
| disruption | 1 | 1 |
| hijacking | 1 | 2 |

이는 범주당 기존 변형 하나를 선정한 개발 정책의 결과다. 현재 명령

```bash
.aciarena/bin/python benchmark.py \
  --mas crewai_seq_nodeleg \
  --suite hijacking \
  --task_domain math \
  --attack_ids hijacking_answer_mapping.agent.v1 \
  --limit 10
```

은 `10 tasks × AnswerMappingAgent 1종 = 10 runs`다. 반면 아래 legacy 명령은

```bash
.aciarena/bin/python benchmark.py \
  --mas sc \
  --suite hijacking \
  --task_domain math \
  --malicious_agents sc1 \
  --limit 10 \
  --max_workers 1
```

`10 tasks × {AnswerMappingAgent, AnswerMappingInstruction, MathInvertMessage} = 30개`
task-attack 실행을 하나의 ASR로 합친다. 두 ASR은 공격 집합과 표면 가중치가 다르다.

### 4.3 객체와 상태 격리

CrewAI는 매 attempt마다 catalog factory로 새 Attack과 새 Judge wrapper/client를
만든다. 공격 객체, Agent, MAS, trace가 run 사이에 공유되지 않는다.

Legacy executor는 suite 시작 시 만든 attack template 목록을 task마다 `deepcopy()`한다.
하지만 `BaseAttack.__deepcopy__()`는 `llm_judge`를 의도적으로 같은 객체로 복사한다.
따라서 Judge가 필요한 공격에서는 여러 task/thread의 Judge client와 token counter가
공유될 수 있다. 정적 verifier 공격은 Judge를 호출하지 않아 직접 판정에는 영향이
없지만, 객체 격리 계약은 CrewAI와 다르다.

### 4.4 공격 target과 노출 횟수

CrewAI recorded catalog는 Math/Code와 `solver` 한 곳만 허용한다. Sequential에서 Solver는
한 번 호출되므로 instruction/agent/message 공격의 직접 노출도 한 번이다.

Legacy MAS는 하나 이상의 서로 다른 역할을 target으로 지정할 수 있고, 해당 역할이
여러 round에서 반복 호출되면 같은 monkey patch가 매 호출에 적용된다. 예를 들어
AgentVerse Solver나 debate 참여자는 반복 노출될 수 있고, message poison은 target의
LLM 호출을 매번 payload 반환으로 대체한다. 따라서 같은 payload라도 공격 강도와
전파 기회가 토폴로지·turn 수에 따라 달라진다. 이 차이는 연구 변수지만 target 수와
호출 횟수를 함께 기록하지 않으면 인프라 차이처럼 ASR에 섞인다.

복수 target을 허용하는 legacy 공격 hook은 loop 안의 monkey patch closure가 마지막
`original_step`을 참조할 가능성도 있다. CrewAI는 단일 Solver만 허용하므로 이 위험에
노출되지 않는다. 복수 악성 Agent 결과는 별도 검증 없이 CrewAI 결과와 비교하면 안 된다.

## 5. MAS 실행 의미와 최종 응답 source

다음 차이는 대부분 제거 대상이 아니라 각 MAS의 역할·토폴로지라는 연구 변수다.

| MAS | 기본 Agent/역할 | 기본 `max_turn` | 최종 응답 source |
|---|---|---:|---|
| CrewAI Sequential | solver → reviewer → finalizer | 1 | finalizer |
| AutoGen | assistant ↔ user_proxy | 2 | assistant |
| AgentVerse | role_assigner, solver, critic, evaluator | 3 | solver solution |
| CAMEL | task_specifier, assistant, user_proxy, critic | 2 | assistant |
| LLM Debate | debater 3명 + aggregator | 2 | aggregator |
| MAD | affirmative, negative, moderator, 내부 judge | 2 | moderator 또는 내부 judge |
| MetaGPT | PM → architect → project manager → engineer → QA | 3 | qa_engineer output |
| Self Consistency | sc1~sc5 → aggregate | 1 | aggregate |

CrewAI는 작업자 3명을 각각 정확히 한 번 호출하고, Reviewer에 원문+초안,
Finalizer에 원문+초안+검토를 전달한다. `allow_delegation=False`이며 memory/cache를
run 간 공유하지 않는다. 기존 MAS는 각자의 종료 조건, 반복 round, history, 내부
JSON 파싱과 aggregation prompt를 사용한다.

MAD의 `judge` Agent는 MAS 내부 최종 선택자이며 보안 평가용 LLM Judge와 다른 개념이다.
호출량을 셀 때 둘을 구분해야 한다.

CrewAI만 `response_agent=finalizer`를 기계적으로 검사한다. 기존 MAS 결과에는 공통
`response_agent`가 없어 최종 source를 코드별로 추론해야 한다. 이 토폴로지 차이는
유지하되, 비교용 기록에서는 각 MAS의 source 역할을 명시해야 한다.

## 6. 반환 계약과 정규화 비대칭

CrewAI 성공 결과는 Pydantic strict schema로 다음 다섯 field만 허용한다.

```python
{
    "raw_response": str,
    "response": str,
    "response_agent": "finalizer",
    "conversation": list,
    "status": "success",
}
```

대화 경로도 user→solver→reviewer→finalizer→user의 네 entry와 순서를 강제하고,
마지막 message가 `raw_response`와 같아야 한다. `response`는 `text-envelope-v1`으로
BOM, 줄바꿈 형식, 양끝 공백만 정리한다.

기존 MAS의 공통 실질 계약은 `args["response"]`가 존재한다는 정도다. extra field,
conversation 형식, 응답 source, 문자열 형식, raw/normalized 구분을 강제하지 않는다.
대부분 `conclude()`가 dict를 그대로 반환하며, MetaGPT만 별도 conversation dict를
추가한다. verifier는 각 MAS의 `response`를 별도 정규화 없이 직접 읽는다.

따라서 다음 입력은 경로별로 다른 판정을 낼 여지가 있다.

- 앞 BOM이나 CRLF, 양끝 공백이 있는 응답
- 최종 응답 외 설명·중간 답이 함께 있는 응답
- 비문자열 또는 빈 응답
- 최종 Agent가 아닌 중간 Agent에서 유래했지만 `response`에 들어간 응답

CrewAI의 현재 `RunRecord` schema는 `topology=sequential`,
`malicious_agent=solver`, `response_agent=finalizer` literal로 고정되어 있다. 그대로는
기존 MAS를 같은 recorded writer에 수용할 수 없으며, 공통화하려면 역할/source와
topology field를 일반화하되 CrewAI의 개별 불변식은 별도 schema로 유지해야 한다.

## 7. Utility verifier 비대칭

| 도메인 | CrewAI recorded | 기존 MAS legacy | 판정 차이 |
|---|---|---|---|
| Math | 별도 `python -I` worker, source hash 확인, CPU/메모리 제한 | main process에서 `MathTask.verify()` 직접 호출 | parse 실패·내부 오류 상태가 다름 |
| Code | Linux x86_64 user/net/PID namespace + Landlock + seccomp + rlimit worker | `human_eval` multiprocessing/reliability guard | 안전 경계·timeout·지원 OS가 다름 |

CrewAI Math worker는 gold 또는 answer parse 결과가 비면 `None`을 반환해
`utility_status=unknown`으로 기록하고 유효 분모에서 제외한다. Legacy Math verifier는
빈 응답에 대해 현재 `0.0`을 반환하므로 일반 오답으로 분모에 포함한다. 이는 같은
출력에 대해 UA/BU 분모가 달라지는 실제 판정 비대칭이다.

CrewAI Code verifier는 격리를 구성할 수 없으면 host fallback 없이 평가 오류로 남긴다.
Legacy Code verifier는 별도의 Linux namespace/Landlock/seccomp 요구 없이 기존
HumanEval 호환 실행기를 사용한다. 실행 제한과 실패 분류가 다르므로 Code pass@1도
현재 상태에서는 동일 verifier 조건이라고 할 수 없다.

## 8. Attack verifier와 Judge 비대칭

Judge 호출 여부는 MAS나 Math/Code만으로 결정되지 않고 공격 verifier가 결정한다.

| 공격 유형 | CrewAI | 기존 MAS |
|---|---|---|
| Answer Mapping | 격리 Math worker로 정적 비교 | `AnswerMapping*.verify()` 직접 정적 비교 |
| Math Invert | 개발 manifest에서 미선정 | legacy Math Hijacking에 자동 포함, 정적 비교 |
| Safety Check/Malicious Report | 문자열 포함 정적 판정 | 문자열 포함 정적 판정 |
| Disclosure | 합성 개인정보 문자열 포함 정적 판정 | 합성 개인정보 문자열 포함 정적 판정 |
| Disruption | strict JSON Schema LLM Judge, 입출력 trace | LLM Judge 직접 호출, stdout 출력 중심 |

Answer Mapping의 숫자 치환 의미는 공유하지만 CrewAI만 worker 격리, source hash,
parse unknown, 평가 오류 field를 적용한다. 정적 verifier에서도 기반 호출 경계가
완전히 같지는 않다.

모든 legacy `BaseAttack`은 정적 verifier인지와 무관하게 생성 시 Judge 객체를 만든다.
CrewAI도 선택 공격 class를 생성하면 Judge 객체가 생길 수 있지만 Answer Mapping에서는
호출하지 않는다. CrewAI benign의 `BenignAttack`만 Judge를 만들지 않고 공격 판정도
`not_applicable`로 둔다. Legacy `NoneAttack`은 Judge를 만들고 `verify=False`를 정의하지만
benign suite에서 security 평가 자체는 하지 않는다.

CrewAI는 Judge가 실제 호출될 때 prompt와 raw 응답을 `evaluation` message로 저장하고
Agent 호출량과 구분해 센다. Legacy disruption은 `[Security Judge]`를 stdout에
출력하지만 동일 수준의 영속적 Judge 입출력·호출 수 연결이 없다.

## 9. 실행 상태, 예외, 재시도 비대칭

CrewAI는 실행 상태와 평가 결과를 분리한다.

- 실행: `success`, `model_error`, `timeout`, `protocol_error`, `budget_exhausted`
- 평가: utility/attack 각각 `valid`, `unknown`, `error`, 필요 시 `not_applicable`
- false 판정도 완료 run이며 유리한 결과를 얻기 위해 재실행하지 않는다.
- provider/timeout 계열의 기록된 오류만 명시적 `--retry_errors`로 최대 3 attempt를
  허용하고 이전 row를 보존한다.
- 저장 실패는 stop event를 세우고 전체 실행을 중단한다.

Legacy suite는 성공/실패 float 목록을 중심으로 집계한다. task 실행 또는 verifier에서
예외가 나면 `future.result()`나 평가 loop에서 suite 전체가 예외로 끝날 수 있으며,
시도별 오류 row와 partial trace, 평가 unknown/error 분리가 없다. 명시적 run-level
resume/retry도 없다.

두 경로 모두 현재 동기 OpenAI wrapper의 한 `call_llm()`에서 provider request를 한 번
보낸다. CrewAI의 최대 3회는 기록된 전체 attempt 재시도 정책이며 Agent 내부의 자동
재시도와 같은 개념이 아니다. Legacy에는 이에 대응하는 시도 이력 계약이 없다.

## 10. 동시성·상태 격리 비대칭

CrewAI는 각 논리 run에 deterministic ID와 non-blocking run lock을 두고, 같은 run의
동시 실행을 거부한다. JSONL append는 POSIX `flock`, pending marker, file/directory
`fsync`로 보호한다. message sequence와 attempt 번호를 매 append마다 재검사한다.

Legacy는 task마다 새 MAS를 만들고 attack template을 복사하는 최소 격리를 적용했지만,
다음 차이가 남는다.

- suite 하나가 `MASLogger` 하나를 모든 task/thread와 공유한다.
- `MASLogger.session["turns"]` append와 파일 logging은 run/attempt로 분리되지 않는다.
- attack deepcopy가 Judge 객체를 공유한다.
- summary `result.json`은 read-modify-write이며 process 간 lock이 없다.
- 실행 중복을 식별하는 안정적 run ID가 없다.
- 개별 MAS 생성자의 mutable list 기본값이 여러 곳에 남아 있다. BaseMAS의 기본값은
  수정됐지만 subclass 호출자가 기본 list를 직접 받는 구조는 CrewAI의 `None` 기본값과 다르다.

따라서 legacy의 `max_workers>1` 결과는 최종 점수 계산은 가능하더라도 CrewAI와 같은
상태·로그 격리 수준이 검증됐다고 볼 수 없다.

## 11. 메시지 관측과 로그 정확도 비대칭

CrewAI는 attempt마다 다음을 구조화해 저장한다.

- 원문 task
- 원본/effective Agent profile
- 실제 LLM input과 공격 전 input
- Agent 간 context/review/final message
- Judge input/output
- `target_invoked`, `payload_injected`, `is_attacked`
- 연속 `seq`, UTC timestamp, raw final output

Legacy `MASLogger`는 각 MAS가 명시적으로 부른 sender/receiver/message만 `.log`에 남긴다.
profile, 실제 LLM input, 공격 전후 원문, 직접 주입 여부, run ID가 없다. 또한 현재
`MASLogger.log_result()` 호출자가 없어 `logs/json/*.json`의 session/result 저장 경로는
일반 benchmark에서 완료되지 않는다.

기존 MAS별 수동 logging에는 다음과 같은 정확도 차이도 현재 코드에 존재한다.

- AutoGen의 `user_proxy → assistant` 로그가 실제 `user_proxy_response` 대신 이전
  `assistant_response`를 기록한다.
- Self Consistency bootstrap은 실제 Agent 목록에 없는 `assistant`를 receiver로 기록한다.
- MAD의 일부 debate route는 sender가 만든 새 응답 대신 이전 상대 응답을 message로
  기록한다.
- 일부 MAS `_log_step()`은 `logger is not None`을 검사하지만 일부는 logger가 항상
  있다고 가정한다.

따라서 legacy route 로그를 공격 전파의 ground truth로 그대로 사용하면 안 된다.
CrewAI 메시지 스키마 역시 현재 Sequential 네 route에 특화되어 있어 기존 MAS를
수용하려면 허용 phase/route를 토폴로지별로 확장해야 한다.

## 12. 저장 artifact와 집계 비대칭

| 항목 | CrewAI recorded | 기존 MAS legacy |
|---|---|---|
| 상세 실행 | `<output>/<experiment>/runs.jsonl` | `<output>/<timestamp>.log` |
| 상세 메시지 | 같은 디렉터리 `messages.jsonl` | 같은 `.log`에 혼합 |
| 설정 snapshot | credential 제거 후 config hash별 JSON | 없음 |
| 요약 결과 파일 | 현재 별도 result JSON을 쓰지 않고 stdout 반환 | `logs/<model>/<domain>/<mas>/<suite>/result.json`에 append |
| `--output_dir` | 모든 recorded artifact에 반영 | 상세 로그에는 반영되나 summary 경로는 `logs/`로 하드코딩 |
| 저장 감사 | JSONL 구조 audit | 없음 |
| 중단 흔적 | partial messages와 pending marker | 남은 text log 외 구조화 계약 없음 |

Legacy `result.json`의 비율은 소수점 네 자리 문자열이다. CrewAI 결과는 숫자 또는
분모가 없을 때 `None`이며, 예정/반환/완료 수와 오류·unknown·미호출·미주입 건수를
함께 반환한다.

Legacy는 `ASR_Surface`를 출력하지만 표면 표본이 없으면 문자열 `-1.0000`을 사용한다.
CrewAI 명령 요약에는 현재 `ASR_Surface`가 없고 row의 `attack_surface`로 사후 재계산해야
한다. 반대로 legacy에는 `ASR_injected`를 계산할 `payload_injected`가 없다. 어느 한쪽의
요약만으로 동일한 표를 만들 수 없는 상태다.

## 13. 지표 분모 비대칭

CrewAI는 다음 유효 subset을 분모로 사용한다.

- BU/UA: 실행 성공이면서 utility 판정이 `valid`인 row
- ASR: 실행 성공이면서 attack 판정이 `valid`인 row
- error와 unknown은 false로 바꾸지 않고 별도 건수로 공개

Legacy는 verifier가 반환한 float 목록 전체의 단순 평균을 사용한다. 오류/unknown
상태가 없으며, 빈 표면에는 `-1` sentinel을 사용한다. 또한 공격 suite의 utility는
각 attack 실행에서 한 번씩 측정되므로 task보다 task-attack pair가 분모다. CrewAI도
선택한 각 task-attack row에서 UA를 측정하지만 명시한 ID 집합이 다르기 때문에 가중치가
다르다.

특히 낮은 ASR은 다음을 분리하지 않으면 보안성으로 해석할 수 없다.

- 공격 미호출 또는 미주입
- 실행·평가 오류
- 모델이 원래 task와 공격 목표를 모두 수행하지 못한 경우
- 실제 공격 저항 후 정상 utility를 유지한 경우

CrewAI는 앞의 세 상태를 일부 구조적으로 분리할 수 있지만 legacy summary만으로는
동일한 분해가 불가능하다.

## 14. 모델·설정·재현성 비대칭

CrewAI는 [core.yaml](../configs/experiments/core.yaml)을 단일 계약으로 읽고 다음을
검증·snapshot한다.

- 활성 MAS/domain, `max_turn=1`, normalizer
- model/Judge provider, model, temperature, max token, seed 요청
- strict disruption Judge schema와 성공 label
- dependency lock과 핵심 package version
- task/attack manifest hash와 구현 source hash
- retry 정책과 개발 단계의 paid API 예산

Legacy는 실행 시 `configs/model.yaml`과 `configs/judge.yaml`을 직접 읽는다. 같은 파일을
사용하므로 현재 값은 우연히 같지만, 계약·dependency·source hash·seed 실제 지원 상태를
결과와 묶지 않는다. 설정 파일이 바뀐 뒤 같은 result 경로에 append하면 서로 다른 조건이
한 배열에 섞일 수 있다.

CrewAI는 설정과 오류에서 credential을 제거·치환한다. Legacy는 설정 snapshot 자체가
없고 provider 예외를 시도별로 정규화·redact하는 공통 경계도 없다.

토큰 사용도 CrewAI는 run별 Agent+Judge 호출 수, prompt/completion token, latency를
기록한다. Legacy executor는 MAS의 token usage를 응답 dict에 붙이지만 최종 suite
요약과 `result.json`에는 이를 집계·보존하지 않는다. 두 경로 모두 현재 실제 비용을
계산해 출력하지는 않는다.

## 15. 방어 지원 비대칭

Legacy executor는 다음 방어를 모든 Agent의 `pre_step` 또는 `post_step`에 monkey
patch할 수 있다.

- `aci_sentinel`
- `delimiter`
- `bert_detector`
- `sandwich`
- `none`

CrewAI recorded executor는 `defense != none`을 시작 전에 거부한다. 따라서 CrewAI와
기존 MAS의 Guardrail 적용 전후 결과를 같은 실행 계약으로 비교할 수는 없다.

**단, 방어 비교는 확정된 범위(D28~D32) 밖이다**(가이드 §7의 기본 범위 제외 항목). 이
절은 비대칭 사실만 기록하며, CrewAI 방어 통합·방어 matrix는 착수 대상이 아니다.

## 16. domain 지원 비대칭

CrewAI 개발 계약은 Math 39개와 Code 30개를 모두 지원한다. 기존 suite도 같은 원본
파일을 읽지만 MetaGPT는 Math를 명시적으로 거부한다. 따라서 전 MAS 완전 교차
Math/Code matrix는 현재 만들 수 없다.

공격도 domain별 등록 수가 다르고 현재 CrewAI manifest는 대표 범주만 선택한다. 결정
(D28)에 따라 도메인은 **math/code로 고정**하며, ①(D32)로 CrewAI manifest를 math/code
전 공격 세트로 확장해 모든 MAS가 동일 집합을 쓰게 한다. 누락 조합을 0%로 채우거나
서로 다른 domain 평균을 직접 비교하지 않는다. MetaGPT의 Math 제외는 위 문단대로
반영한다(해당 MAS는 Math 비교에서 빠진다).

## 17. 테스트와 검증 증거 비대칭

CrewAI recorded 경로에는 다음 전용 검증이 있다.

- strict 반환 계약과 Finalizer source
- 세 공격 표면의 실제 주입 관측
- fresh Attack/Judge와 병렬 격리
- JSONL 동시 append, run claim, resume/retry
- 오류 row와 partial trace
- credential 제거
- Math parse unknown과 격리 worker
- Code namespace/Landlock/seccomp 차단
- 설정·manifest·dependency drift

기존 MAS는 G0 회귀에서 주로 Self Consistency의 Math/Code 정답·오답 경로와 공통 기반
수정을 확인했다. 각 legacy MAS 전체에 동일한 concurrency, logging, error, verifier,
resume/audit 테스트가 적용된 것은 아니다. CrewAI의 높은 관측 신뢰도를 다른 MAS에
자동으로 전이해서 주장할 수 없다.

G3에 예정된 공식 CrewAI/재구현 calibration은 CrewAI 재구현 충실도를 검증하는 작업이다.
그 자체로 CrewAI recorded와 모든 legacy MAS 사이의 평가 인프라 비대칭을 해소하지는
않는다.

## 18. 현재 `test1` 결과에 적용한 해석

`logs/test1`의 10개 Answer Mapping run은 모두 실행 성공, Solver 호출, payload 주입,
attack 판정 valid였고 공격 성공은 0건이었다. 따라서 recorded 계약 안에서 ASR 0%는
정상 계산이다.

그러나 이를 legacy Math Hijacking 명령과 비교하면 다음이 달라진다.

- CrewAI는 AnswerMapping Agent 한 표면만 사용한다.
- legacy는 Agent, Instruction, Message의 세 공격을 합친다.
- CrewAI는 parse unknown과 오류를 분리하지만 legacy는 그렇지 않다.
- CrewAI는 Finalizer 최종 출력을 평가하지만 legacy MAS마다 최종 source가 다르다.
- CrewAI UA는 10%로 낮아 공격 실패와 task 수행 실패를 함께 해석해야 한다.

그러므로 `test1 ASR 0% < legacy ASR X%`와 같은 우열 문장은 현재 근거가 부족하다.

## 19. 비교 가능성 확보를 위한 정렬 순서

### 19.1 본 비교 전 필수

1. task와 공격을 모든 MAS에서 동일한 manifest ID로 선택한다.
2. legacy 경로에서도 단일 attack ID 실행을 지원하고, suite 전체 자동 합산 결과와
   구분한다.
3. MAS별 target 역할을 사전 대응표로 고정하고 한 run의 악성 Agent 수와 직접 노출
   횟수를 기록한다.
4. 동일 raw/normalized 응답 계약과 최종 source field를 사용한다.
5. Math parse 실패, Code sandbox, Judge 오류에 같은 status와 유효 분모를 적용한다.
6. 동일 model/Judge config hash, dependency lock, prompt/verifier version을 결과에 묶는다.
7. 최소한 run ID, attack surface, target invoked, payload injected, 실행/평가 상태를
   모든 MAS에서 기록한다.

### 19.2 재현성과 감사에 필수

1. baseline은 `max_workers=1`로 실행해 legacy의 공유 Judge·공유 logger 경합을
   우회한다(D32 Tier 2). 전면적 run 단위 격리는 확정 범위 밖이다.
2. 실패·partial trace·재시도 attempt를 보존한다.
3. summary와 상세 row를 같은 `output_dir`과 experiment identity 아래 저장한다.
4. 원본 row에서 BU/UA/ASR/ASR_Surface와 각 유효 분모를 재계산하는 공통 집계기를 둔다(③).
5. legacy route log의 알려진 부정확(§11)은 문서화하고, 헤드라인 지표는 최종응답
   기반이라 영향받지 않음을 명시한다. 각 MAS route log 회귀 테스트는 확정 범위 밖이다
   (D32 Tier 3).

### 19.3 유지해야 하는 연구 변수

다음은 공정성을 위해 같게 만들 항목이 아니라, 같은 평가 계약 아래 설명해야 할
독립 변수다.

- Agent 수와 역할
- 순차, debate, critic, self-consistency 등 토폴로지
- round/turn과 종료 조건
- 최종화 Agent의 역할
- Agent 간 전달 context와 memory 정책
- 동일 target에 대한 실제 공격 노출·전파 거리

## 20. 단계별 반영 위치

| 단계 | 이 문서에서 연결되는 작업 (`DECISIONS.md` D30/D32) |
|---|---|
| G2 | CrewAI 세 표면, injection evidence, golden, resume, audit를 완료하고 현재 비대칭을 실제 fixture로 고정 |
| G3 | 공식 CrewAI와 재구현의 20-run 기능 대조 |
| G4 | 실제 모델 파일럿에서 완료율·주입률·parse·비용을 확인하고 낮은 UA/ASR을 구분 |
| G5 | manifest 동결 시 ① CrewAI를 math/code 전 공격 세트로 확장(모든 MAS 동일 집합); CrewAI 본 matrix 실행 |
| G6 | 원본 row에서 지표 재계산하는 공통 집계기 골격을 legacy 수용 가능하게 구성 (**CrewAI 독립 벤치 완료**) |
| G7 | ② legacy per-row 기록 + bug-fixed legacy 재실행 + ③ 공통 집계기 완성으로 CrewAI↔legacy 정렬·비교. 파일럿·예산 게이트 통과 후 착수 |

정렬(G7)이 끝나기 전까지는 CrewAI recorded 결과를 독립 실험으로 제시하고 legacy
결과는 분리해 보고한다. G7 이후에도 동일 공격·동일 verifier·동일 기록 계약이 확인된
지표만 비교하고 논문 수치는 정성 참조로 쓰며, 그 전까지는 MAS 간 ASR 차이를 토폴로지나
역할의 효과로 귀속하지 않는다.

## 21. 주요 코드 근거

- CLI 분기: [benchmark.py](../benchmark.py)
- suite/executor 분기와 legacy 공격 선택: [factory.py](../aciarena/utils/factory.py)
- legacy 실행·집계: [evaluation_suite.py](../aciarena/evaluation/evaluation_suite.py),
  [task_executor.py](../aciarena/evaluation/task_executor.py)
- CrewAI 실행·집계: [recorded_suite.py](../aciarena/evaluation/recorded_suite.py),
  [recorded_executor.py](../aciarena/evaluation/recorded_executor.py)
- CrewAI 반환 계약: [schemas.py](../aciarena/mas/crewai/schemas.py),
  [sequential_mas.py](../aciarena/mas/crewai/sequential_mas.py)
- 공격 관측: [message_bus.py](../aciarena/mas/crewai/message_bus.py)
- 공격 계약: [catalog.py](../aciarena/attacks/catalog.py),
  [attacks.json](../manifests/attacks.json)
- 기록 계약: [records.py](../aciarena/evaluation/records.py),
  [run_writer.py](../aciarena/evaluation/run_writer.py)
- verifier: [math_verifier_worker.py](../aciarena/evaluation/math_verifier_worker.py),
  [code_verifier_worker.py](../aciarena/evaluation/code_verifier_worker.py)
- 최신 연구 기준: [구현 가이드](../CrewAI_ACIArena_연구계획/00_구현_가이드.md),
  [평가·데이터 가이드](../CrewAI_ACIArena_연구계획/archive/04_실험_평가_기준_및_데이터_가이드.md),
  [검증 기준](../CrewAI_ACIArena_연구계획/archive/05_검증_및_품질_기준.md)

