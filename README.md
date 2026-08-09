
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
```powershell
# Step 2: Run the evaluation pipeline

python3 benchmark.py --mas sc --suite disruption --task_domain math --malicious_agents aggregate --max_workers 1

```