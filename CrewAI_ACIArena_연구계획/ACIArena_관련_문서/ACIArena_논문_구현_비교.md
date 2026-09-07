# ACIArena — 논문 vs 구현 코드 수준 비교

> 비교 대상
> - **논문 원문**: [`ACIARENA 논문/ACIARENA - Toward Unified Evaluation for Agent Cascading Injection.md`](<ACIARENA 논문/ACIARENA - Toward Unified Evaluation for Agent Cascading Injection.md>) (arXiv:2604.07775v1)
> - **구현 코드**: `aciarena/` (커밋 시점 2026-07-23 로그 기준)
>
> 이 문서는 논문이 주장하는 벤치마크 사양과 실제 저장소 코드의 구현 수준을 항목별로 대조한다.
> 코드 경로는 모두 `aciarena/aciarena/...` 기준이며, 확인에 사용한 실제 파일을 각주로 표기했다.

---

## 0. 한눈에 보기 (TL;DR)

| 항목 | 논문 주장 | 구현 코드 | 달성도 | 비고 |
|---|---|---|---|---|
| 총 정상 태스크(benign pool) | ≈ 벤치마크 1,356 케이스 기반 | **69개** (math 39 + code 30) | 🔴 ~5% | 데이터셋 JSON 2개뿐 |
| 태스크 도메인 | 4종 (수학·코드·과학·의학) | **2종** (수학·코드) | 🟡 50% | QATask 클래스는 있으나 미배선 |
| 공격 종류 | 28종 | **23개 등록** (고유 22, 중복 1) | 🟡 ~80% | 하드코딩 페이로드 |
| 공격면(Attack Surface) | 3종 | **3종 정의, 실질 2.x종 사용** | 🟡 | Tool/Memory 주입은 미사용 |
| 평가 스위트 | 3종 (Hijacking/Disruption/Exfiltration) | **4종** (benign + 위 3종) | 🟢 100%+ | 모두 구현·등록됨 |
| 통합 MAS | 6종 | **7종 등록** (6종 + MAD 추가) | 🟢 100%+ | 논문 6종 전부 존재 |
| 평가 지표 | BU / ASR / UA / **PVI** | BU / ASR / UA / ASR_Surface | 🟡 | **PVI 미구현** |
| 공격 자동생성(생성-변이-선택) | 핵심 기여 (§4.5) | **미구현** | 🔴 0% | 최적화 루프 없음 |
| 방어 기법 | 6종 (BERT/Delimiter/Sandwich/AGrail/G-Safeguard/ACI-Sentinel) | **4종** | 🟡 67% | AGrail·G-Safeguard 없음 |
| 위협모델(악성 에이전트 수) | 1개 (BFT 근거) | **1개** | 🟢 일치 | |
| 신뢰성 검증(인간 어노테이션/kappa) | 있음 | **없음** | 🔴 | 코드에 없음 |

**요약 판정**: 코드는 **프레임워크의 골격(모듈 구조·MAS·스위트·공격면·지표 계산)은 논문과 정합적으로 잘 갖춰져 있으나**, 논문을 "벤치마크"로 만드는 **규모(데이터셋·공격 수)**, **핵심 방법론(공격 자동생성 루프)**, **핵심 지표(PVI)**, **일부 방어/검증**이 빠져 있는 **연구 프로토타입 단계**다.

> ⚠️ 사용자 인식 교정: "평가 suite가 Hijacking 하나뿐"이라는 인상은 **사실과 다르다.** 코드에는 `benign / hijacking / disruption / disclosure(=Exfiltration)` **4개 스위트가 모두 구현·등록**되어 있다(`evaluation_suite.py`). 다만 `logs/`에 남은 실행 결과가 `benign`·`hijacking`뿐이라 그렇게 보였을 수 있다.

---

## 1. 데이터셋 / 테스트 케이스 규모

