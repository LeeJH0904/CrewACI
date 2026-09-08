# G0 검증 기록

## 일곱 번째 작업: 설정·Judge·의존성 동결 (2026-09-08)

**unit 51개 + 실행기 통합 16개 + 기존 회귀 9개 = 누적 76개 통과**.
manifest `--check`와 `git diff --check`도 통과했으며 실제 모델 API 호출은 없다.

`configs/experiments/core.yaml`의 참조·로컬 endpoint·모델 값·예산·재시도·Judge·
verifier·예정 수를 검사하고, `requirements.lock`과 필수 설치 version을 대조했다.
계약의 provider 요청 수를 8회로 바꾼 fixture는 거부됐다. Disruption 세 label의
판정값과 strict OpenAI json_schema 요청, 동기 provider 호출 1회를 mock으로 확인했다.

## 여섯 번째 작업: Code 격리 verifier (2026-09-08)

기본 Code 경로에서 HumanEval·MBPP 정답, timeout false, 네트워크·저장소 읽기·
sandbox 밖 쓰기 차단을 확인했다. Linux x86_64 namespace·Landlock·seccomp·rlimit 중
하나라도 적용할 수 없으면 host fallback 없이 평가 오류를 남긴다. 이 작업까지
unit 46개·실행기 통합 16개·기존 회귀 9개, 누적 71개를 통과했다.

## 다섯 번째 작업: CrewAI 실행기 연결 (2026-09-08)

**unit 46개 + 당시 실행기 통합 14개 + 기존 회귀 9개 = 69개 통과**.
manifest `--check`와 `git diff --check`도 통과했다.

```bash
.aciarena/bin/python -m unittest discover -s tests/unit -q
.aciarena/bin/python -m unittest tests.integration.test_recorded_executor -q
.aciarena/bin/python -m unittest discover -s tests/integration -p test_g0_baseline.py -q
.aciarena/bin/python scripts/build_manifests.py --check
```

실제 MAS·공격·수학 verifier를 실행하고 LLM 경계만 mock했다. 정상 false 재개,
세 공격 표면의 실제 입력/메시지, benign 오염 방지, 20개 병렬 run의 60개 Agent LLM
분리, 같은 run의 중복 모델 호출 방지, 생성/모델/timeout/평가/저장 오류 보존,
Judge 원문, 공격 answer mapping 및 파싱 unknown, 집계 분모와 factory 경로를 확인했다.
최종 메시지 뒤 Judge evaluation을 기록해도 출력 증거 audit가 통과하는 unit도 추가했다.

math-verify는 작업 스레드의 signal 오류를 false로 삼킬 수 있어 별도 main-thread
프로세스로 옮겼다. worker 구현 중 verify 이름 충돌도 실패 테스트를 통해 수정했다.
이 절은 실행기 연결 당시의 이력이다. Code 격리와 설정 동결 결과는 위 최신 절을 따른다.

## 네 번째 작업: 실행별 JSONL 저장 (2026-09-08)

```bash
.aciarena/bin/python -m unittest discover -s tests/unit -v
.aciarena/bin/python scripts/build_manifests.py --check
```

writer 신규 테스트 **16개**, 기존 포함 **unit test 총 45개 통과**.
100개 동시 실행의 100개 run rows·200개 messages와 4개 프로세스의 20개 rows를
검사했다. 중복 쓰기 경쟁에서는 한 요청만 기록됐고, seq 단절·시도 gap·마감 후
추가 쓰기·완료 후 재시도를 거부했다. valid false는 reopen 후에도 완료로 조회됐다.

실행 오류 전 partial trace와 오류 row/재시도 row가 보존됐으며, 실패 전 메시지가
없는 오류도 기록할 수 있었다. 잘못된 JSON·누락 newline·중복 row·메시지 seq 변조는
검사 실패로 드러났다. disk write·부분 쓰기·파일 fsync·마지막 directory fsync
실패를 주입해 marker/원본을 보존하고 새 writer도 복구 전 진행하지 못함을 확인했다.

검증 환경은 로컬 Linux/WSL의 POSIX 파일 잠금이다. 전원 장애나 NFS·Windows를
검증한 결과는 아니다. API 및 Code evaluator는 실행하지 않았다. 기존 executor/logger
연결과 matrix audit·CLI resume는 아직 후속 작업이며 G0 전체 통과가 아니다.

## 세 번째 작업: 공격 catalog/factory (2026-09-08)

```bash
.aciarena/bin/python -m unittest discover -s tests/unit -v
.aciarena/bin/python scripts/build_manifests.py --check
```

신규 catalog 테스트 13개를 포함한 **unit test 총 29개 통과**.
대표 공격 전체의 지원 domain 생성, Judge 생성 전 잘못된 ID/domain/target/
class/surface/hash 거부, 중복·누락 검출, 불변 spec, registry 순서 비의존성을 확인했다.
반복 및 20개 동시 생성에서 Attack·Judge·client·answer·token 상태가 분리됐다.
실제 OpenAI provider factory도 SDK 생성자만 mock하여 wrapper와 동기/비동기 client가
새로 생성됨을 확인했다. 정상 조건은 새 객체를 만들지만 Judge와 공격 판정이 없다.

API 호출·Code evaluator 실행은 없었다. 실제 공격 적용 및 MAS 실행 격리의 전체
검증은 executor 연결 단계에 남아 있다. 기존 executor의 deepcopy 경로도 아직 유지된다.

