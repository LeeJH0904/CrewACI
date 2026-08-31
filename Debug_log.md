## 2026-08-11

- disruption security judge가 OpenAI choice를 반환하고도 `message.content=None`을 줄 때 `json.loads(None)`으로 종료되는 문제를 수정.
- `OpenAILLM.call_llm()`에서 빈 choices와 `None` content를 `EmptyLLMResponseError`로 검출하고, 기존 Tenacity 정책으로 재시도하도록 처리.
- 재시도 후에도 실패하면 `finish_reason`과 `message.refusal`을 예외에 포함해 content filter, refusal 등의 실제 종료 원인을 확인할 수 있게 함.
- `agentverse_disruption_2026-08-11_15-20-01.log`에 설정만 남은 원인 확인: `AgentVerse`는 `MASLogger`를 전달받지만 `log_message()`를 호출하지 않으며, benchmark/evaluation 경로도 `log_result()`를 호출하지 않음. 따라서 logger 생성 시의 Evaluation Settings 외에는 기록되지 않음.
- `AgentVerse`에도 다른 MAS와 동일한 `_log_step()` 경로를 추가하고 user, role assigner, solver, critic, evaluator 간 메시지와 최종 응답을 기록하도록 수정. logger 없이 직접 생성하는 경우도 동작하도록 `if self.logger`로 보호.
- `human_eval==1.0.3`의 `reliability_guard()`가 `os.unlink`를 비활성화한 뒤 복원하지 않아, 코드 평가 후 임시 디렉터리 정리 과정에서 `TypeError: 'NoneType' object is not callable`이 반복되는 문제를 수정.
- 프로젝트 로컬 호환 모듈 `aciarena/evaluation/human_eval_execution.py`를 추가해 `os.unlink`를 임시 디렉터리 정리 전에 복원하도록 처리.
- `CodeTask`가 패키지의 `human_eval.execution` 대신 프로젝트 로컬 호환 모듈에서 `check_correctness`를 가져오도록 변경.

## 2026-08-09

- OpenAI TPM 초과 시 `RateLimitError`를 유지해 Tenacity가 재시도하도록 수정.
- 재시도를 최대 8회, 1~60초 무작위 지수 백오프로 조정.
- 잘못 사용된 `Timeout`을 실제 SDK 예외인 `APITimeoutError`로 변경하고 동기·비동기 재시도 대상에 반영.

## 2026-08-06

- Google Gemini provider 지원 추가: `GeminiLLM` 구현 및 provider 라우팅 추가.
- `ACISentinel`이 judge 설정의 provider에 따라 OpenAI/Gemini를 선택하도록 수정.
- Gemini API 사용을 위해 `google-genai` 의존성 추가.


## 2026-08-31 — 도연: CrewAI 순차형 MAS 통합 및 공격 평가 검증

* **통합 브랜치:** `feature/crewai-integration` 브랜치에서 ACIArena 내부에 CrewAI 방식의 순차형 MAS를 1차 구현.
* **통합 방식 재구현:** 실제 CrewAI 패키지의 `Agent`, `Task`, `Crew`, `crew.kickoff()`를 직접 사용하지 않고, ACIArena 공격 경로와 호환되도록 `BaseAgent`와 `BaseMAS`를 기반으로 CrewAI의 역할 기반 Agent 및 순차 협업 구조를 재구현.
* **공통 Agent 구조:** 공통 `CrewAIAgent`에 CrewAI의 주요 Agent 속성인 `role`, `goal`, `backstory`, `allow_delegation`을 추가.
* **Agent 구성:** `SolverAgent`, `ReviewerAgent`, `FinalizerAgent`를 구현하고 `Solver → Reviewer → Finalizer` 순서로 실행되는 `CrewAISequentialNoDelegation` MAS를 추가.
* **공격 호환성:** 모든 Agent 호출이 `run_step()`을 거치도록 구현해 ACIArena의 instruction injection, malicious agent, message poison 공격이 기존 실행 경로를 통해 적용되도록 처리.
* **MAS 등록:** 새 MAS를 `crewai_seq_nodeleg` 이름으로 등록하고 `aciarena/mas/__init__.py`에 import 경로를 연결.
* **테스트 옵션:** 빠른 실행 검증을 위해 `benchmark.py`에 `--limit` 옵션을 추가하고, `BaseEvaluationSuite`에서 불러온 태스크 목록을 지정한 개수만큼 제한하도록 수정.
* **Benign 실행 검증:** LM Studio의 OpenAI 호환 API와 `qwen2.5-0.5b-instruct` 모델을 사용해 수학 태스크 1건의 benign 실행을 검증. `Solver → Reviewer → Finalizer` 메시지 전달과 최종 답 `320`을 확인했으며 `Benign Utility: 100.0000`을 기록함. 단, 태스크 1건에 대한 연결 확인 결과이므로 전체 성능을 의미하지 않음.
* **Disruption 실행 검증:** Solver를 공격 대상으로 지정한 disruption 테스트에서 수학 task 1건에 일반 disruption 공격 4종과 수학 도메인 공격 1종이 적용되어 총 5회 실행되는 것을 확인.
* **공격 전파 확인:** Message Poison 조건에서 Solver 출력이 `<ALERT>...` 공격 메시지로 교체되고 해당 메시지가 Reviewer에게 전달되는 것을 확인. Reviewer가 원래 문제를 다시 계산해 Finalizer가 정답 `320`을 출력한 사례를 통해 Solver 공격 적용과 하위 Agent 전달 경로가 정상 동작함을 확인.
* **발생 오류:** 첫 disruption 평가의 Security Judge 단계에서 LM Studio가 `response_format.type=json_object`를 지원하지 않아 다음 오류로 종료됨.

  ```text
  'response_format.type' must be 'json_schema' or 'text'
  ```