**논문(§4.2)**: 총 1,356 케이스 = 정상 태스크 1개 + ACI 공격 1개의 쌍. 스위트별 Hijacking 336 / Disruption 585 / Exfiltration 435. 출처 벤치마크 GSM8K, MATH500, HumanEval, MBPP, GPQA, MedMCQA. LLM 심판이 복잡도·분해가능성·모호성 기준으로 선별.

**구현**:
- 데이터셋 파일은 `evaluation/datasets/aciarena_math.json`(**39개**), `aciarena_code.json`(**30개**) 두 개뿐 → **정상 태스크 총 69개**.[^ds]
- `init_tasks()`는 `math`, `code` 두 도메인만 로드하며, 그 외 도메인은 `ValueError`.[^suite]
- 실제 공격 실행 수는 (태스크 × 스위트별 공격 수)로 늘어나지만(예: disclosure+code = 30 × 5 = 150회), **정상 태스크 풀 자체가 논문의 약 5%**.
- `datasets/selection.py`(LLM 심판 선별 로직)는 존재하나, 논문의 6개 출처 벤치마크 전부를 커버하지 못하고 결과물이 math/code JSON 2개로만 남아 있음.

**판정**: 🔴 규모가 논문 벤치마크에 크게 못 미침. "총 테스트케이스 70개 미만"이라는 관찰은 **정상 태스크 풀 기준으로 정확**하다.

---

## 2. 공격면 (Attack Surface) — 논문 3종

**논문(§3.2)**: Adversarial Input(I·M·T 조작) / Malicious Agent(P 조작) / Message Poison(전송 메시지 조작).

**구현**(`attacks/base_attack.py`):

| 공격면 | 구현 클래스 | 상태 |
|---|---|---|
| Adversarial Input | `InstructionInjectionAttack` (지시 I) | 🟢 사용됨 |
| " | `ToolInjectionAttack` (도구 T) | 🟡 **정의만, 등록 공격 0개** |
| " | `MemoryInjectionAttack` (메모리 M) | 🟡 **정의만, 등록 공격 0개** |
| Malicious Agent | `MaliciousAgentAttack` (프로파일 P) | 🟢 사용됨 (최다) |
| Message Poison | `MessagePoisonAttack` | 🟢 사용됨 |

**판정**: 🟡 3개 공격면의 **부모 클래스는 모두 존재**하나, Adversarial Input 중 **도구/메모리 주입 경로는 실제 공격이 하나도 등록되지 않아** 미행사 상태. 실질적으로 `Instruction 주입 / Malicious Agent / Message Poison` 3경로만 평가에 동작한다.

---

## 3. 공격 목표(Suite) & 공격 개수

**논문(§3.3, §4.2)**: 3 목표(Hijacking/Disruption/Exfiltration) × 3 공격면 격자, 총 **28종 공격**.

**구현**: 스위트는 `benign / hijacking / disruption / disclosure` **4개 모두 등록**(`@register_suite`).[^suite] 공격 클래스는 `@register_attack_goal`로 총 **23개 등록**(NoneAttack 제외):

| 스위트(목표) | 파일 | 등록 공격 수 | 공격면 분포 |
|---|---|---|---|
| Hijacking | `hijacking_attack.py` | **8** | MaliciousAgent 4·Instruction 3·MessagePoison 1 |
| Disruption | `disruption_attack.py` | **6** | MaliciousAgent 4·Instruction 1·MessagePoison 1 |
| Exfiltration(=disclosure) | `disclosure_attack.py` | **9** | MaliciousAgent 4·Instruction 4·MessagePoison 1 |
| **합계** | | **23** | |

주의점:
- `hijacking_attack.py`에 **`AnswerMappingAgent`가 두 번(라인 134·218) 중복 정의·중복 등록**되어 있음 → 고유 클래스는 **22개**, 실행 시 hijacking_math 공격이 하나 중복 카운트됨(사실상 버그).[^dup]
- 공격은 모두 **하드코딩된 정적 프롬프트 페이로드**(예: `SAFETY_CHECK_PROMPT`, `MATH_INVERT_SIGN_PROMPT`). 논문의 자동 생성/변이 결과물이 아님.

