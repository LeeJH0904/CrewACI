# CrewAI × ACIArena 연구·구현 문서

갱신일: 2026-09-11

**G5~G7의 활성 구성은 Sequential 하나로 확정한다.** Hierarchical/GH는
G7 완료 후 자원·일정 여유가 있을 때만 별도 승인으로 재검토하며,
현재 필수 연구 범위와 RQ에 포함하지 않는다(D41).

## 구현 진입점

[00_구현_가이드.md](00_구현_가이드.md)는 공통 계약→기준본 문제→범위→작업 공간→구현 명세→구현 순서→완료 기준 순서의 실행용 요약이다. 날짜별 일정과 인원별 분배는 포함하지 않는다.

## 최신 세부 가이드

`archive/`라는 폴더명은 유지하지만, 아래 6개 문서는 과거 폐기본이 아니라 **현재 유효한 상세 기준**이다.

1. [연구 목표 및 기여](archive/01_연구_목표_및_기여.md): 신청서·범위 축소·연구 질문·Hierarchical 결정.
2. [실험 설계 가이드](archive/02_실험_설계_가이드.md): 데이터·공격 범주/표면·기본/확장 규모·통제.
3. [구현 아키텍처 가이드](archive/03_구현_아키텍처_가이드.md): 역할·파일 책임·실행·공격 경계.
4. [실험 평가 기준 및 데이터 가이드](archive/04_실험_평가_기준_및_데이터_가이드.md): 필드명·지표 분모·실패·재시도·재사용.
5. [검증 및 품질 기준](archive/05_검증_및_품질_기준.md): CrewAI 기능 충실도·ACIArena 공격 계약·Gate 증거.
6. [논문 구성 가이드](archive/06_논문_구성_가이드.md): 기본/확장 원고·결과·주장 범위.

범위는 01, 실험 조합은 02, 구조는 03, 데이터 계약은 04, 검증은 05, 논문은 06을 기준으로 한다. 변경 시 구현 요약과 관련 문서를 함께 갱신한다.

## 개편 이력과 사용상 주의

- 2026-08-31의 신청서 정합성·범위 축소 결정을 6개 주제 문서에 통합했다.
- 2026-09-04의 Sequential 우선 결정을 반영해, 20-run 기본 calibration과 40-run 확장 calibration을 구별했다.
- 2026-09-08 기존 공격의 domain을 확인해 기본 **455/확장 총 910 runs**로 산식을 정정했다(이전 563/1,126). 대표 공격 1개/범주, Math 4종·Code 5종의 개발 manifest 기준이며 별도 파일럿·재시도는 제외한다. [manifest 설명](../manifests/README.md)을 참조한다.
- 2026-09-08 CrewAI recorded 실행기와 Linux x86_64 Code 격리 verifier를 연결했다. 이 시점에는 설정·Judge/verifier·의존성 동결이 남아 있었다.
- 2026-09-08 단일 개발 설정·Judge·verifier·dependency lock·paid API 예산 0을 기록하고 G0를 완료했다. 다음은 G1 표준 반환 계약·normalizer다. 전체 matrix/coverage audit는 G2/G6에서 수행한다.
- 2026-09-09 Finalizer 원본/정규화 출력, 순서가 있는 conversation, source/status의
  strict 반환 계약과 `text-envelope-v1` normalizer를 연결해 G1을 완료했다. 다음은
  G2의 세 공격 표면·저장 격리·domain별 golden·resume·audit 검증이다.
- 2026-09-09 AnswerMapping의 분수 오판을 수정하고 task-level 적용 가능성을 명시했다.
  선정 공격 8종·세 표면, 20개 병렬 공격 run, 100개 병렬 JSONL, Math/Code golden,
  resume/retry 및 manifest matrix audit를 통과해 G2를 완료했다. 다음은 G3의 공식
  CrewAI↔재구현 20-run calibration과 기능별 차이 보고다.