## 두 번째 작업: manifest·기록 스키마 (2026-09-08)

```bash
.aciarena/bin/python scripts/build_manifests.py --check
.aciarena/bin/python scripts/build_manifests.py --dry-run
.aciarena/bin/python -m unittest discover -s tests/unit -v
```

manifest/records unit test **16개 통과**. hash·source·선정 일치, 원본 공격 클래스와
payload 대조, domain·표면·표본 coverage, 변경/누락/중복 검출,
JSON 왕복·strict 판정·실행/평가 오류 분리·false 완료·재시도 ID를 확인했다.
예정 수량은 69 tasks, 8 categories, 핵심 공격 306회, 별도 파일럿을 제외한 455회다.
이 테스트는 API와 Code evaluator를 실행하지 않는다. runtime·writer 연결과
G0/G1/G2 전체 통과를 의미하지 않는다. 세부 선정은 [manifest 설명](../manifests/README.md)을 따른다.

## 첫 번째 작업: 기준본 회귀

검증일: 2026-09-08. **G0의 기준본 보존·오프라인 회귀 하위 작업만 완료**했다.
G0 전체 또는 G1/G2 통과 보고서가 아니다.

## 재실행

저장소 루트에서 실행한다.

```bash
.aciarena/bin/python -m unittest discover -s tests/integration -p 'test_g0_baseline.py' -v
```

추가 테스트 패키지 없이 표준 라이브러리 `unittest`를 사용한다.
기존 프로젝트 의존성은 설치돼 있어야 한다. Agent의 LLM 초기화 경계만
`ScriptedLLM`으로 대체하고, 실제 MAS·Agent·Math/Code verifier를 실행한다.
모델 endpoint나 인증정보는 읽지 않으며 실제 LLM 초기화가 발생하면 실패시킨다.

Code 검증은 기존 HumanEval의 자식 프로세스와 로컬 IPC 소켓을 사용하고,
각 평가의 timeout은 2초다. 소켓을 차단하는 실행 환경에서는 환경 권한 오류가
발생한다. 2026-09-08 첫 실행은 이 제한으로 실패했고, 허용된 환경에서
재실행해 **9 tests, OK**를 확인했다. 오류를 skip하거나 verifier를 mock해
통과 처리하지 않았다.

실행하는 Code 응답은 저장소의 첫 HumanEval 문제의 canonical solution과
고정 오답 `return []`다. 이 검증은 신뢰된 회귀 fixture만 대상으로 하며,
본 실험의 모델 생성 코드에 필요한 네트워크·자원 격리 sandbox를 검증하지 않는다.

## 기준본과 fixture

- 검증 대상 코드 commit: `70c90bbc376b3fbe161e9310fb8606abaa4907ca`.
- 보존 브랜치: `baseline/g0-70c90bb`.
- 작업 브랜치: `LeeJH`; 기준본 생성으로 checkout은 바꾸지 않았다.
- 이번 테스트와 기록은 기준 commit 이후 추가한 작업 파일이다.
- `golden/g0_baseline.json`: Math·Code 각각 원본 index 0, 데이터 파일 SHA-256,
  고정 정답·오답 응답과 기대 utility. 데이터가 바뀌면 명시적으로 검토하도록
  테스트에서 hash를 확인한다.
- 이 두 fixture는 회귀용이다. G0의 전체 task manifest나 calibration/confirmation
  표본 선정으로 간주하지 않는다.

## 확인한 동작

| 검증 | 범위 |
|---|---|
| 기존 MAS Math·Code 회귀 | SelfConsistency에서 domain별 정답 1회·오답 1회, 실제 verifier가 각각 1.0·0.0 판정 |
| Sequential Math | Solver→Reviewer→Finalizer 각각 1회, pre/post 훅, 원문·초안·검토 전달, 최종 응답 320 |
| Sequential Code | Finalizer의 고정 정답이 실제 Code verifier를 통과 |
| profile·새 Agent | 변경된 profile이 실제 system 입력에 반영되고 새 MAS의 profile·memory에 남지 않음 |
| 모델 예외 | Reviewer 예외를 그대로 전달하고 Finalizer는 호출하지 않음 |
| 기존 기반 수정 | BaseAgent tools·BaseMAS 기본 malicious_agents 분리, AnswerMappingAgent 단일 등록 |

고정 응답의 utility는 모델 성능 측정값이 아니다. profile 검사는 직접 profile을
변경한 최소 회귀이며 실제 공격 클래스·주입 증거·동시성 검증을 대체하지 않는다.
모델 예외 테스트도 현재의 예외 전파만 확인하며 오류 RunRecord 보존은 아직 없다.

## 실행 환경

Python 3.10.12, Linux 6.18.33.2-microsoft-standard-WSL2.
주요 설치 버전은 openai 1.63.2, google-genai 2.8.0, pydantic 2.10.6,
tenacity 9.0.0, PyYAML 6.0.2, math-verify 0.6.0, human_eval 1.0.3,
transformers 4.56.1이다. 이 목록은 환경 관측 기록이며 dependency lockfile은 아니다.

## 다음 작업

G0는 완료됐다. 다음은 G1 표준 반환 계약·normalizer이며, 전체 matrix/coverage
audit는 단계표에 따라 G2/G6에서 수행한다.
