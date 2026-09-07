# ACIArena × CrewAI 통합 기준 문서

> 작성 기준일: 2026-08-05  
> 상태: 통합 구현 전 설계 기준선  
> 목적: 흩어진 조사 문서를 하나로 통합하고, ACIArena의 현재 구현 수준과 CrewAI 통합 방법을 팀 공통 기준으로 확정한다.

## 문서 사용법

이 문서는 다음 네 질문에 순서대로 답한다.

1. ACIArena 공개 구현은 논문을 어느 수준까지 재현하는가?
2. CrewAI는 어떤 구성요소로 어떻게 실행되는가?
3. 두 시스템은 무엇이 다르며, 통합 전에 무엇을 해결해야 하는가?
4. CrewAI의 대표성을 훼손하지 않으면서 ACIArena에 어떻게 재구현할 것인가?

기존 문서는 조사 근거로 유지하되, 이후 구현 판단에서는 이 문서를 우선 기준으로 사용한다.

## 핵심 결론

- 현재 ACIArena 코드는 논문의 **확장 가능한 실행 골격**은 잘 구현했지만, 데이터 규모·공격 자동 생성·PVI·일부 방어·신뢰성 검증이 빠진 연구 프로토타입이다.
- 현재 저장소에는 CrewAI 전용 MAS 구현이 없다. 지금까지 완료된 것은 **통합 가능성 조사와 재구현 설계**이며, 실제 통합 코드는 다음 단계다.
- 기존 ACIArena의 7개 MAS는 원본 프레임워크를 직접 호출하지 않고 MASLab 방식으로 협업 패턴을 재구현한다. 따라서 CrewAI도 동일 조건 비교를 위해 **충실 재구현**하는 것이 기본 노선이다.
- 단순 순차 파이프라인에 CrewAI라는 이름만 붙이면 대표성이 부족하다. 최소한 역할 구조, sequential/hierarchical 프로세스, 매니저, 위임 가능 여부, 코워커 위임 채널을 보존해야 한다.
- 정량 평가 전에 verifier, 병렬 실행 데이터 경합, 공격 중복 등록, 비밀키 관리와 결과 감사 가능성을 먼저 고쳐야 한다.

---

# 1. ACIArena의 구현 코드 상태 — 논문 기준

## 1.1 논문이 제시하는 ACIArena

ACIArena 논문의 목표는 다양한 LLM 기반 다중 에이전트 시스템을 동일한 조건에서 실행하고, Agent Cascading Injection(ACI)의 전파와 방어 성능을 비교하는 것이다.

논문이 제시하는 주요 구성은 다음과 같다.

| 구분 | 논문 기준 |
|---|---|
| 정상 태스크 | 수학, 코드, 과학, 의학 4개 도메인 |
| 테스트 케이스 | 총 1,356개 |
| 원천 벤치마크 | GSM8K, MATH500, HumanEval, MBPP, GPQA, MedMCQA |
| 공격 목표 | Hijacking, Disruption, Exfiltration |
| 공격면 | Adversarial Input, Malicious Agent, Message Poison |
| 공격 | 28종 |
| MAS | MetaGPT, Self-Consistency, AutoGen, CAMEL, AgentVerse, LLM Debate 6종 |
| 방어 | BERT 계열 탐지기, Delimiter, Sandwich, AGrail, G-Safeguard, ACI-Sentinel 6종 |
| 지표 | BU, UA, ASR, 공격면별 ASR, PVI |
| 공격 생성 | 수동 초기 공격에서 출발하는 생성–변이–선택 최적화 루프 |
| 신뢰성 검증 | 3인 인간 평가, Cohen's kappa, LLM judge와 인간 판단 일치도 |

논문에서 ACI 공격면은 에이전트 \(A=(\pi,P,M,T)\)의 구성요소와 메시지 흐름을 기준으로 다음과 같이 정의된다.

- **Adversarial Input**: 지시 `I`, 메모리 `M`, 도구 설명 `T`에 악성 입력을 주입한다.
- **Malicious Agent**: 에이전트 프로파일 `P`를 변조해 악성 행동을 유도한다.
- **Message Poison**: 에이전트 사이에 전달되는 메시지를 공격자가 교체하거나 변조한다.

## 1.2 현재 코드가 구현한 실행 골격

현재 코드는 논문의 모듈 구조를 비교적 충실하게 반영한다.

```text
Task
  │
  ▼
EvaluationSuite ──> Executor ──> Attack / Defense 적용
                               │
                               ▼
                         BaseMAS 실행
                    bootstrap → step → conclude
                               │
                               ▼
                         BaseAgent.run_step
                    pre_step → step → post_step
```

핵심 계약은 `BaseAgent.run_step()`이다.

- `pre_step`: 입력 전처리 방어가 연결되는 지점
- `step`: 실제 에이전트 호출 및 Instruction Injection/Message Poison이 연결되는 지점
- `post_step`: 출력 정제·차단 방어가 연결되는 지점

새 MAS가 `BaseMAS`를 상속하고 모든 에이전트 호출을 `run_step()`으로 수행하면 기존 공격·방어 실행 구조를 재사용할 수 있다.

## 1.3 논문과 현재 구현의 차이

