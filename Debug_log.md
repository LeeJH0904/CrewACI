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

## 2026-08-31

- CrewAI 통합을 위한 MAS scaffold 추가: `aciarena/mas/crewai/__init__.py`와 `aciarena/mas/crewai/crewai_mas.py` 생성.
- `CrewAIMAS`를 `BaseMAS` 패턴에 맞춰 구현하고, `@register_mas("crewai")`로 registry에 등록.
- `aciarena/mas/__init__.py`에서 `CrewAIMAS`를 import하도록 연결해 프로젝트 수준에서 접근 가능하게 구성.
- `python3 -m compileall aciarena` 검증 결과, 새 CrewAI 코드의 문법 오류는 없었음.
- CrewAI 설치 검증 완료: `pip install crewai` 후 `pip show crewai`에서 `Version: 1.15.18` 확인.
- 런타임 검증 단계에서 의존성 충돌 발견: 현재 프로젝트는 `openai==1.63.2`, `pydantic==2.10.6` 기준인데, CrewAI 1.15.18는 더 최신 OpenAI/Pydantic 범위를 요구함.
- 추가로 프로젝트 전체 import 단계에서 `torch`가 없어 `ModuleNotFoundError: No module named 'torch'` 발생. 이건 기존 프로젝트 환경 의존성이 아직 해결되지 않았음을 의미함.
- 결론: CrewAI 통합 구조는 마련되었지만, 실제 benchmark 실행까지 가려면 프로젝트 의존성 버전 정합성 및 `torch` 설치/호환성 해결이 필요함.