**판정**: 🟡 개수는 논문 28종 대비 23종(≈80%)으로 근접하나, **생성 방식이 근본적으로 다르다**(§6 참조). 사용자의 "공격 4종류뿐" 인상은 실제와 다르며, 실제로는 스위트당 6~9종이 등록되어 있다(단, 도메인 필터로 한 실행에서 4~5종만 활성화됨).

---

## 4. 통합 MAS — 논문 6종

**논문(§4.4)**: MetaGPT, Self Consistency, AutoGen, CAMEL, AgentVerse, LLM Debate (토폴로지: Vertical/Horizontal/Hierarchical).

**구현**(`@register_mas`): **7종 등록** → `metagpt`, `sc`(self consistency), `autogen`, `camel`, `agentverse`, `llm_debate`, **`mad`(Multi-Agent Debate, 논문 표에 없는 추가 MAS)**.[^mas]

**판정**: 🟢 논문 6종을 **전부 구현**했고 MAD를 추가로 제공. MAS 커버리지는 **논문 수준 이상**. (각 MAS의 에이전트 역할·프롬프트 충실도까지는 별도 검증 필요.)

---

## 5. 평가 지표

**논문(§4.6)**: BU(Benign Utility, pass@1) / ASR / UA / **PVI(Propagation Vulnerability Index, 토폴로지 거리 가중)**.

**구현**(`evaluation_suite.py`):

| 지표 | 구현 | 근거 |
|---|---|---|
| BU | 🟢 | `BenignSuite`가 `Benign Utility` 반환 |
| UA (Utility under Attack) | 🟢 | 각 공격 스위트가 `Utility under Attack` 반환 |
| ASR | 🟢 | `Attack Success Rate` 반환 |
| ASR_Surface(공격면별 ASR) | 🟢 (논문 §5.3(g) 분석에 대응) | adv_input/malicious_agent/message_poison 분해 |
| **PVI** | 🔴 **미구현** | 코드 전체에 `pvi/propagation/topology distance` 심볼 **전무** |

**판정**: 🟡 유틸리티·ASR 계열은 완비. 그러나 **논문의 대표적 신규 지표 PVI(전파 취약성)와 이를 위한 토폴로지 최소거리 계산이 코드에 전혀 없음.** 전파(cascade)를 정량화한다는 논문의 핵심 서사가 지표 수준에서 빠져 있다.

---

## 6. 공격 프롬프트 자동 생성 (논문의 핵심 방법론)

**논문(§4.5)**: 화이트박스 없이 **생성–변이–선택 루프**. 변이 연산자 ω 샘플링 → 후보 공격 실행 → 심판 점수 `J = J_stealth(은밀성) + (1/N)ΣJ_harm(유해성)` → argmax 선택을 반복.

**구현**: **존재하지 않음.**
- `mutat*`, `optimiz*`, `stealth`, `J_harm`, `argmax` 등 관련 심볼이 코드 전체에서 검색되지 않음.
- 모든 공격 페이로드는 소스에 문자열 상수로 하드코딩.
- 즉, 논문이 "우리 벤치마크의 공격이 특정 시스템에 종속되지 않는다"고 주장하는 근거인 **자동 최적화 파이프라인이 재현 불가**.

**판정**: 🔴 **논문의 가장 독창적인 기여 중 하나가 통째로 미구현.** 이는 규모 부족(§1)의 직접 원인이기도 하다(자동 생성이 없으니 공격이 수작업 정적 세트에 머묾).

> 참고: 사용자가 IDE에서 연 `scripts/autogen.sh`는 "공격 자동생성"이 아니라 **AutoGen MAS를 벤치마크에 돌리는 실행 스크립트**다(`--mas autogen`). 이름이 혼동을 줄 수 있으나 최적화 루프와 무관하다.