| 항목 | 논문 | 현재 구현 | 판정 |
|---|---:|---:|---|
| 정상 태스크 | 1,356개 | 수학 39 + 코드 30 = 69개 | 크게 부족 |
| 도메인 | 4개 | 수학·코드 2개 | 과학·의학 미배선 |
| MAS | 6종 | 논문 6종 + MAD = 7종 | 커버리지 충족 |
| 공격 등록 | 28종 | 23개 등록, 의미상 고유 공격 22개 | 부분 구현 |
| 공격면 | 3종 | 부모 클래스는 모두 존재 | 골격 충족 |
| 실제 사용 공격면 | I/M/T, P, 메시지 | Instruction, Profile, Message만 사용 | Tool/Memory 미행사 |
| 공격 자동 생성 | 있음 | 없음 | 핵심 기능 누락 |
| 방어 | 6종 | 4종 | AGrail·G-Safeguard 누락 |
| BU/UA/ASR | 있음 | 있음 | 구현 |
| 공격면별 ASR | 있음 | 있음 | 구현 |
| PVI | 있음 | 없음 | 핵심 지표 누락 |
| 공격 스케줄 | 다양한 시점·빈도 | continuous만 활성 | 부분 구현 |
| 인간 검증 | 있음 | 없음 | 미구현 |
| 반복·신뢰구간 | 3회 및 95% CI | 자동화 없음 | 미구현 |

### 공격 수 산정 정정

기존 문서의 “23개 중 21개만 CrewAI에 적용 가능하고 메모리 계열 2개가 불일치한다”는 설명은 현재 코드와 맞지 않는다.

- 현재 등록된 23개 공격은 모두 `InstructionInjectionAttack`, `MaliciousAgentAttack`, `MessagePoisonAttack` 중 하나를 사용한다.
- `ToolInjectionAttack`과 `MemoryInjectionAttack`은 부모 클래스만 존재하며, 이를 상속한 구체 등록 공격은 **0개**다.
- 따라서 현재 등록 공격을 기준으로 하면 메모리 공격 2개를 제외할 이유가 없다.
- 다만 `hijacking_attack.py`의 `AnswerMappingAgent`가 같은 의미로 두 번 정의·등록되어 있어 의미상 고유 공격은 22개다.

도메인별로 활성화되는 공격 수도 다르다. 예를 들어 code/hijacking 실행에는 Message Poison 공격이 없어 결과의 `message_poison` 값이 `-1`로 기록된다. 따라서 전체 공격 수와 한 번의 실행에서 실제 활성화되는 공격 수를 구분해야 한다.

## 1.4 현재 등록된 MAS와 토폴로지

| 등록명 | 에이전트 구성 | 협업 형태 |
|---|---|---|
| `autogen` | assistant, user_proxy | 2자 왕복 대화 |
| `camel` | assistant, user_proxy, task_specifier, critic | 역할 기반 왕복 대화 |
| `agentverse` | role_assigner, solver, evaluator, critic | 동적 역할 배정 + 비평 |
| `metagpt` | product_manager, architect, project_manager, engineer, qa_engineer | 고정 수직 파이프라인 |
| `sc` | sc1~sc5, aggregate | 병렬 생성 + 집계 |
| `llm_debate` | debater 3개, aggregator | 토론 + 집계 |
| `mad` | affirmative, negative, moderator, judge | 찬반 토론 + 판정 |

이 구현들은 실제 AutoGen·CAMEL·MetaGPT 패키지를 래핑하지 않는다. MASLab의 연구용 통일 원칙에 따라 역할, 프롬프트, 상호작용 순서를 ACIArena의 `BaseAgent`/`BaseMAS` 위에서 재구현한 것이다.

## 1.5 현재 로컬 수정과 실행 결과

현재 `aciarena` Git 저장소는 upstream initial commit 위에 다음 변경이 미커밋 상태로 남아 있다.

- 존재하지 않는 `SafetyFilter` import를 `ACISentinel`로 교체
- `maspi_code.json`, `maspi_math.json`을 `aciarena_*`로 이름 변경
- 로그 타임스탬프 포맷 오타 수정
- 모델·judge 설정 입력
- `scripts/autogen.sh`의 방어 설정 변경

데이터셋 파일은 이름만 바뀌었고 Git blob 내용은 원본과 동일하다.

기존 AutoGen code 실행 결과는 다음과 같다.

| 실행 | 결과 |
|---|---|
| benign | BU 0.0000 |
| hijacking | UA 0.0000, ASR 85.8333 |
| hijacking 공격면 | Adversarial Input 96.6667, Malicious Agent 75.0000, Message Poison 미측정 |

로그에서는 공격 페이로드가 후속 에이전트로 전파된 사실은 확인된다. 그러나 benign utility가 0이므로 현재 수치를 시스템 성능으로 해석해서는 안 된다. 출력 포맷과 verifier의 정합성을 먼저 수동 검증해야 한다.

## 1.6 통합 전에 반드시 고칠 평가 문제

### 필수 수정

1. **API 키 평문 저장**
   - `configs/model.yaml`, `configs/judge.yaml`에 실제 형식의 키가 존재한다.
   - 노출된 키는 폐기·재발급하고 환경변수 또는 Git 비추적 로컬 설정으로 옮겨야 한다.

