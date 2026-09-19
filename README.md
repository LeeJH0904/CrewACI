
> 📌 연구 계획·가이드는 [`CrewAI_ACIArena_연구계획/`](CrewAI_ACIArena_연구계획/README.md)에 있다. 개발·검증 중 새 결정(범위·지표·구성·설정)이 생기면 즉시 [`DECISIONS.md`](DECISIONS.md)에 결정일·근거·영향과 함께 추가한다.

> 각 단계별로 진행된 개발 내용은 'CrewACI/구현문서/~' 폴더 내부에 각 단계별 문서로 하여 정리한다.

---
## 🔧 Installation

```bash

git clone https://github.com/LeeJH0904/CrewACI.git
cd CrewACI

# 가상환경 세팅
# conda create -n aciarena python=3.10
# conda activate aciarena

sudo apt update
sudo apt install -y python3 python3-pip python3-venv

python3 -m venv .aciarena
source .aciarena/bin/activate 

# 의존성 설치
pip install -e .
pip install torch python-dotenv

# 가상환경 종료 시
deactivate
```

## 🚀 Quickstart

### 1. Set up the API keys for both the agent model and the judge model.
See `configs/judge.yaml` and `configs/model.yaml`

```yaml
# openai API 사용할 경우
provider: openai
base_url: <your_base_url>
model_name: <your_model_name>
temperature: 0.0
max_tokens: 1024
```

# .env 파일 생성 후
```
OPENAI_API_KEY=sk000
```

### 2. Run Evaluation

```bash
# Step 1: LM Studio (Bionic) 실행

Bionic 실행하여 API활성화 확인 후 진행

# Step 2: Run the evaluation pipeline

python3 benchmark.py --mas sc [--suite disruption] [--task_domain math] [--malicious_agents aggregate] [--max_workers 1]
```


### 기본 명령행 옵션

> 아래 실행 예시에서 `[]`로 감싼 옵션은 생략 가능(기본값 사용)하고, 감싸지 않은 옵션은 그 예시에서 필수다. crewai 공격 예시의 `--task_domain`은 domain 선택을 위해 필수로 둔다(`--attack_ids`를 지정하면 그 domain과 일치해야 한다).

```bash
python3 benchmark.py \
  --mas sc \
  [--suite disruption] \
  [--attack_mode continuous] \
  [--defense none] \
  [--task_domain math] \
  [--max_workers 1] \
  [--output_dir outputs/g7] \
  [--malicious_agents aggregate]
```

| 옵션 | 선택 가능 값 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `--mas` | `autogen`, `agentverse`, `camel`, `llm_debate`, `mad`, `metagpt`, `sc`, `crewai_seq_nodeleg` | `autogen` | 평가에 사용할 멀티 에이전트 시스템 구조를 지정합니다. `crewai_seq_nodeleg`는 CrewAI 방식의 순차형(비위임) 구조입니다. |
| `--suite` | `benign`, `disruption`, `hijacking`, `disclosure` | `hijacking` | 평가 또는 공격 유형을 지정합니다. `benign`은 공격 없이 평가합니다. |
| `--attack_mode` | `continuous` | `continuous` | 공격 실행 방식을 지정합니다. 현재는 `continuous`만 등록되어 있습니다. |
| `--defense` | `none`, `aci_sentinel`, `delimiter`, `bert_detector`, `sandwich` | `none` | 에이전트의 입력 또는 출력에 적용할 방어 기법을 지정합니다. |
| `--task_domain` | `math`, `code` | `code` | 평가 데이터셋의 도메인을 지정합니다. `metagpt`는 `math`를 지원하지 않습니다. |
| `--max_workers` | 양의 정수 | `1` | 동시에 처리할 평가 작업 수를 지정합니다. G7 legacy 경로는 결정성 보장을 위해 `1`만 허용합니다. |
| `--output_dir` | 디렉터리 경로 | `outputs/g7` | per-row 기록(`runs.jsonl`·`messages.jsonl`)을 저장할 루트입니다. 실제 저장 위치는 `<output_dir>/<experiment_id>/` 이며, 동결 경로(`outputs/g5-v2`·`outputs/g6`) 하위 쓰기는 거부됩니다. |
| `--malicious_agents` | 하나 이상의 에이전트 이름 | MAS별 기본값 | 공격에 의해 악성으로 동작할 에이전트를 지정합니다. 여러 이름은 공백으로 구분합니다. |