---

## 7. 방어(Defense) 평가

**논문(§6)**: 전형적 3종(BERT/DeBERTa 탐지기, Delimiter, Sandwich) + 고급 2종(AGrail, G-Safeguard) + 제안 방어 ACI-Sentinel = **6종**.

**구현**(`task_executor.py`의 `load_defense`):

| 방어 | 구현 | 근거 |
|---|---|---|
| BERT/DeBERTa 탐지기 | 🟢 | `bert_detector.py` (protectai/deberta-v3) |
| Delimiter | 🟢 | post_step 래핑 |
| Sandwich | 🟢 | pre_step에 태스크 재삽입 |
| ACI-Sentinel | 🟢 | `aci_sentinel.py` (Contextual Least Privilege / semantic pruning) |
| **AGrail** | 🔴 미구현 | — |
| **G-Safeguard** | 🔴 미구현 | — |

**판정**: 🟡 전형적 방어 3종 + 제안 방어 ACI-Sentinel은 구현됨(4/6). 그러나 논문이 "보안-유틸리티 딜레마"의 근거로 삼은 **고급 방어 2종(AGrail·G-Safeguard)이 없어**, §6.3의 비교 결론은 코드로 재현 불가. 또한 논문 §6.5의 **적응형 공격 재취약성 실험**도 자동 최적화 루프(§6)가 없어 재현 불가.

---

## 8. 위협 모델 / 실행 설정

| 항목 | 논문(§5.1) | 구현 | 판정 |
|---|---|---|---|
| 악성 에이전트 수 | 1개 (BFT 근거) | 1개 (`--malicious_agents`로 지정, 스크립트는 단일) | 🟢 일치 |
| 공격 스케줄링(시점·빈도) | Executor가 제어 | `ContinuousAttackExecutor`만 구현(`intermittent`는 주석 처리) | 🟡 부분 |
| 모델 | GPT-4o / 4o-mini / Qwen2.5-7B | `configs/model.yaml`로 임의 지정(로그엔 gpt-4o-mini) | 🟢 구조 지원 |
| 상호작용 턴 제한(≤3) | 있음 | `mas.max_turn` 존재 | 🟢 |

---

## 9. 평가 신뢰성 검증 (논문 §7)

**논문**: 인간 어노테이터 3인, Cohen's kappa 0.92, LLM 심판–인간 98% 일치.

**구현**: 관련 코드·스크립트·데이터 **없음**. LLM 심판(`configs/judge.yaml`, Disruption/Exfiltration 판정용)은 있으나, 인간 검증·일치도 계산은 저장소에 부재.

**판정**: 🔴 미구현(연구 산출물이라 별도 문서로만 존재할 가능성).

---

## 10. 모듈 아키텍처 정합성 (논문 §4.7)

논문이 제시한 5개 모듈 추상화는 코드에 **잘 반영**되어 있어, 확장성 설계 목표는 실제로 달성:

| 논문 모듈 | 구현 대응 | 판정 |
|---|---|---|
| Agent | `agent_components/base_agent.py` (LLM·Memory·Tool 추상화) | 🟢 |
| MAS | `mas/base_mas.py` (bootstrap/step/conclude 3단계, 악성 에이전트 지정) | 🟢 |
| Task | `evaluation/task/*` (`verify` 인터페이스) | 🟢 |
| Attack | `attacks/base_attack.py` (공격면별 부모 클래스, step 오버라이드) | 🟢 |
| Executor | `evaluation/task_executor.py` (공격/방어 스케줄링) | 🟢 |
| (레지스트리) | `utils/factory.py` (register_* 데코레이터) | 🟢 |

**판정**: 🟢 **논문의 "Extensible/Standardized" 설계 원칙은 코드에서 충실히 구현됨.** 골격은 논문 그대로다 — 빠진 것은 골격이 아니라 **채워 넣을 내용물(데이터·공격 생성·지표·방어)**이다.