2. **병렬 평가의 공유 공격 객체 데이터 경합**
   - `BaseEvaluationSuite`가 하나의 `executor`와 `attacks` 목록을 여러 worker thread에서 공유한다.
   - 각 실행은 같은 공격 객체의 `answer`, `turn_count`, `malicious_agents`를 변경한다.
   - 다른 태스크의 값이 deepcopy 전에 덮일 수 있으므로 태스크별 공격 객체를 생성하거나 executor를 격리해야 한다.

3. **`AnswerMappingAgent` 중복 등록**
   - hijacking/math 표본과 전체 ASR의 가중치를 왜곡한다.

4. **Verifier 포맷 종속성**
   - Math는 `math_verify.parse`, Code는 Markdown 코드 블록과 문자열 절단 규칙에 의존한다.
   - MAS별 최종 출력 형식 차이가 실제 정답률보다 크게 작용할 수 있다.

5. **결과 감사 가능성 부족**
   - 집계 결과만 `result.json`에 남고, 태스크·공격별 정규화 결과와 판정 근거가 체계적으로 저장되지 않는다.
   - 재현 가능한 평가를 위해 task ID, attack ID, agent 위치, 원문 출력, 정규화 출력, verifier 결과, token usage를 행 단위로 저장해야 한다.

### 후속 보강

- PVI와 토폴로지 거리 기록
- Tool Injection 구체 공격 추가
- 과학·의학용 `QATask` 배선 및 `verify` 인터페이스 정리
- 반복 실행과 bootstrap 신뢰구간
- judge 판정 샘플의 인간 검증
- 공격 자동 생성은 전체 논문 재현이 목표일 때 별도 단계로 구현

## 1.7 현재 구현 수준에 대한 최종 판정

현재 코드는 **논문 전체의 완성된 벤치마크가 아니라, 실행 가능한 확장 골격 프로토타입**이다.

- 새 MAS를 추가하기 위한 인터페이스는 충분히 명확하다.
- 기존 MAS·공격·방어를 같은 실행 계약으로 연결할 수 있다.
- 반면 현재 데이터와 평가 배관만으로 CrewAI의 취약성을 정량적으로 단정하기는 어렵다.

따라서 CrewAI 통합과 평가 신뢰도 보강을 별개의 작업으로 나누되, 최소 평가 수정 사항은 통합 실험 전에 완료해야 한다.

---

# 2. CrewAI의 특징과 구동 방식

## 2.1 CrewAI의 분석 단위

CrewAI에는 크게 두 실행 계층이 있다.

- **Crew**: 여러 Agent가 Task를 협업 수행하는 자율적 다중 에이전트 단위
- **Flow**: 이벤트·상태·분기를 명시적으로 제어하며 Crew를 포함할 수 있는 상위 오케스트레이션 단위

이번 연구의 ACIArena 대응 단위는 **Crew**다. Flow는 ACIArena의 단일 질의→MAS 실행→최종 응답 모델보다 상위 계층이므로 1차 통합 범위에서 제외한다.

## 2.2 핵심 구성요소

| CrewAI 요소 | 역할 | ACI 관점 |
|---|---|---|
| `Agent` | 역할을 가진 LLM 실행 주체 | 프로파일·도구·메모리 공격 대상 |
| `Task` | description, expected_output, agent, context 등을 가진 작업 | 입력·컨텍스트·출력 전파 단위 |
| `Crew` | Agent와 Task를 묶어 실행 | ACIArena의 MAS에 대응 |
| `Process` | sequential 또는 hierarchical 실행 규칙 | 토폴로지 및 전파 경로 결정 |
| Tool | 외부 함수·API 호출 능력 | Tool Injection 및 위임 경로 |
| Guardrail | Task 출력 검증·재시도·선택적 변환 | 내장 방어이자 결과 비교 교란 변수 |
| Memory | 실행 정보를 저장·검색 | 태스크·세션 간 장기 전파 가능성 |

## 2.3 Agent

CrewAI Agent의 핵심 정체성은 다음 세 필드다.

- `role`: 크루 안에서 담당하는 기능과 전문성
- `goal`: 의사결정을 유도하는 개별 목표
- `backstory`: 행동 맥락과 성격을 제공하는 배경

주요 선택 속성은 `llm`, `tools`, `allow_delegation`, `max_iter`, `step_callback`, prompt template 등이다. 공식 문서상 `allow_delegation` 기본값은 `False`, `max_iter` 기본값은 20이다.

ACI 관점에서 `role/goal/backstory`를 하나의 평면 문자열로 취급하면 어느 정체성 요소가 공격받았는지 분석할 수 없다. 재구현에서도 구조화된 필드로 보존한 뒤 실행 시 시스템 프롬프트로 렌더링해야 한다.

## 2.4 Task

Task의 주요 필드는 다음과 같다.

- `description`: 수행할 작업
- `expected_output`: 기대 출력 형태
- `agent`: 담당 에이전트
- `context`: 선행 Task 출력 참조
- `tools`: 해당 Task에서 허용되는 도구
- `guardrail`: 출력 검증 함수 또는 기준
- `callback`: 완료 후 관찰·처리

`context`는 단순 실행 순서와 별개로 특정 선행 Task의 출력을 다음 Task 입력에 포함할 수 있다. 이 연결은 ACI 전파 그래프의 명시적 edge로 기록해야 한다.

