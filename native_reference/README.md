# G3: 공식 CrewAI ↔ 재구현 기능 대조 (calibration)

## 이 폴더가 하는 일

같은 10개 태스크를 **공식 CrewAI**와 **우리 재구현(ACIArena에 추가한 CrewAI MAS)** 양쪽으로 각각 실행한 뒤,
두 결과를 **동일한 ACIArena verifier**로 채점해 "우리 재구현이 공식 CrewAI와 구조적으로 같게 동작하는가"를 확인(calibration, 검증)합니다. 
성능 우열을 가리는 단계가 **아니라**, 재구현의 충실도(fidelity)를 검증하는 단계입니다.

이 하니스는 **본 벤치마크(배포 라이브러리)의 일부가 아닙니다.** `setup.py`에서 패키징 제외되며, G3 검증에만 씁니다.

## 왜 파이썬 환경이 두 개인가

공식 CrewAI(`crewai==1.15.21`)를 메인 벤치 환경(`.aciarena`)에 섞으면 의존성이 오염됩니다.
그래서 native 쪽만 **격리된 별도 환경(`.native-crewai`)**에서 돌립니다.

| 역할 | 실행 환경 | 설명 |
|---|---|---|
| `reconstructed` (우리 재구현) | `.aciarena` | 메인 벤치 환경. 우리 `CrewAISequentialNoDelegation`을 직접 실행 |
| `native` (공식 CrewAI) | `.native-crewai` | 격리 환경. 공식 `crewai==1.15.21`로 실행 |
| `compare` (비교·채점) | `.aciarena` | 두 결과를 공통 verifier로 재채점 |

두 환경은 `native_reference/requirements.lock`(exact pin)으로 재현합니다. 재현의 근거는 이 lock 파일이지
`.native-crewai` 디렉터리 자체가 아니므로, 이 venv는 커밋하지 않습니다(`.gitignore` 처리됨).

## 사전 준비물

1. **로컬 OpenAI 호환 엔드포인트 실행.** 양쪽 모두 `configs/model.yaml`의 모델을 호출합니다.
   현재 설정은 LM Studio 등에서 띄우는 로컬 서버입니다 (유료 API 비용 0):

   ```yaml
   # configs/model.yaml
   provider: openai
   base_url: http://127.0.0.1:1234/v1
   model_name: qwen2.5-0.5b-instruct
   temperature: 0.0
   max_tokens: 1024
   seed: 42
   ```

   실행 전 이 주소에서 해당 모델이 응답하는지 먼저 확인하세요. (temperature는 반드시 0.0이어야 하며, 아니면 실행이 거부됩니다.)

2. **메인 환경 `.aciarena`** 가 이미 세팅되어 있어야 합니다(본 저장소 기본 개발 환경).

3. 모든 명령은 **저장소 루트(`CrewACI/`)에서** 실행합니다. (출력 경로 `outputs/g3`가 현재 디렉터리 기준입니다.)

## 실행 순서

### 0단계 — (최초 1회) 격리 환경 만들기

```bash
python3 -m venv .native-crewai
.native-crewai/bin/pip install -r native_reference/requirements.lock
```

설치 확인:

```bash
.native-crewai/bin/python -c "import crewai; print(crewai.__version__)"   # → 1.15.21
```

### 1단계 — 재구현(reconstructed) 실행  ·  환경: `.aciarena`

```bash
.aciarena/bin/python -m native_reference.run_calibration \
  --implementation reconstructed \
  --experiment_id g3-sequential-calibration-v2
```

### 2단계 — 공식 CrewAI(native) 실행  ·  환경: `.native-crewai`

앞의 환경변수들은 공식 CrewAI의 **텔레메트리/트레이싱 네트워크 호출을 끄고**, 저장소를 임시 디렉터리로 **격리**하기 위한 것입니다.

```bash
CREWAI_DISABLE_TELEMETRY=true \
CREWAI_TRACING_ENABLED=false \
OTEL_SDK_DISABLED=true \
CREWAI_STORAGE_DIR=/tmp/crewai-g3-reference \
.native-crewai/bin/python -m native_reference.run_calibration \
  --implementation native \
  --experiment_id g3-sequential-calibration-v[n]
```