### 이번 연구 중 추가된 옵션

아래 옵션은 ACIArena 원본에는 없고 본 연구(CrewAI 통합·G0)에서 추가한 것으로, 위 원본 옵션 표와 구분한다. `crewai 전용` 옵션은 `--mas crewai_seq_nodeleg`의 recorded 경로에서만 의미가 있고, 다른 MAS에서는 무시되거나 legacy 경로에 적용된다.

| 옵션 | 값 · 기본값 | 추가 시점 | 적용 범위 | 설명 |
| --- | --- | --- | --- | --- |
| `--execute` | 플래그 · off | G7 | 전체 MAS | 실모델 호출을 허용한다. 생략 시 기본은 계획만 출력하는 **0-call dry-run**이다. |
| `--limit` | 양의 정수 · 없음 | 2026-08-31 (CrewAI 통합) | 전체 MAS | 빠른 검증용으로 평가 태스크 수를 제한한다. 미지정 시 전체 태스크를 평가한다. `--task_ids`와 동시 사용 불가. |
| `--task_ids` | manifest task ID 하나 이상 · 없음 | G7 | 전체 MAS | 실행할 정확한 task ID를 지정한다. `--limit`와 함께 쓸 수 없다. |
| `--attack_ids` | manifest attack ID 하나 이상 · 없음 | G0 | crewai + G7 legacy | 실행할 공격 ID. **생략 시 선택한 `--suite`(목표)의 해당 domain attack이 전부 자동 선택**되고, 지정 시 그 목표 내 부분집합만 실행한다(**crewai·legacy 동일**). `<category>.<surface>.v1` 형식이며 attack_id의 goal은 `--suite`와 일치해야 한다. |
| `--experiment_id` | 디렉터리 안전 문자열 · 없음 | G0 | crewai + G7 legacy | 출력 `<output_dir>/<experiment_id>/{runs,messages}.jsonl` 의 실험 식별자. 미지정 시 `g7-cross-mas-v1`. |
| `--experiment_config` | YAML 경로 · `configs/experiments/g5_v2.yaml` | G0 | crewai 전용 | 개발 계약(단일 출처). model/Judge 개별 override를 거부한다. |
| `--phase` | `calibration`·`pilot`·`core`·`confirmation` · `core` | G0 | crewai + G7 legacy | 기록할 실행 단계(run_id 결정 요소). |
| `--repetition` | 양의 정수 · `1` | G0 | crewai + G7 legacy | 확인 반복 번호(run_id 결정 요소). |
| `--resume` | 플래그 · off | G0 | crewai + G7 legacy | 완료된 run(정상 false 판정 포함)을 재사용해 건너뛴다. |
| `--retry_errors` | 플래그 · off | G0 | crewai + G7 legacy | 기록된 일시적 provider/timeout 오류만 총 3시도까지 재시도한다. |

> ℹ️ **`crewai_seq_nodeleg`의 `--suite` / `--attack_ids`**
> - `--suite` 기본값은 `hijacking`(공격 suite)이다. 정상 평가는 `--suite benign`으로 실행한다.
> - `--attack_ids`는 **생략 가능**하다. 생략하면 선택한 `--suite`(목표)의 해당 domain attack이 **전부 자동 선택**된다(현재 benchmark.py의 G7 경로에서 crewai·legacy 모두 동일). 부분집합만 돌릴 때만 명시한다.
> - `--attack_ids`를 지정하는 경우 그 goal이 `--suite`와 달라선 안 된다(`attack_id and suite disagree` 오류). 예: Math hijacking 일부만 실행 → `--suite hijacking --attack_ids hijacking_answer_mapping.agent.v1`.