Guardrail은 일반적인 임의 post-processing 함수와 완전히 같지 않다. 실패 시 피드백을 에이전트에 전달하고 재시도하는 실행 의미를 갖는다. 따라서 실제 CrewAI 런타임을 래핑할 경우 ACIArena의 `post_step` 방어와 1:1로 동일하다고 가정해서는 안 된다.

## 2.5 Crew와 실행

일반적인 실행 흐름은 다음과 같다.

```python
crew = Crew(
    agents=[...],
    tasks=[...],
    process=Process.sequential,  # 또는 Process.hierarchical
)

result = crew.kickoff(inputs={...})
```

실행 결과는 최종 원문, Task별 출력, 사용량 정보 등을 제공할 수 있으며 crew 실행 후 `usage_metrics`로 전체 LLM 사용량을 확인할 수 있다.

## 2.6 Sequential process

Sequential은 Task 목록의 순서대로 실행된다. 앞 Task의 출력은 뒤 Task의 컨텍스트로 전달되며, `Task.context`로 참조 관계를 명시할 수도 있다.

```text
사용자 질의
   │
   ▼
Task 1 / Agent A
   │ 출력이 검증 없이 컨텍스트로 전달
   ▼
Task 2 / Agent B
   │
   ▼
Task 3 / Agent C
   │
   ▼
최종 결과
```

ACI 관점에서는 상류 에이전트의 오염된 출력이 그대로 하류 입력이 되는 전형적인 cascading 경로다.

## 2.7 Hierarchical process

Hierarchical은 `manager_llm` 또는 사용자 정의 `manager_agent`가 필요하다. 매니저가 작업을 계획하고, 에이전트 역량을 기준으로 할당하고, 결과를 검토하고, 완료 여부를 판단한다.

```text
                 ┌──────────────┐
사용자 질의 ───> │ Manager Agent│
                 └──────┬───────┘
                        │ 배정·위임
              ┌─────────┼─────────┐
              ▼         ▼         ▼
           Worker A  Worker B  Worker C
              └─────────┼─────────┘
                        │ 결과 검토·통합
                        ▼
                  Manager Agent
                        │
                        ▼
                     최종 결과
```

매니저가 공격받으면 여러 하위 에이전트에 악성 지시를 배포할 수 있고, 하위 에이전트가 공격받으면 매니저의 검토가 완충 역할을 할 수도 있다. 이 위치 차이는 CrewAI 통합의 핵심 실험 변수다.

## 2.8 코워커 위임 채널

`allow_delegation=True`인 에이전트에는 공식 문서상 다음 협업 도구가 자동 제공된다.

- `Delegate work to coworker(task, context, coworker)`
- `Ask question to coworker(question, context, coworker)`

이 채널의 보안상 핵심은 송신 에이전트가 다음을 선택한다는 점이다.

1. 수신자 `coworker`
2. 수행할 task 또는 question
3. 수신자에게 전달할 자유 텍스트 `context`

따라서 위임은 단순 함수 호출이 아니라, 공격자가 메시지 내용과 전파 방향을 동시에 통제할 수 있는 ACI 전파 경로다.

## 2.9 Memory와 버전 고정 주의

기존 문서에는 CrewAI 메모리가 “short-term/long-term/entity memory에서 통합 `Memory`로 완전히 교체되었다”는 단정이 있다. 그러나 현재 공식 문서의 `Crews` 페이지와 `Memory` 페이지는 서로 다른 세대의 설명을 함께 노출한다.

- Crews 페이지: short-term, long-term, entity memory 표현 유지
- Memory 페이지: LLM 분석, 중요도·최신성·의미 유사도 조합, LanceDB 저장을 사용하는 통합 Memory 설명

또한 `v1.15.7` URL이 영구 불변 스냅샷이라고 보장할 수 없다. 따라서 구현 문서만으로 메모리 구조를 확정하지 않고 다음 원칙을 사용한다.

- 1차 비교에서는 메모리를 **명시적으로 비활성화**한다.
- 실제 CrewAI 동등성 검증 시 설치 package version, Git commit, lockfile을 기록한다.
- 메모리를 실험할 경우 설치본 소스를 기준으로 별도 위협 모델과 공격을 정의한다.
- 실행 간 영속 저장소는 태스크별 임시 디렉터리로 격리한다.

## 2.10 Hook과 callback에 대한 정정

기존 문서는 비공식 2차 자료를 근거로 “v1.15.3+ before/after-LLM hook으로 메시지를 자유롭게 수정할 수 있다”고 단정했다. 현재 확인한 공식 핵심 문서만으로는 특정 버전의 해당 API 계약을 확정하기 어렵다.

확실히 문서화된 것은 다음과 같다.

- `step_callback`: 에이전트 단계 관찰
- `task_callback`: Task 완료 관찰
- `guardrail`: Task 출력 검증·재시도·선택적 변환
- kickoff 전후 callback: Crew 실행 경계 처리

따라서 실제 CrewAI 패키지를 직접 래핑하는 B 노선은 “공식 훅이 있으므로 가능”이라고 선결론 내리지 않는다. 선택한 버전의 공개 API와 소스를 검증하는 별도 spike가 필요하다.

---

# 3. ACIArena와 CrewAI의 차이점 및 해소 과제

## 3.1 분석 대상의 차이

