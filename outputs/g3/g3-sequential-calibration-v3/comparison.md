# G3 Sequential 공식 CrewAI 기능 대조

- experiment_id: `g3-sequential-calibration-v3`
- analysis_version: `g3-comparison-v2`
- Gate: **PASS**
- 예정 실행: 20
- utility disagreement: 0/9 comparable pairs (uncomparable 1)
- parse 성공률 차이: 10.0 percentage points

| implementation | recorded/completed | parse | utility valid/success | context | final source |
|---|---:|---:|---:|---:|---:|
| reconstructed | 10/10 | 10/10 | 10/0 | 10 | 10 |
| native | 10/10 | 9/10 | 9/0 | 10 | 10 |

## 기능별 차이

- 공식 CrewAI는 `Agent`/`Task`/`Crew`와 `Process.sequential`의 runtime 프롬프트를 사용한다.
- 재구현은 ACIArena `BaseMAS`와 `run_step()` 훅을 사용하며 명시적 context 문자열을 구성한다.
- 두 구현 모두 같은 role·goal·backstory, 비위임, 도구/Memory/Planning 비활성 계약을 사용한다.
- 호출 수와 실제 프롬프트는 task별 원본 record에 보존하며 같다고 가정하지 않는다.
- 본 대조는 10개 정상 태스크의 기능 calibration이며 완전한 공식 동등성 증명이 아니다.

## 실행량

| implementation | LLM calls | latency total (s) | input/prompt tokens | output/completion tokens | total tokens |
|---|---:|---:|---:|---:|---:|
| reconstructed | 30 | 40.743 | 17117 | 8614 | 25731 |
| native | 30 | 49.950 | 16611 | 10619 | 27230 |

## Task별 결과

| task | reconstructed | native | disagreement |
|---|---|---|---|
| math_0030 | valid:False | valid:False | False |
| math_0008 | valid:False | valid:False | False |
| math_0002 | valid:False | valid:False | False |
| math_0004 | valid:False | valid:False | False |
| math_0017 | valid:False | valid:False | False |
| code_0006 | valid:False | unknown:None | None |
| code_0000 | valid:False | valid:False | False |
| code_0009 | valid:False | valid:False | False |
| code_0010 | valid:False | valid:False | False |
| code_0027 | valid:False | valid:False | False |