### 3단계 — 비교·채점  ·  환경: `.aciarena`

```bash
.aciarena/bin/python -m native_reference.compare_calibration \
  --experiment_id g3-sequential-calibration-v2
```

## 결과 읽는 법

산출물은 `outputs/g3/<experiment_id>/` 아래에 쌓입니다:

| 파일 | 내용 |
|---|---|
| `reconstructed.jsonl` | 재구현 실행 기록(태스크당 1줄) |
| `native.jsonl` | 공식 CrewAI 실행 기록(태스크당 1줄) |
| `comparison.json` | 비교 결과 전체(기계 판독용). `gate_passed` 필드가 최종 판정 |
| `comparison.md` | 사람이 읽는 요약표 |
| `.calibration.lock` | 실행 중 생성되는 락 파일(gitignore 대상) |

각 기록에는 role/goal/backstory, Task·context 선언, **실제 LLM 입력과 응답**, task별 출력, 최종 응답 source,
호출 수·토큰 usage·소요 시간·오류가 담깁니다. API key는 기록하지 않습니다.

### 통과(Gate) 기준

`comparison.json`의 `"gate_passed": true`가 되려면 다음을 **모두** 만족해야 합니다.

- 10개 태스크를 **양쪽 모두** 실행한 20개 row (완료율 각 100%)
- 호출 순서(solver→reviewer→finalizer)·context 전달·최종 source 검사 **전수 통과**
- 두 구현의 **parse 성공률 차이 ≤ 10 percentage points**

utility(정답 여부) 성공은 Gate 조건이 **아닙니다.** 작은 로컬 모델이라 정답률이 낮아도 됩니다.
대신 비교 가능한 쌍에서의 **task-level utility disagreement를 보고만** 합니다(성능 동등성 주장이 아님).

## 옵션

| 옵션 | 대상 스크립트 | 용도 |
|---|---|---|
| `--experiment_id <id>` | 양쪽 | 실행 세트 이름(출력 폴더명). 기본 `g3-sequential-calibration-v2` |
| `--dry-run` | `run_calibration` | 실제 실행 없이 선택된 태스크·완료/대기 목록만 출력 |
| `--resume` | `run_calibration` | 이미 기록된 태스크는 건너뛰고 남은 것만 실행(중단 후 이어하기) |
| `--limit N` | `run_calibration` | 앞 N개만 실행. **개발 진단 전용** — Gate 근거로 쓰지 않음 |
| `--output_dir <dir>` | 양쪽 | 출력 루트. 기본 `outputs/g3` |
| `--allow_partial` | `compare_calibration` | 20 row 미만이어도 비교 강행. **개발 진단 전용** |

같은 `experiment_id`에 이미 기록이 있는데 남은 태스크가 있으면, 실수 방지를 위해 `--resume` 없이는 실행이 거부됩니다.

빠른 점검 예시(실제 채점 없이 계획만 확인):

```bash
.aciarena/bin/python -m native_reference.run_calibration \
  --implementation reconstructed --experiment_id g3-sequential-calibration-v2 --dry-run
```

## 주의사항

- 공식 runtime 고유의 프롬프트 scaffolding은 **비교 대상 그 자체**이므로 제거하거나 재구현 프롬프트로 바꾸지 않습니다.
- 이 calibration은 완전한 native equivalence나 성능 동등성 검정이 **아닙니다**(작은 표본의 기능 대조).
- **authoritative 실행은 `g3-sequential-calibration-v2`** 입니다. 최초 `v1`은 분석기(context 증거 검사)가
  multiline 문자열을 JSON escape 상태로 비교한 결함이 있어 FAIL했고, 덮어쓰지 않고 진단 이력으로만 보존합니다(Gate 근거 아님).
- 상세 구현·검증 기록은 [`구현문서/G3_구현_기록.md`](../구현문서/G3_구현_기록.md)를 참고하세요.
