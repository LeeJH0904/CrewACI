
---
## 🔧 Installation

```bash
# 디렉토리 생성
mkdir ACIArena
cd ./ACIArena

# Step 1: 가상환경 세팅
# conda create -n aciarena python=3.10
# conda activate aciarena

sudo apt update
sudo apt install -y python3 python3-venv
python3 -m pip install python-dotenv

python3 -m venv .aciarena
source .aciarena/bin/activate 

# Step 2: 리포지토리 클론
git clone https://github.com/LeeJH0904/CrewACI.git
cd CrewACI

# Step 3: 의존성 설치
sudo apt install python3-pip
pip install -e .
pip install torch

# 가상환경 종료 시
deactivate
```

## 🚀 Quickstart

### 1. Set up the API keys for both the agent model and the judge model.
See `configs/judge.yaml` and `configs/model.yaml`

```yaml
# openai API 사용할 경우
provider: openai
api_key: <your_api_key>
base_url: <your_base_url>
model_name: <your_model_name>
temperature: 0.0
max_tokens: 1024
```

### 2. Run Evaluation
```bash
# Step 2: Run the evaluation pipeline

python3 benchmark.py --mas sc --suite disruption --task_domain math --malicious_agents aggregate --max_workers 1
```

### 명령행 옵션

```bash
python3 benchmark.py \
  --mas sc \
  --suite disruption \
  --attack_mode continuous \
  --defense none \
  --task_domain math \
  --max_workers 1 \
  --output_dir logs \
  --malicious_agents aggregate
```

| 옵션 | 선택 가능 값 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `--mas` | `autogen`, `agentverse`, `camel`, `llm_debate`, `mad`, `metagpt`, `sc` | `autogen` | 평가에 사용할 멀티 에이전트 시스템 구조를 지정합니다. |
| `--suite` | `benign`, `disruption`, `hijacking`, `disclosure` | `hijacking` | 평가 또는 공격 유형을 지정합니다. `benign`은 공격 없이 평가합니다. |
| `--attack_mode` | `continuous` | `continuous` | 공격 실행 방식을 지정합니다. 현재는 `continuous`만 등록되어 있습니다. |
| `--defense` | `none`, `aci_sentinel`, `delimiter`, `bert_detector`, `sandwich` | `none` | 에이전트의 입력 또는 출력에 적용할 방어 기법을 지정합니다. |
| `--task_domain` | `math`, `code` | `code` | 평가 데이터셋의 도메인을 지정합니다. `metagpt`는 `math`를 지원하지 않습니다. |
| `--max_workers` | 양의 정수 | `4` | 동시에 처리할 평가 작업 수를 지정합니다. API 사용량 제한이 낮다면 값을 줄이세요. |
| `--output_dir` | 디렉터리 경로 | `logs` | 상세 MAS 로그를 저장할 디렉터리입니다. 종합 `result.json`은 `logs/<model>/<domain>/<mas>/<suite>/` 아래에 저장됩니다. |
| `--malicious_agents` | 하나 이상의 에이전트 이름 | MAS별 기본값 | 공격에 의해 악성으로 동작할 에이전트를 지정합니다. 여러 이름은 공백으로 구분합니다. |

#### `--malicious_agents`에서 사용할 수 있는 에이전트 이름

지정하는 값은 선택한 `--mas`에 속한 에이전트 이름과 일치해야 합니다.

| `--mas` | 선택 가능한 에이전트 이름 | 기본 악성 에이전트 |
| --- | --- | --- |
| `autogen` | `assistant`, `user_proxy` | `assistant` |
| `agentverse` | `role_assigner`, `solver`, `evaluator`, `critic_0` | `solver` |
| `camel` | `assistant`, `user_proxy`, `critic`, `task_specifier` | `assistant` |
| `llm_debate` | `debater_0`, `debater_1`, `debater_2`, `aggregator` | 없음 |
| `mad` | `affirmative`, `negative`, `moderator`, `judge` | `negative` |
| `metagpt` | `product_manager`, `architect`, `project_manager`, `engineer`, `qa_engineer` | `product_manager` |
| `sc` | `sc1`, `sc2`, `sc3`, `sc4`, `sc5`, `aggregate` | `sc1` |

다음과 같이 악성 에이전트를 여러 개 지정할 수도 있습니다.

```bash
python3 benchmark.py --mas sc --suite disruption --task_domain math \
  --malicious_agents sc1 aggregate --max_workers 1
```

일부 후속 검사에서는 옵션값의 대소문자를 구분하므로 위 표에 표시된 소문자 값을 사용하세요.