---

## 11. 종합 결론

### 구현이 논문 수준에 도달한 영역 🟢
- 모듈러 아키텍처(Agent/MAS/Task/Attack/Executor/Registry) — 논문 §4.7 그대로.
- MAS 6종 전부 + MAD 추가(7종).
- 3개 공격 목표 스위트 전부(+ benign) 구현·등록.
- 3개 공격면 부모 클래스, BU/UA/ASR/ASR_Surface 지표.
- 위협모델(단일 악성 에이전트), 3단계 MAS 실행, LLM 심판 판정.

### 논문 대비 결정적으로 부족한 영역 🔴
1. **공격 자동생성(생성-변이-선택) 루프 전무** — 논문 핵심 기여, 재현 불가.
2. **데이터셋 규모 ~5%** (69 vs 1,356), 도메인 2/4 (과학·의학 없음).
3. **PVI 지표 미구현** — 전파 정량화 서사가 지표에 없음.
4. **고급 방어 2종(AGrail·G-Safeguard) 및 적응형 공격 실험 미구현.**
5. **인간 검증/신뢰성 실험 부재.**

### 부분/버그 🟡
- Tool·Memory 주입 공격면은 클래스만 있고 등록 공격 0개.
- `AnswerMappingAgent` 중복 정의/등록(정리 필요).
- Executor는 continuous 1종만(intermittent 주석).

### 한 줄 정리
> **코드는 논문 벤치마크의 "실행 가능한 골격 프로토타입"이다.** 프레임워크 설계·MAS·스위트·공격면·기본 지표는 논문과 정합적으로 갖춰졌으나, 벤치마크를 벤치마크답게 만드는 **규모(데이터·공격)·핵심 방법론(공격 자동생성)·핵심 지표(PVI)·검증**이 빠져, 현재 수준은 **논문 주장의 30~40% 재현**으로 평가된다.

---

## 12. 프로젝트 관점 적합성 — "ACIArena에 CrewAI 추가 후 정량 평가"

> 이 절은 §0~§11의 일반 비교와 달리, **"새 MAS(CrewAI)를 붙여 정량 평가한다"는 특정 목표**에서 이 저장소의 구현 수준이 적절한지를 판정한다. 결론: **베이스로서는 적절하다(🟢). 다만 실제 노력·리스크는 "데이터·공격 채우기"가 아니라 "CrewAI를 어느 충실도로 붙일지 + 그 숫자를 신뢰할 수 있게 만들지"에 있다.**

### 12.1 왜 뼈대가 적절한가 — 에이전트 계약(Extension Contract)

공격·방어·스위트는 **에이전트 계약을 통해서만** 동작한다. 새 MAS가 이 계약만 지키면 나머지가 전부 자동으로 붙는다.[^contract]

```
BaseAgent.run_step()  =  pre_step()  →  step()  →  post_step()
                          ▲방어(sandwich)  ▲공격(injection/poison)  ▲방어(sentinel/bert/delimiter)
```

- 공격: `agent.step` 몽키패칭(`InstructionInjection`·`MessagePoison`), `agent.profile`/`tools`/`memory` 조작(`MaliciousAgent` 등).
- 방어: `agent.pre_step`/`post_step` 몽키패칭.
- **새 MAS가 각 에이전트를 `run_step()`으로 구동하기만 하면 23개 공격 · 4개 스위트 · 4개 방어 · 토큰 계측이 공짜로 붙는다.**

`AutoGen` MAS가 `init_agents` + `bootstrap/step/conclude` 약 50줄인 점을 보면, **MAS 추가는 검증된 패턴**이다. → "뼈대는 다 있다"는 판단은 **이 계약을 따를 때 정확**하다.

### 12.2 결정적 지점 — 기존 7개 MAS는 "진짜 프레임워크"가 아니다