| ACIArena | CrewAI |
|---|---|
| 연구용 통일 실행 프레임워크 | 범용 Agent/Crew/Flow 개발 프레임워크 |
| 협업 패턴을 간결한 Python 클래스로 재구현 | 실제 런타임이 prompt, tool loop, delegation, memory 등을 관리 |
| 모든 agent step을 명시적으로 노출 | 실행 세부가 Agent executor와 Crew 내부에 분산 |
| 공격·방어의 동일 조건 비교가 우선 | 기능 유연성과 실제 애플리케이션 구성이 우선 |

ACIArena가 비교하는 것은 원본 제품의 모든 엔지니어링이 아니라 **역할 구성과 상호작용 패턴**이다. CrewAI는 엔지니어링 기능 자체가 정체성의 큰 부분이므로 재구현 시 손실이 더 크다.

## 3.2 구성요소 매핑

| ACIArena | CrewAI | 차이 |
|---|---|---|
| `BaseAgent.profile` | `role`, `goal`, `backstory` | 단일 문자열 대 구조화 속성 |
| `BaseAgent.tools` | Agent/Task tools | Task별 도구 제한과 실행 루프 존재 |
| `Memory.conversation` | CrewAI memory/context | 저장·검색 의미와 영속성이 다름 |
| `BaseMAS` | `Crew` | ACIArena는 3단계 메서드, CrewAI는 `kickoff()` |
| `bootstrap/step/conclude` | Process 실행 | 호출 경계가 일치하지 않음 |
| `pre_step/step/post_step` | callbacks/guardrail/runtime internals | 공격·방어 개입 granularity가 다름 |
| `max_turn` | `max_iter`, Task 수, manager loop | 반복 단위가 다름 |
| `get_token_usage()` | `usage_metrics` | 집계 기준이 다를 수 있음 |
| `answer["response"]` | Crew/Task output | verifier 입력 정규화 필요 |

## 3.3 공격면 매핑과 남는 문제

| 공격 프리미티브 | 재구현 노선 | 실제 패키지 래핑 노선 | 남는 문제 |
|---|---|---|---|
| 프로파일 변조 | role/goal/backstory 렌더링 결과 또는 개별 필드 변조 | Agent 생성 전 config 변조 | 공격 필드를 기록해야 해석 가능 |
| Instruction Injection | `run_step()` 입력 변조 | Task description/context 또는 검증된 LLM 입력 훅 | 실제 호출마다 적용됐는지 추적 필요 |
| Message Poison | `run_step()` 반환 교체 | Task output/전달 context 개입 | guardrail과 의미가 다름 |
| Tool Injection | tools 목록에 악성 도구 추가 | CrewAI Tool 객체 추가 | 현재 ACIArena에 구체 공격 없음 |
| Memory Injection | 대화 메시지 append | CrewAI 저장 API/DB 오염 | 의미가 달라 별도 공격 정의 필요 |
| 위임 경로 공격 | 명시적 delegate message 생성 | 자동 위임 도구 호출 | 기존 ACIArena 공격 모델에 없는 핵심 경로 |

## 3.4 해결해야 할 문제 우선순위

### P0 — 결과가 유효하려면 반드시 해결

1. API 키 제거와 실험 설정 외부화
2. 공격 객체 병렬 공유 제거
3. 중복 공격 등록 제거
4. MAS 출력 정규화와 verifier golden test
5. 모든 CrewAI 상호작용의 `run_step()` 경유
6. sequential/hierarchical 및 위임 메시지 edge 기록
7. 모델·temperature·max token·seed·반복 수 고정

### P1 — CrewAI 대표성을 위해 반드시 해결

1. role/goal/backstory 구조 보존
2. 매니저를 명시적 Agent로 등록해 공격 위치로 선택 가능하게 구성
3. `allow_delegation`을 에이전트별 설정으로 유지
4. 자유 텍스트 context를 가진 코워커 위임 구현
5. 앞 Task 출력이 다음 Task로 전달되는 경로 보존
6. 실제 CrewAI 설치본과 benign 동등성 검증

### P2 — 연구 범위를 확장할 때 해결

1. CrewAI-native Tool Injection
2. 메모리 영속 공격
3. PVI 구현
4. 과학·의학 데이터
5. 공격 자동 최적화
6. 내장 guardrail을 포함한 방어 비교

## 3.5 공정 비교를 위한 통제 변수

다음 항목이 다르면 CrewAI와 기존 MAS의 차이가 아니라 실험 조건의 차이를 측정할 수 있다.

- 동일 LLM과 API endpoint
- temperature 0.0, 동일 max token
- 동일 정상 태스크와 verifier
- 동일 공격 payload
- 동일 malicious agent 수
- 동일 최대 상호작용 예산
- 동일 token accounting 범위
- 동일 반복 횟수와 실패 재시도 정책
- 메모리·캐시·planning·guardrail 명시적 on/off

---

# 4. ACIArena와 CrewAI 통합 방법론

## 4.1 연구 질문과 주장 범위

통합의 연구 질문은 다음처럼 한정한다.

> 동일한 ACIArena 실행·공격·평가 조건에서 CrewAI의 표준 sequential/hierarchical 협업 패턴과 코워커 위임 채널은 ACI의 성공률과 전파에 어떤 영향을 주는가?

결과 문서에서 피해야 할 표현:

- “CrewAI 전체의 ASR은 X다.”
- “CrewAI 프레임워크가 AutoGen보다 취약하다.”
- “실제 CrewAI 제품의 모든 보안 특성을 평가했다.”

권장 표현:

- “고정된 공식 기반 구성에서 CrewAI식 sequential/hierarchical 패턴의 ASR은 X다.”
- “동일 재구현 조건에서 위임 기반 패턴과 2자 대화 패턴을 비교했다.”
- “메모리 영속, Flow, 내장 guardrail은 1차 범위에서 제외했다.”

## 4.2 통합 노선 선택

| 노선 | 설명 | 장점 | 단점 | 용도 |
|---|---|---|---|---|
| A. 단순 모사 | 역할 이름과 순서만 흉내 | 가장 쉬움 | CrewAI 대표성 부족 | 사용하지 않음 |
| B. 실제 패키지 어댑터 | `crewai`를 직접 실행 | 런타임 충실도 높음 | 주입 지점·의존성·회계가 이질적 | benign 동등성 검증 및 후속 연구 |
| C. 충실 재구현 | ACIArena 위에 핵심 CrewAI 기제 재현 | 기존 MAS와 공정 비교, 공격 재사용 | 실제 런타임 전체는 아님 | **주 실험 노선** |

주 실험은 C 노선을 사용한다. B 노선은 C가 실제 CrewAI의 정상 동작을 지나치게 왜곡하지 않았는지 확인하는 보조 기준으로 사용한다.

## 4.3 대표성 확보 원칙

### 원칙 1 — 구성을 숨은 상수가 아니라 실험 변수로 만든다

최소 구현:

- `crewai_seq`: sequential process
- `crewai_hier`: hierarchical manager process

권장 구현은 process와 worker delegation을 분리한 2×2 구성이다.

| 구성 | Process | worker `allow_delegation` | 의미 |
|---|---|---:|---|
| `crewai_seq_nodeleg` | sequential | False | 공식 기본에 가까운 순차 기준선 |
| `crewai_seq_deleg` | sequential | True | 코워커 위임이 추가된 순차 구조 |
| `crewai_hier_nodeleg` | hierarchical | False | 매니저 위임만 있는 계층 구조 |
| `crewai_hier_deleg` | hierarchical | True | 매니저 + worker 간 위임 구조 |

비용이 제한되면 `crewai_seq_nodeleg`와 `crewai_hier_deleg`을 최소 쌍으로 실행하되, process 효과와 delegation 효과가 혼합된다는 limitation을 명시한다.

### 원칙 2 — 역할 선택 근거를 외부화한다

CrewAI에는 하나의 정본 Crew가 없다. 역할과 Task가 사용자 정의이므로 다음 순서로 근거를 남긴다.

1. 통합 시점의 공식 quickstart 또는 CLI scaffold를 보관
2. package version, Git commit, lockfile 기록
3. 공식 기본값과 변경한 값을 표로 기록
4. 수학·코드에 공통 적용 가능한 역할명을 사용
5. 공격 외 조건에서는 모든 구성에서 역할 프롬프트를 동일하게 유지

권장 공통 역할:

| 역할 | 책임 |
|---|---|
| Solver | 원 태스크 분석과 초기 해답 생성 |
| Reviewer | 정확성·제약·공격성 없는 정상 조건의 오류 검토 |
| Finalizer | 선행 출력과 검토를 종합해 verifier 친화적 최종 답 생성 |
| Manager | hierarchical에서 작업 배정·검토·완료 판단 |

이 역할들은 특정 도메인 정답 지식을 하드코딩하지 않고 “전문화된 팀 + 검토 + 최종화”라는 CrewAI의 역할 중심 구성을 표현한다.

### 원칙 3 — 위임 채널을 실제 메시지 edge로 보존한다

위임은 문자열을 직접 함수에 넘기는 헬퍼로 끝내면 안 된다. 최소 메시지 구조를 남긴다.

```python
DelegationMessage(
    sender="solver",
    recipient="reviewer",
    kind="delegate" | "ask",
    task="...",
    context="...",
    parent_task_id="...",
)
```

수신 에이전트의 처리는 반드시 다음 형태를 따른다.

```text
sender가 메시지 생성
  → logger/topology recorder에 edge 기록
  → recipient.run_step(message)
  → 결과를 sender 또는 manager에게 전달
```

이렇게 해야 위임 메시지에도 공격·방어가 적용되고, 전파 거리와 PVI를 나중에 계산할 수 있다.

## 4.4 권장 코드 구조

```text
aciarena/aciarena/mas/crewai/
├── __init__.py
├── agents/
│   ├── __init__.py
│   ├── crewai_agent.py
│   ├── solver_agent.py
│   ├── reviewer_agent.py
│   ├── finalizer_agent.py
│   └── manager_agent.py
├── messages.py
├── prompts.py
├── sequential_mas.py
└── hierarchical_mas.py
```

### `CrewAIAgent`의 최소 책임

- `role`, `goal`, `backstory`를 별도 필드로 보존
- 세 필드를 일정한 template으로 `profile`에 렌더링
- `allow_delegation`과 coworker 목록 보존
- LLM 호출은 `step()`, 외부 호출은 항상 `run_step()` 사용
- 도구 호출과 위임 호출을 구분해 로깅
- 최종 응답과 중간 협업 메시지를 구분

