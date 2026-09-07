## 결론

2026년 8월 23일 기준으로 공개 논문·arXiv·GitHub를 조사한 결과, **ACIArena를 CrewAI에 적용했다고 명시한 선행연구가 이미 1건 있습니다.**

따라서 앞으로 논문에서 **“최초로 ACIArena를 CrewAI에 적용했다”**고 주장하는 것은 위험합니다. 다만 해당 연구는 ACIArena 방식으로 CrewAI의 보안성을 종합 평가한 연구라기보다, **ACIArena에서 생성한 공격 실행 로그를 CASPIAN 탐지기의 평가 데이터로 사용한 연구**에 가깝습니다. 더구나 현재 공개 코드만으로는 CrewAI 실험을 재현하기 어렵습니다.

## 1. 직접적인 선행연구: CASPIAN

가장 중요한 논문은 다음 연구입니다.

> Kavana Venkatesh et al., “CASPIAN: Online Detection and Attribution of Cascade Attacks in LLM Multi-Agent Systems via Cross-Channel Causal Monitoring,” arXiv:2605.19240, 2026.

[CASPIAN 논문](https://arxiv.org/abs/2605.19240) · [논문 HTML](https://arxiv.org/html/2605.19240v1) · [공개 저장소](https://github.com/caspian-detector/caspian)

논문에서는 다음 네 MAS를 대상으로 TAMAS와 ACIArena 시나리오를 실행했다고 명시합니다.

- AutoGen
- CrewAI
- MetaGPT
- LLM Debate

이 중 AutoGen, MetaGPT, LLM Debate는 원래 ACIArena 논문에 포함되어 있지만, **CrewAI는 원래 ACIArena의 여섯 MAS에 포함되어 있지 않습니다.** 원 논문의 대상은 MetaGPT, AutoGen, CAMEL, Self Consistency, LLM Debate, AgentVerse입니다. [ACIArena 논문](https://aclanthology.org/2026.acl-long.457/)

### CASPIAN에서 사용한 ACIArena 범위

CASPIAN은 ACIArena 전체를 그대로 사용한 것이 아니라, 논문에서 `public MASPI instruction-injection subset`이라고 부르는 부분집합을 사용했습니다.

| 항목 | CASPIAN의 ACIArena 설정 |
|---|---:|
| Benign task | 69개 |
| 공격 시나리오 | 258개 |
| 전체 시나리오 | 327개 |
| 대상 MAS | 4개 |
| 최종 실행 trace | 1,308개 |
| 태스크 영역 | Math 39개, Code 30개 |
| 공격 클래스 | 8개 |

사용한 공격 클래스는 다음과 같습니다.

- Disclosure: `MathLocation`, `MathName`, `CodeApikey`, `CodeName`
- Disruption: `DDOS`
- Hijacking: `SafetyCheck`, `MaliciousReport`, `AnswerMapping`

즉, **CrewAI에 ACIArena의 69개 공개 태스크와 8개 공격 클래스를 적용한 실험은 논문상 이미 존재합니다.** [CASPIAN Appendix E](https://arxiv.org/html/2605.19240v1)

### 하지만 평가 목적이 다름

CASPIAN의 주된 연구 대상은 CrewAI의 취약성이 아니라 **CASPIAN 탐지기 자체의 탐지·귀속 성능**입니다.

사용한 지표도 ACIArena의 BU·UA·ASR·PVI가 아니라 다음과 같습니다.

- AUROC
- TPR@5% FPR
- EDR@5
- 공격 발원·증폭·중계 agent의 Acc@1과 MRR
- propagation spine 복원 정확도
- channel accuracy
- attribution lag

예를 들어 ACIArena × CrewAI 실험에서 다음 탐지 결과를 보고합니다.

| 공격 유형 | AUROC | TPR@5% FPR | EDR@5 |
|---|---:|---:|---:|
| Disclosure/Intent | 0.901 | 0.782 | 0.724 |
| Disruption/Execution | 0.927 | 0.821 | 0.761 |
| Hijacking/Coordination | 0.936 | 0.843 | 0.774 |

이 수치는 **CrewAI가 얼마나 취약한지를 나타내는 ASR이 아니라, CASPIAN이 공격 trace를 얼마나 잘 탐지했는지를 나타내는 값**입니다.

## 2. CASPIAN의 재현성 문제

CASPIAN 논문은 “lightweight adapter”를 통해 CrewAI 로그를 통합 trace로 변환했다고 설명하지만, 다음 정보는 충분히 공개되어 있지 않습니다.

- CrewAI 버전
- CrewAI agent의 role·goal·backstory
- Sequential 또는 Hierarchical process 구성
- manager agent 설정
- delegation 활성화 여부
- task context와 출력 전달 방식
- CrewAI 이벤트를 communication/memory/tool/execution 채널로 변환한 구체적인 adapter
- 공격을 어느 CrewAI 구성요소에 주입했는지에 대한 구현
- 공식 CrewAI와 재구현 간 동작 동등성 검증

더 중요한 점은 현재 [CASPIAN GitHub 저장소](https://github.com/caspian-detector/caspian)에 `images/`, `LICENSE`, `README.md`만 공개돼 있다는 것입니다. README에는 실행 명령이 있지만 다음 구성요소가 실제 저장소에 없습니다.

- `experiments/`
- `eval/`
- `configs/`
- `requirements.txt`
- CrewAI adapter 코드

또한 README의 ACIArena와 TAMAS clone 주소가 `github.com/your-org/...`라는 placeholder 상태입니다. 따라서 현재로서는 **논문의 실험 주장은 확인되지만, CrewAI 통합 구현을 독립적으로 재현하거나 정확성을 검증할 수 없는 상태**라고 판단하는 것이 타당합니다.

## 3. ACIArena를 직접 사용하지 않은 인접 선행연구

### TAMAS

[TAMAS](https://arxiv.org/abs/2511.05269)는 ACIArena보다 먼저 공개된 독립적인 MAS 보안 벤치마크입니다.

- 300개 adversarial instance
- 100개 harmless task
- 6개 공격 유형
- AutoGen과 CrewAI 평가
- CrewAI Sequential 및 Centralized 구성 비교
- 안전성과 정상 태스크 성능을 결합한 ERS 제안

특히 CrewAI의 centralized와 sequential 프로세스를 실제 비교했다는 점에서, 현재 연구의 가장 가까운 경쟁·비교 연구 중 하나입니다. 하지만 **ACIArena 데이터나 인터페이스를 사용한 연구는 아닙니다.** [TAMAS 논문 전문](https://arxiv.org/html/2511.05269v1)

### deep-xpia

[deep-xpia](https://github.com/freyzo/deep-xpia)는 delegation chain에서 발생하는 multi-hop cross-prompt injection을 다루는 공개 소프트웨어 벤치마크입니다.

ACIArena를 관련 연구로 인용하고 `aciarena_mapping.yaml`을 제공하지만, 현재 구조상 ACIArena 태스크를 CrewAI에 실행한 연구는 아닙니다. README에서도 CrewAI·AutoGen adapter는 구현 완료 기능이라기보다 향후 기여 대상으로 제시됩니다.

## 4. 공개 코드 파생 사례

[ACIArena 공식 저장소](https://github.com/Greysahy/aciarena)는 현재 공개적으로 확인되는 fork가 2개이고, 이 중 확인 가능한 [NESA-Lab fork](https://github.com/NESA-Lab/aciarena)는 원본을 복제한 수준으로 보이며 CrewAI 확장은 없습니다.

공개 PR·fork·파생 저장소 중에서는 CASPIAN 외에 새로운 MAS를 실제 추가하여 결과까지 보고한 사례를 찾지 못했습니다. 다만 비공개 프로젝트나 아직 검색 색인에 포함되지 않은 작업까지 없다고 단정할 수는 없습니다.

## 연구에 미치는 영향

현재 연구는 다음과 같이 위치시키는 것이 안전합니다.

> “CrewAI를 ACIArena에 최초 적용”이 아니라,  
> **“CrewAI의 실행 의미론을 보존하고 검증 가능한 형태로 ACIArena에 통합하여, ACI 위협에 대한 utility–security 특성을 체계적으로 평가”**

특히 다음 요소를 포함하면 CASPIAN과 명확하게 구별됩니다.

- CASPIAN의 8개 공격보다 넓은 ACIArena 공격군 적용
- BU·UA·ASR 중심의 CrewAI 취약성 평가
- 가능한 경우 PVI 또는 agent/edge 단위 전파 분석
- Sequential과 Hierarchical 비교
- delegation on/off 비교
- manager·worker 등 공격 agent 위치별 비교
- 공식 CrewAI 실행과 ACIArena용 재구현의 동등성 검증
- CrewAI 버전, 프롬프트 조립, context 전달, delegation 과정을 모두 공개
- 재현 가능한 코드·설정·raw trace 제공

핵심적으로, **CASPIAN은 “ACIArena trace에서 공격을 탐지할 수 있는가”를 묻고 있고, 현재 연구는 “CrewAI의 어떤 구조적 특성이 ACI 취약성을 만들거나 완화하는가”를 물을 수 있습니다.** 이 차이를 연구 질문과 기여점에 명시하는 것이 가장 중요합니다.