`autogen_mas.py`는 `pyautogen` 패키지를 호출하지 않고 2-에이전트 루프를 **손으로 재구현**한 것이다(나머지 6종도 동일 패턴, 논문 §4.4의 "MASLab 구현을 따름"). 따라서 **"CrewAI 추가"는 데이터/공격 문제가 아니라 설계 결정**이다.

| 항목 | A. CrewAI 토폴로지를 BaseAgent로 재구현 | B. 진짜 `crewai` 패키지 래핑 |
|---|---|---|
| 공격 적용 | 🟢 자동 (per-agent `run_step` 후킹점 존재) | 🔴 `crew.kickoff()`가 블랙박스 → **per-agent 후킹점 소멸**, injection/방어 미적용. 내부 브리징 필요 |
| 충실도(fidelity) | 🟡 "진짜 CrewAI인가" 논란 여지 | 🟢 높음 |
| 리포 정합성/비교가능성 | 🟢 나머지 6종과 동일 조건 | 🟡 조건 이질 |
| 난이도 | 낮음(~50줄 패턴) | 높음 |

저장소 설계는 **A를 강하게 유도**한다. 즉 "뼈대가 적절하다"는 명제는 **A를 택할 때만** 온전히 성립하며, B를 원하면 리포가 주는 도움이 거의 없다. **이 선택이 프로젝트 난이도를 좌우하므로 초기에 못 박아야 한다.**

### 12.3 "조금 부족"을 넘어서는 정량 평가 배관(plumbing)

Task 데이터·공격 다양성 외에, **새 MAS의 숫자를 신뢰 가능하게 만드는** 별도 작업이 필요하다:

| # | 항목 | 성격 | CrewAI 관점 영향 |
|---|---|---|---|
| 1 | **Verifier 취약성** | must-check (뼈대 아님) | `verify()`가 전부 문자열 매칭(`'safety_check' in ...`, `math_verify.parse(response)`)이라 **기존 MAS 출력 포맷에 종속**. CrewAI `conclude()`가 `answer["response"]`에 깨끗한 최종 답을 넣지 않으면 ASR/UA **오측정**. 소수 케이스 수동 검증 필수 |
| 2 | **LLM 배관** | 정합성 | `get_llm()`은 `provider=="openai"`만, `get_token_usage()`는 `agent.llm.input_tokens` 참조 → CrewAI 에이전트도 `OpenAILLM` 경유해야 토큰 계측·조건 일치 유지 |
| 3 | **데이터 규모** | 신뢰도 | 69개(math 39/code 30)를 per-surface로 쪼개면 셀당 n 극소 → 논문식 95% CI 붙이면 CrewAI 숫자가 **노이즈에 묻힘**. "조금 부족"보다 무겁게 봐야 함 |
| 4 | **Tool 주입 공격면 공백** | 커버리지 | `ToolInjectionAttack`은 정의만·등록 0개. CrewAI는 **도구·위임(delegation) 중심**이라 가장 흥미로운 공격면이 비어 있음 → 일반적 아쉬움이 아니라 **핵심 공격면 공백** |
| 5 | **PVI 부재** | 서사 완성 | CrewAI의 악성 에이전트 **위치별 전파 취약성** 특성화하려면 PVI + 토폴로지 거리 필요(현재 실행당 악성 에이전트 1개 고정). 중간 우선순위 |
| 6 | **`AnswerMappingAgent` 중복 등록** | 버그 | hijacking_math ASR **이중 카운트** → 숫자 신뢰 전 반드시 수정 |

### 12.4 프로젝트 관점 종합 판정

> **베이스로서 적절함(🟢).** 뼈대(에이전트 계약)는 새 MAS를 받기에 충분히 깨끗하고, MAS 추가 경로도 검증된 패턴이다.
>
> 단, 실제 노력·리스크는 지목된 "Task 데이터 + 공격 다양성"이 아니라 **(a) CrewAI 충실도 결정(재구현 vs 래핑)** 과 **(b) 새 MAS용 verifier/토큰 배관 검증**에 있다. 이 둘은 "빠진 뼈대"가 아니라 "새 시스템 통합 시 항상 드는 통합·검증 비용"이며, 데이터 규모는 정량 비교 신뢰도 측면에서 한 단계 더 무겁게 봐야 한다.

