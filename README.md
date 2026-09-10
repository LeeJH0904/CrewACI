
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

> 아래 실행 예시에서 `[]`로 감싼 옵션은 생략 가능(기본값 사용)하고, 감싸지 않은 옵션은 그 예시에서 필수다. crewai 공격 예시의 `--task_domain`은 `--attack_ids`의 domain과 일치해야 하므로 필수로 둔다.

```bash
python3 benchmark.py \
  --mas sc \
  [--suite disruption] \
  [--attack_mode continuous] \
  [--defense none] \
  [--task_domain math] \
  [--max_workers 1] \
  [--output_dir logs] \
  [--malicious_agents aggregate]
```

| 옵션 | 선택 가능 값 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `--mas` | `autogen`, `agentverse`, `camel`, `llm_debate`, `mad`, `metagpt`, `sc`, `crewai_seq_nodeleg` | `autogen` | 평가에 사용할 멀티 에이전트 시스템 구조를 지정합니다. `crewai_seq_nodeleg`는 CrewAI 방식의 순차형(비위임) 구조입니다. |
| `--suite` | `benign`, `disruption`, `hijacking`, `disclosure` | `hijacking` | 평가 또는 공격 유형을 지정합니다. `benign`은 공격 없이 평가합니다. |
| `--attack_mode` | `continuous` | `continuous` | 공격 실행 방식을 지정합니다. 현재는 `continuous`만 등록되어 있습니다. |
| `--defense` | `none`, `aci_sentinel`, `delimiter`, `bert_detector`, `sandwich` | `none` | 에이전트의 입력 또는 출력에 적용할 방어 기법을 지정합니다. |
| `--task_domain` | `math`, `code` | `code` | 평가 데이터셋의 도메인을 지정합니다. `metagpt`는 `math`를 지원하지 않습니다. |
| `--max_workers` | 양의 정수 | `4` | 동시에 처리할 평가 작업 수를 지정합니다. API 사용량 제한이 낮다면 값을 줄이세요. |
| `--output_dir` | 디렉터리 경로 | `logs` | 상세 MAS 로그를 저장할 디렉터리입니다. 종합 `result.json`은 `logs/<model>/<domain>/<mas>/<suite>/` 아래에 저장됩니다. |
| `--malicious_agents` | 하나 이상의 에이전트 이름 | MAS별 기본값 | 공격에 의해 악성으로 동작할 에이전트를 지정합니다. 여러 이름은 공백으로 구분합니다. |



### 이번 연구 중 추가된 옵션

아래 옵션은 ACIArena 원본에는 없고 본 연구(CrewAI 통합·G0)에서 추가한 것으로, 위 원본 옵션 표와 구분한다. `crewai 전용` 옵션은 `--mas crewai_seq_nodeleg`의 recorded 경로에서만 의미가 있고, 다른 MAS에서는 무시되거나 legacy 경로에 적용된다.

| 옵션 | 값 · 기본값 | 추가 시점 | 적용 범위 | 설명 |
| --- | --- | --- | --- | --- |
| `--limit` | 양의 정수 · 없음 | 2026-08-31 (CrewAI 통합) | 전체 MAS | 빠른 검증용으로 평가 태스크 수를 제한한다. 미지정 시 전체 태스크를 평가한다. |
| `--attack_ids` | manifest attack ID 하나 이상 · 없음 | G0 | crewai 전용 | recorded 경로에서 실행할 대표 공격 ID를 명시한다. 공격 suite면 **필수**이며 `<category>.<surface>.v1` 형식이다. |
| `--experiment_id` | 디렉터리 안전 문자열 · 없음 | G0 | crewai 전용 | 출력 `<output_dir>/<experiment_id>/{runs,messages}.jsonl` 의 실험 식별자. |
| `--experiment_config` | YAML 경로 · `configs/experiments/core.yaml` | G0 | crewai 전용 | G0 개발 계약(단일 출처). model/Judge 개별 override를 거부한다. |
| `--phase` | `calibration`·`pilot`·`core`·`confirmation` · `pilot` | G0 | crewai 전용 | 기록할 실행 단계(run_id 결정 요소). |
| `--repetition` | 양의 정수 · `1` | G0 | crewai 전용 | 확인 반복 번호(run_id 결정 요소). |
| `--resume` | 플래그 · off | G0 | crewai 전용 | 완료된 run(정상 false 판정 포함)을 재사용해 건너뛴다. |
| `--retry_errors` | 플래그 · off | G0 | crewai 전용 | 기록된 일시적 provider/timeout 오류만 총 3시도까지 재시도한다. |

> ⚠️ **`crewai_seq_nodeleg`의 `--suite` / `--attack_ids` 주의**
> - `--suite` 기본값은 `hijacking`(공격 suite)이다. crewai에서 `--suite`를 생략하면 공격 suite로 잡히지만 `--attack_ids`가 없어 `Select unique --attack_ids explicitly for an attack suite` 오류가 난다.
> - 따라서 crewai는 **정상이면 `--suite benign`**, **공격이면 `--suite <goal> --attack_ids <id>`** 를 명시해야 한다. attack_id의 goal이 suite와 다르면 `attack_id and suite disagree` 오류다. (예: Math hijacking → `--suite hijacking --attack_ids hijacking_answer_mapping.agent.v1`)
> - 이는 recorded 경로 전용 계약이다. 다른 MAS(legacy)는 종전대로 `--suite`만으로 공격을 자동 선택하며 `--attack_ids`가 필요 없다.

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
.aciarena/bin/python benchmark.py --mas crewai_seq_nodeleg --suite benign [--task_domain math] [--limit 1] [--experiment_id test1] [--output_dir logs]


# 공격 실행 — --suite 와 일치하는 --attack_ids 를 함께 명시
.aciarena/bin/python benchmark.py --mas crewai_seq_nodeleg --suite hijacking --task_domain math --attack_ids hijacking_answer_mapping.agent.v1 [--limit 1] [--experiment_id test1] [--output_dir logs]

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

**이제 모든 로그는 '--experiment_id' 옵션으로 지정한 이름으로 만들어지는 logs/~ 폴더에 저장됩니다.**
* '--experiment_id' 옵션을 지정하지 않으면 자동으로 [crewai-development-v1]로 생성됩니다.
* 각 실험 폴더에는 `runs.jsonl`·`messages.jsonl` 외에 `configs/<hash>.json`(설정 스냅샷)·`.writer.lock`·`.run_locks/`가 함께 생성되며, 같은 `--experiment_id`로 다시 실행하면 기존 파일에 append(누적)됩니다.

```text
runs.jsonl = "무엇이 나왔나(결과)"
messages.jsonl = "어떻게 나왔나(과정)"

위 둘은 run_id로 join됨
```