- 2026-09-10 G3 공식 참조를 `crewai==1.15.21`의 별도 exact-lock 환경으로 고정하고,
  같은 10개 태스크를 native/reconstructed에서 실행·기록한 뒤 공통 verifier로 비교하는
  실행기와 보고서를 구현했다. G4의 최종 형식 보강 후 다시 수행한 현재 기준
  `g3-sequential-calibration-v3`에서 양쪽 10/10 완료,
  context·Finalizer source 전수 통과, parse 차이 10pp로 G3 Gate를 완료했다. utility는
  비교 가능한 9쌍에서 disagreement 0건이며 작은 기능 대조 이상의 동등성은 주장하지 않는다.
- 2026-09-11 고정 30-run G4 파일럿 실행기·감사·Gate 보고서를 추가했다. 진단 v1/v2가
  각각 Math 최종 형식과 Disruption 비답변 평가 계약의 문제를 드러냈고, 수정 후
  `g4-sequential-pilot-v3`에서 완료·저장·도달·주입·domain별 평가 가능률이 모두
  30/30 또는 100%로 G4 기술 Gate를 통과했다. Hierarchical은 비용 상한과 연구팀 합의가
  없어 보류하며, 명시적 승인 전 활성 구성은 Sequential 하나다.
- 2026-09-11 GH는 G7 완료 후 여유 자원이 있을 때만 재검토하도록
  후순위로 확정했다. G5용 중복 제거 22개 전 공격 manifest(Math 13·
  Code 14), 1,056-run 정확 matrix, GPT-4o-mini 고정 snapshot·$2 실행 상한·
  provider preflight 잠금을 구현했다. 비용 불확실성에 대비해 smoke 8→benign 69→
  Math 507→Code 420→confirmation 60과 기본 20-run 소배치·session $1.00 정지선으로
  나눴다. credential 갱신 뒤 provider preflight를 통과하고 실제 1,056/1,056 계획 행을
  모두 수집했다. strict 완료는 1,052건이며 빈 Math 답변 3건과 provider 호출 전 중단
  1건을 보존한다. input 2,433,353 + output 1,107,609 tokens, 정가 환산
  $1.02956835로 $2 상한 이내다. MathInvert의 worker-thread signal 결함은 원본을
  덮어쓰지 않고 성공 응답 38건을 main thread에서 무과금 재판정해 7개 판정을 교정한
  versioned artifact로 남겼다(D46). 다음은 G6 감사·집계·보고서 동결이다.
- 2026-09-11 재감사에서 MathInvert의 int/float 외 정답을 그대로 목표로 삼던 의미 결함과
  config_hash 없는 matrix resume, SDK 내부 재시도·불완전 usage 비용 계측 문제를 추가로
  수정했다. MathInvert v2는 파싱된 수학 객체의 가법 역원이며 39개 중 의미상 구별할 수
  없는 4개 task만 비적용이다. `manifests/g5-v2/`와
  `configs/experiments/g5_v2.yaml`을 별도 생성했고, v2 preflight 전까지 유료 실행은
  잠겨 있다. 따라서 현재 단계는 **G5-v2 2차 벤치마크 실행 전**이며 G6로 진입하지 않는다.
- 2026-09-12 Claude 재검증 권고를 반영했다. 현재 소스에서 G0~G4의 과거 config를
  in-place 재감사하면 drift가 발생하는 것이 정상이며, 당시 hash 계약의 재생성·재감사는
  G4 완료 커밋 `a1d662e`에서만 수행한다. 오해 소지가 있던 G5-v1 readiness config와
  버그 실행 output은 삭제했고, 실행 가능한 최종 계약은 `g5_v2.yaml`만 유지한다(D52·D53).
- ACIArena_관련_문서/ 폴더 내부에 '연구개발 사업 선청서'와 'ACIArena_CrewAI_통합_정리' 문서가 저장되어있다.
    'ACIArena_CrewAI_통합_정리.md'의 경우, 초반의 통합 구상안을 담고있으며, 현재 진행 과정도 해당 문서를 중심으로 한다.
    다만 초기 작성된 문서이므로, 'ACIArena_CrewAI_통합_정리.md' 문서와 'archive/' 폴더 내부 문서 및 '00_구현_가이드.md' 문서 내용상의 불일치가 있다면, 'archive/' 폴더 내부 문서 및 '00_구현_가이드.md' 문서 내용을 우선한다.