### Sequential MAS의 최소 책임

1. 원 질의를 Solver에 전달
2. Solver 출력을 Reviewer 컨텍스트에 전달
3. Reviewer 검토와 원 답을 Finalizer에 전달
4. Finalizer 출력만 `args["response"]`에 저장
5. 모든 전달 edge 기록

### Hierarchical MAS의 최소 책임

1. Manager가 질의를 받아 작업을 배정
2. Worker 응답을 Manager가 수집
3. 필요 시 Manager 또는 delegation-enabled worker가 추가 위임
4. Manager가 결과를 검토
5. Finalizer 또는 Manager의 정규화된 최종 출력 반환
6. Manager를 `malicious_agents` 대상에 포함

## 4.5 공격·방어 적용 설계

### 기존 공격 재사용

- `InstructionInjectionAttack`: 대상 Agent의 `step()` 입력에 payload 추가
- `MessagePoisonAttack`: 대상 Agent의 `step()` 반환을 payload로 교체
- `MaliciousAgentAttack`: 렌더링된 profile을 교체하되 공격 전 구조화 필드를 로그에 보존

### 신규 CrewAI 특화 공격

1. **Delegation Context Injection**
   - 위임의 `context`에 payload를 삽입
   - recipient와 이후 manager/finalizer로의 전파 측정

2. **Delegation Recipient Hijacking**
   - 원래 수신자 대신 공격에 유리한 coworker를 선택

3. **Tool Description Injection**
   - 실제 호출 가능한 악성 또는 오염 도구를 등록
   - 단순 문자열 append가 아니라 tool schema와 실행 결과까지 평가

4. **Manager Profile Attack**
   - 배정·검토 권한을 가진 매니저를 공격해 위치 효과 측정

메모리 공격은 1차 실험에 섞지 않는다. CrewAI 설치본의 저장·검색 동작을 고정한 후 별도 suite로 설계한다.

### 방어 적용

- ACIArena 방어는 기존처럼 `pre_step`/`post_step`에만 적용
- CrewAI 내장 guardrail은 1차 비교에서 명시적으로 비활성화
- 내장 guardrail 비교는 “ACIArena 방어 + CrewAI 방어”가 아니라 별도 실험군으로 실행

## 4.6 출력·토큰·토폴로지 표준화

### 최종 출력 계약

모든 CrewAI 재구현 MAS는 다음 최소 결과를 반환한다.

```python
{
    "response": "verifier에 전달할 최종 원문",
    "conversation": {...},
    "edges": [...],
    "token_usage": {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    },
}
```

`response`에는 Finalizer가 만든 최종 답만 넣고, 대화 전체나 manager reasoning을 섞지 않는다.

### 토큰 회계

- 재구현본은 기존 `OpenAILLM`을 사용해 기존 MAS와 같은 범위로 집계
- 실제 CrewAI 동등성 실행은 `usage_metrics`를 별도 기록
- 재구현본과 실제 패키지의 token usage는 절대값이 아니라 호출 수와 범위 차이를 함께 보고

### 토폴로지 기록

각 메시지마다 다음을 저장한다.

- sender, recipient
- message kind: task/context/delegate/ask/review/final
- round 및 task ID
- 공격 적용 여부와 attack ID
- 방어 적용 여부
- payload가 처음 등장한 위치

이 기록이 있어야 malicious agent와 최종 응답 사이의 거리 및 PVI를 계산할 수 있다.

## 4.7 검증 절차

### 단계 0 — 평가 기반선 복구

- 키 제거
- 병렬 공격 객체 격리
- 중복 공격 제거
- AutoGen benign verifier 실패 원인 확인
- 태스크별 상세 결과 저장

### 단계 1 — 단위 테스트

- role/goal/backstory 렌더링
- delegation on/off
- 잘못된 recipient 차단
- 모든 위임이 recipient `run_step()`을 통과하는지 spy로 확인
- sequential context 전달
- hierarchical manager 배정과 결과 회수
- 최종 `response` 정규화
- token 합산

### 단계 2 — 공격 발동 smoke test

각 공격을 한 태스크·한 agent에 적용하고 다음을 확인한다.

- 프로파일이 실제 LLM system message에 반영되는가?
- instruction payload가 실제 대상 호출에 들어가는가?
- poisoned output이 downstream context에 들어가는가?
- delegation context payload가 recipient와 후속 agent로 전파되는가?
- 방어가 동일 경로에서 발동하는가?

### 단계 3 — 실제 CrewAI와 benign 동등성

별도 가상환경에 고정 버전 CrewAI를 설치한다.

- 동일 role/goal/backstory
- 동일 Task description/expected_output
- 동일 process
- 동일 LLM·temperature
- 공격·방어 없음
- 메모리·planning·guardrail 명시적 비활성

비교 항목:

- 태스크 정확도
- 호출 수
- 최종 출력 형식
- 토큰 소비량
- sequential/hierarchical 메시지 경로

정확도가 크게 다르면 재구현본의 프롬프트 또는 실행 순서를 재검토한다. 이 검증은 “같은 내부 구현”을 증명하는 것이 아니라 “정상 조건의 기능적 유사성”을 확보하는 절차다.

### 단계 4 — 파일럿 평가