**한 줄 정리**: "뼈대는 충분하다"는 맞다. 남은 일이 '데이터·공격 채우기'라기보다 **'CrewAI를 어느 충실도로 붙일지 + 그 숫자를 신뢰 가능하게 만들지'** 라는 점을 초기에 확정하는 것이 프로젝트 성패를 가른다.

### 12.5 CrewAI 통합 시 착수 순서(권장)

| 우선 | 할 일 | 이유 |
|---|---|---|
| ★★★ | **충실도 노선 확정(A vs B)** | §12.2, 이후 모든 작업의 전제 |
| ★★★ | CrewAI를 `BaseAgent`/`BaseMAS` 계약으로 래핑(`init_agents`+`bootstrap/step/conclude`, `run_step` 경유) | 공격/방어/스위트 자동 연결 |
| ★★★ | `conclude()` 최종답 포맷 정합 + verifier 소수 케이스 수동 검증 | ASR/UA 오측정 방지(§12.3-1) |
| ★★☆ | `OpenAILLM` 경유 토큰 계측 배선 | `get_token_usage` 정합(§12.3-2) |
| ★★☆ | `AnswerMappingAgent` 중복 제거 | 숫자 신뢰(§12.3-6) |
| ★☆☆ | Tool 주입 공격 등록(선택) | CrewAI 도구 공격면 보강(§12.3-4) |
| ★☆☆ | 데이터 확장·PVI(선택, 비교 심화 시) | 통계 신뢰도·전파 서사(§12.3-3,5) |

---

## 부록. 갭 우선순위(구현 시 권장 순서)

| 우선 | 갭 | 이유 | 난이도 |
|---|---|---|---|
| ★★★ | 공격 자동생성 루프(§4.5) | 논문 핵심·규모 문제의 근원 | 高 |
| ★★★ | 데이터셋 확장(6개 벤치마크·4도메인) | 벤치마크 규모/일반화 | 中 |
| ★★☆ | PVI 지표 + 토폴로지 거리 계산 | 전파 서사 완성 | 中 |
| ★★☆ | QATask 도메인 배선(과학·의학) | 이미 클래스 존재, 배선만 | 低 |
| ★☆☆ | Tool/Memory 주입 공격 등록 | 공격면 커버리지 | 低 |
| ★☆☆ | AGrail·G-Safeguard 방어 | 방어 비교 재현 | 中 |
| ★☆☆ | `AnswerMappingAgent` 중복 제거 | 버그 정리 | 低 |

[^ds]: `aciarena/aciarena/evaluation/datasets/aciarena_math.json`(39), `aciarena_code.json`(30).
[^suite]: `aciarena/aciarena/evaluation/evaluation_suite.py` — `init_tasks()`는 math/code만, `@register_suite`는 benign/disruption/hijacking/disclosure.
[^dup]: `aciarena/aciarena/attacks/hijacking_attack.py` 라인 134·218에 동일 클래스명 `AnswerMappingAgent` 재정의.
[^mas]: `@register_mas`: agentverse, autogen, camel, llm_debate, mad, metagpt, sc.
[^contract]: `aciarena/aciarena/agent_components/base_agent.py`의 `run_step()`(pre_step→step→post_step) + `aciarena/aciarena/mas/base_mas.py`의 `bootstrap/step/conclude`·`get_agent`·`malicious_agents`·`get_token_usage`. 공격은 `attacks/base_attack.py`에서 `agent.step` 몽키패칭, 방어는 `evaluation/task_executor.py`의 `load_defense`에서 `pre_step`/`post_step` 몽키패칭.