상세 CLI·출력·격리 계약은 [manifest·CLI 가이드](manifests/README.md#crewai-실행-cli-g0-개발-경로)를 따른다.



#### `--malicious_agents`에서 사용할 수 있는 에이전트 이름

지정하는 값은 선택한 `--mas`에 속한 에이전트 이름과 일치해야 합니다.

[⚠️ crewai_seq_nodeleg 는 개발중인 옵션임.]

| `--mas` | 선택 가능한 에이전트 이름 | 기본 악성 에이전트 |
| --- | --- | --- |
| `autogen` | `assistant`, `user_proxy` | `assistant` |
| `agentverse` | `role_assigner`, `solver`, `evaluator`, `critic_0` | `solver` |
| `camel` | `assistant`, `user_proxy`, `critic`, `task_specifier` | `assistant` |
| `llm_debate` | `debater_0`, `debater_1`, `debater_2`, `aggregator` | 없음 |
| `mad` | `affirmative`, `negative`, `moderator`, `judge` | `negative` |
| `metagpt` | `product_manager`, `architect`, `project_manager`, `engineer`, `qa_engineer` | `product_manager` |
| `sc` | `sc1`, `sc2`, `sc3`, `sc4`, `sc5`, `aggregate` | `sc1` |
| `crewai_seq_nodeleg` | `solver`, `reviewer`, `finalizer` | `solver` |


다음과 같이 악성 에이전트를 여러 개 지정할 수도 있습니다.

```bash
python3 benchmark.py --mas sc [--suite disruption] [--task_domain math] [--malicious_agents sc1 aggregate] [--max_workers 1]

# or

python benchmark.py --mas sc [--task_domain math] [--max_workers 1]

# crewai_seq_nodeleg 실행 예시 (recorded 경로 — --suite 를 반드시 명시)
# [] 내부 옵션은 생략 가능 옵션임. 실제 사용 시에는 [] 제거 후 사용 

# 실행
.aciarena/bin/python benchmark.py --mas crewai_seq_nodeleg --suite benign [--task_domain math] [--limit 1] [--experiment_id test1] [--output_dir outputs/g7]


# 공격 실행 — --attack_ids는 생략 가능(생략 시 목표 전체 자동). 아래는 일부만 돌리는 예시
.aciarena/bin/python benchmark.py --mas crewai_seq_nodeleg --suite hijacking --task_domain math [--attack_ids hijacking_answer_mapping.agent.v1] [--limit 1] [--experiment_id test1] [--output_dir outputs/g7]

```

### CrewAI G2 recorded 실행·감사

`crewai_seq_nodeleg`는 이제 recorded 실행기를 거친다. run마다 객체를 새로 만들고,
`runs.jsonl` / `messages.jsonl`에 기록하며, 설정 스냅샷과 명시적 attack ID를 남긴다.
자세한 내용은 [CLI·manifest 가이드](manifests/README.md#crewai-실행-cli-g0-개발-경로)와
[오프라인 검증](tests/README.md)을 참조한다. Linux x86_64에서는 Code utility가
namespace/Landlock/seccomp/rlimit 격리(sandbox) 안에서 실행된다. 해당 커널 제어를
적용할 수 없으면 생성된 코드를 실행하지 않고 `CodeSandboxUnavailable`을 기록한다.
recorded CLI는 `configs/experiments/core.yaml`을 단일 G0 개발 계약으로 읽고, 여기서
참조하는 model·Judge·retry·verifier·dependency lock을 검증한다.
G2부터 각 실행 결과를 반환하기 전에 선택한 task/attack 계획과 JSONL·config·주입
증거를 함께 감사한다. 전체 기록은 아래 명령으로 manifest matrix와 다시 대조할 수 있다.
**즉, audit_records.py는 벤치마크 기록의 무결성 검사 도구입니다.**

```bash
.aciarena/bin/python scripts/audit_records.py \
  --experiment_id <experiment-id> --output_dir logs \
  --matrix core-attacks --allow_additional
```

**이제 모든 로그는 `<output_dir>/<experiment_id>/` 폴더에 저장됩니다(`--output_dir` 기본값 `outputs/g7`).**
* '--experiment_id' 옵션을 지정하지 않으면 자동으로 [g7-cross-mas-v1]로 생성됩니다.
* 각 실험 폴더에는 `runs.jsonl`·`messages.jsonl` 외에 `configs/<hash>.json`(설정 스냅샷)·`.writer.lock`·`.run_locks/`가 함께 생성되며, 같은 `--experiment_id`로 다시 실행하면 기존 파일에 append(누적)됩니다.

```text
runs.jsonl = "무엇이 나왔나(결과)"
messages.jsonl = "어떻게 나왔나(과정)"

위 둘은 run_id로 join됨
```

### CrewAI G5/G6 통합 실행·집계

연구 단계 실행은 manifest 기반 통합 오케스트레이터를 사용한다. 기본 동작은 계획만
출력하는 **0-call dry-run**이며, `--suite`는 해당 manifest의 attack ID로 확장된다.

```bash
# 예: G5-v2 Math hijacking 계획 확인 — 모델/API 호출 없음
.aciarena/bin/python scripts/run_experiment.py \
  --config configs/experiments/g5_v2.yaml \
  --stage core --matrix attacks --domain math --suite hijacking

# 동결 G5-v2 원본을 read-only로 재감사·재집계
.aciarena/bin/python scripts/aggregate_results.py
```

`--execute`를 붙이면 실제 모델 호출 경로에 진입한다. 동결된 G5-v2는 재실행하지 않는다.
G7 유료 실행은 D64에 따라 사전 비용 산정·승인 게이트 없이 per-invocation으로 진행한다
(기본은 dry-run이며 유료 호출은 `--execute` 명시 시에만 발생). G6 최종 보고서는
[`outputs/g6/crewai-g5-final-v2/g6_report.md`](outputs/g6/crewai-g5-final-v2/g6_report.md),
구현·분모·통계 계약은 [`구현문서/G6_구현_기록.md`](구현문서/G6_구현_기록.md)에 있다.

### CrewAI G7 cross-MAS 통합 벤치·집계

G7은 논문 6종(MAD 제외)과 CrewAI를 **동일한 per-row 스키마**로 기록해 나란히 비교하는
단계다. legacy MAS는 `benchmark.py`의 recording 어댑터를 거치고, CrewAI는 기존 recorded
계약을 그대로 쓴다. 실행은 **per-invocation**으로, `MAS × task_domain(math|code) × suite(목표)`
슬라이스를 하나씩 돌려 `outputs/g7/<experiment_id>/`에 누적한다. 기본은 0-call dry-run이며
`--execute` 명시 시에만 유료 경로에 진입한다. 대상 agent·task/attack ID는 결과를 보기 전
`manifests/g7/{systems,targets,identifiers}.json`에 결정적으로 고정된다.

```bash
# 계획 확인 — 모델/API 호출 없음(0-call dry-run)
.aciarena/bin/python benchmark.py --mas camel --task_domain math --suite hijacking

# 한 슬라이스 실측 — 유료(--execute), 결과는 outputs/g7/<experiment_id>/ 에 저장
.aciarena/bin/python benchmark.py --mas camel --task_domain math --suite hijacking --limit 2 --execute --experiment_id g7-pilot
```

집계는 수집된 원본을 read-only로 읽어 CrewAI·legacy에 동일 규칙을 적용한다(paired 검정·
순위표 없음, 시스템별 task-cluster bootstrap CI). 예정 6,426 조건이 완결되어야 정식 리포트를
쓰며, 미완결 상태의 파일 산출은 `--allow-partial-write`를 명시해야 한다.

```bash
# read-only 집계 미리보기(파일 미생성)
.aciarena/bin/python scripts/aggregate_g7.py --records-dir outputs/g7/g7-pilot

# G6 동결 산출물 read-only 무결성 재검증
.aciarena/bin/python scripts/verify_g6_frozen.py
```

단계·결정 근거는 [`CrewAI_ACIArena_연구계획/07_G7_구현단계.md`](CrewAI_ACIArena_연구계획/07_G7_구현단계.md),
구현 기록은 [`구현문서/G7_구현_기록.md`](구현문서/G7_구현_기록.md)에 있다.

### CrewAI G3 공식 runtime 기능 대조

G3는 고정된 정상 태스크 10개를 재구현과 공식 CrewAI 1.15.21에서 각각 실행해 총 20 rows를
비교하는, 재구현 충실도 검증 단계다. 공식 패키지는 본 벤치 runtime에 섞지 않고 `.native-crewai`
별도 환경에서만 쓰며, 본 벤치 라이브러리(패키징)에는 포함되지 않는다. `g3-sequential-calibration-v2`에서
양쪽 10/10 완료, context/Finalizer source 전수 확인, parse 성공률 100% 대 90%(차이 10 percentage
points)로 **G3 Gate를 통과했다**(비교 가능한 9쌍의 utility disagreement 0건, 성능 동등성 증명은 아님).

설치·실행 순서·옵션·산출물·판정 기준은 [`native_reference/README.md`](native_reference/README.md)를 참고한다.