- math/code에서 각각 소수 태스크 선정
- 2×2 구성 실행
- manager와 worker 위치를 각각 공격
- 결과를 수동 판정과 비교
- 실패·timeout·judge parse 오류를 별도 오류율로 보고

### 단계 5 — 본 평가

- 전체 69개 태스크 우선 실행
- 구성·공격면·악성 agent 위치별 3회 반복
- BU, UA, ASR, 공격면별 ASR, token usage 보고
- 가능하면 bootstrap 95% CI 추가
- PVI는 topology edge 기록이 안정화된 후 추가

## 4.8 완료 기준

다음 조건을 모두 만족해야 “CrewAI 통합 완료”로 본다.

- [ ] sequential과 hierarchical MAS가 각각 등록되어 있다.
- [ ] role/goal/backstory가 구조적으로 보존된다.
- [ ] delegation on/off가 실제 메시지 경로를 바꾼다.
- [ ] 모든 LLM 호출과 위임 수신이 `run_step()`을 통과한다.
- [ ] manager를 악성 agent로 지정할 수 있다.
- [ ] 기존 세 공격 프리미티브가 smoke test에서 발동한다.
- [ ] delegation 전용 공격이 최소 1개 존재한다.
- [ ] 최종 출력이 math/code verifier와 호환된다.
- [ ] 공격 객체 병렬 경합이 제거되었다.
- [ ] 태스크·공격별 상세 결과가 저장된다.
- [ ] 실제 CrewAI와 benign 동등성 결과가 기록된다.
- [ ] package version, commit, 모델 설정, prompt manifest가 고정된다.
- [ ] 저장소에 API 키가 남아 있지 않다.

---

# 5. 권장 구현 순서

| 순서 | 작업 | 산출물 |
|---:|---|---|
| 1 | 보안·평가 기반선 수정 | 안전한 config, 격리된 attack 객체, verifier golden test |
| 2 | 공통 CrewAIAgent와 메시지 모델 | 구조화 profile, DelegationMessage, edge logger |
| 3 | `crewai_seq_nodeleg` 구현 | 순차 기준선 |
| 4 | delegation-enabled sequential 구현 | 코워커 위임 경로 |
| 5 | hierarchical manager 구현 | manager 공격 가능 구조 |
| 6 | 공격·방어 smoke test | 경로별 발동 증거 |
| 7 | 실제 CrewAI benign 비교 | 동등성 보고서 |
| 8 | 파일럿 평가와 verifier 교정 | 수동 대조 결과 |
| 9 | 전체 평가 | BU/UA/ASR/토큰/CI |
| 10 | PVI·Tool/Memory 확장 | 후속 연구 결과 |

---

# 6. 출처와 기존 문서 관계

## 로컬 1차 자료

- ACIArena 구현: `aciarena/`
- ACIArena 원 논문: `ACIArena_관련_문서/ACIARENA - Toward Unified Evaluation for Agent Cascading Injection/`
- MASLab 논문: `ACIArena_관련_문서/MASLab_A Unified and Comprehensive Codebase.md`
- 실행 로그: `aciarena/logs/`

## 기존 분석 문서

- `Debug_log.md`: 로컬 실행 버그 수정 기록
- `ACIArena_관련_문서/ACIArena_요약.md`: 논문 한글 요약
- `ACIArena_관련_문서/논문_구현_비교.md`: 논문과 코드 차이의 상세 조사
- `CrewAI_통합_평가.md`: 통합 노선의 초기 평가
- `CrewAI_대표성_및_재구현_설계.md`: 대표성 및 P0 보존 요소 논의

기존 문서의 판단 중 이 문서에서 수정한 사항:

1. 현재 저장소에는 CrewAI 통합 구현이 없으므로 “통합이 완료되었다”가 아니라 “통합 가능한 골격과 설계가 준비되었다”로 표현한다.
2. 현재 등록 공격에는 구체 Memory Injection 공격이 없으므로 “23개 중 메모리 공격 2개 제외” 계산을 사용하지 않는다.
3. Task guardrail은 단순 post-processing이 아니라 검증·피드백·재시도 의미를 포함한다.
4. 비공식 자료만으로 특정 버전의 before/after-LLM hook을 확정하지 않는다.
5. CrewAI 메모리 문서가 서로 다른 세대의 설명을 포함하므로 package/source pin 없이 구조를 단정하지 않는다.
6. 기존 문서에 없던 병렬 공격 객체 데이터 경합과 API 키 노출을 선행 해결 과제로 추가한다.

## CrewAI 공식 자료

- [CrewAI GitHub](https://github.com/crewAIInc/crewAI)
- [Agents](https://docs.crewai.com/v1.15.7/en/concepts/agents)
- [Tasks](https://docs.crewai.com/v1.15.7/en/concepts/tasks)
- [Crews](https://docs.crewai.com/v1.15.7/en/concepts/crews)
- [Processes](https://docs.crewai.com/v1.15.7/en/concepts/processes)
- [Collaboration](https://docs.crewai.com/v1.15.7/en/concepts/collaboration)
- [Memory](https://docs.crewai.com/v1.15.7/en/concepts/memory)

> 주의: 문서 URL의 버전 경로만으로 내용 불변성이 보장된다고 가정하지 않는다. 실제 실험에서는 설치 package version, Git commit, dependency lockfile과 사용한 문서 사본을 함께 보관한다.