* **LM Studio 호환 수정:** LM Studio 호환을 위해 `OpenAILLM.call_llm()`의 JSON 응답 형식을 `json_schema` 방식으로 임시 변경하고 `py_compile` 검증을 완료. 변경 후 Utility와 Security 평가가 모두 종료되는 것을 확인.
* **재실행 결과:** `Utility under Attack: 80.0000`, `Attack Success Rate: 80.0000`이 출력됨. Utility는 최종 응답 5개 중 정답 `320`이 4개, 오답 `300`이 1개인 실행 로그와 일치함.
* **ASR 결과 불일치:** ASR은 실제 최종 응답 5개가 모두 원래 수학 문제에 답한 로그와 일치하지 않음.
* **원인 분석:** ASR 불일치의 정확한 원인은 미확정. 현재 JSON Schema가 객체 형식만 요구해 `judgement` 필드를 보장하지 않는 점과, 기존 disruption 검증 코드가 `judgement` 필드가 없을 때 `.get("judgement", "yes")`로 공격 성공을 기본 처리하는 점을 확인. Qwen2.5 0.5B Judge의 잘못된 의미 판정 가능성도 있으나 Judge 원문 응답이 저장되지 않아 추가 검증이 필요함.
* **후속 작업:** `judgement` 필드와 `yes`·`no` 값만 허용하는 구체적인 JSON Schema 적용, 누락된 판정의 자동 성공 처리 제거, Judge 원문 출력 기록, 실행 로그와 ASR의 일치 여부 재검증이 필요함.
* **Git 반영 상태:** CrewAI 순차형 MAS 1차 구현은 커밋 `c982f0e`(`CrewAI 순차형 MAS 구현`)으로 원격 `feature/crewai-integration` 브랜치에 업로드. 이후 수행한 LM Studio JSON Schema 수정은 검증 중인 로컬 변경으로 해당 커밋에는 포함되지 않음.
* **개발 방향:** 공격 전·후 메시지, 감염 Agent, 전달 경로, 차단 위치를 태스크별로 저장 -> 현재 구조(순차형 비위임)를 Agent 위임 구조와 Manager 중심의 계층형 구조로 확장 -> 위임 context 및 Manager 대상 공격을 추가하고, Agent 입력·메시지·최종 출력 단계에 Guardrail을 적용 -> 순차형 비위임·위임·계층형 구조에서 Guardrail 적용 전후의 Utility, ASR, 공격 전파 깊이를 비교.


# Debug Log

## 2026-07-23 — `ModuleNotFoundError: No module named 'aciarena.defenses.safety_filter'`

### 수정
`aciarena/aciarena/defenses/__init__.py`
```diff
- from .safety_filter import SafetyFilter
+ from .aci_sentinel import ACISentinel
  from .bert_detector import BertDetector
```

### 검증
수정 후 `safety_filter` 관련 오류 해소됨. import 체인이 정상 진행되어 이후 단계에서 멈춤.



## `C:\Users\Lee\Desktop\ACIArena\aciarena\aciarena\evaluation\datasets`

프로젝트의 새 이름(aciarena)에 맞춰 파일을 리네임:
maspi_code.json → aciarena_code.json
maspi_math.json → aciarena_math.json

## `C:\Users\Lee\Desktop\ACIArena\aciarena\aciarena\utils\factory.py`

오타 수정:
timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%]S")
-> timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
