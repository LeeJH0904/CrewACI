모든 구현 단계가 끝났고, 이제 벤치마크를 진행할 차례입니다.

실제 유료 벤치마크를 진행할 때 선택할 옵션은 아래와 같습니다.

## 실제 벤치마크 시행 (openai api 활용)

### benign 

--suite benign 옵션으로도 각각 측정 필요

### math task

  | MAS | Hijacking | Disruption | Disclosure |
  |---|---|---|---|
  | CAMEL | critic | task_specifier | user_proxy |
  | AutoGen | user_proxy | assistant | assistant |
  | AgentVerse | critic_0 | solver | solver |
  | Self Consistency | sc1 | aggregate | aggregate |
  | LLM Debate | debater_2 | aggregator | aggregator |
  | CrewAI | solver | solver | solver |

 - MetaGPT는 code task만 측정. math에서는 제외

### code task

  | MAS | Hijacking | Disruption | Disclosure |
  |---|---|---|---|
  | CAMEL | critic | task_specifier | user_proxy |
  | AutoGen | user_proxy | assistant | assistant |
  | AgentVerse | critic_0 | solver | solver |
  | Self Consistency | sc1 | aggregate | aggregate |
  | LLM Debate | debater_2 | aggregator | aggregator |
  | MetaGPT | engineer | architect | qa_engineer |
  | CrewAI | solver | solver | solver |

  ### 벤치마크 실행 명령어
  
  .aciarena/bin/python benchmark.py --mas camel --task_domain math --suite hijacking --limit 2 --execute --experiment_id g7-realbench

이때, --limit 옵션은 유료 상한 제한으로 필수 옵션이 아니라 제거하고 진행해도 무방합니다.

또한 --malicious_agents 옵션도 측정 시 기입할 필요 없습니다. 
--malicious_agents 옵션을 주지 않으면 디폴트로 사전 지정해둔 malicious_agents로 벤치마크가 진행되기 때문입니다.

--execute 옵션을 포함해야 실제 api 호출을 통한 벤치마크가 진행되기 때문에, 꼭 포함해주시길 바랍니다.

--experiment_id 옵션은, mas나 suite가 바뀌어도 동일한 이름으로 지정해주세요. 그러면 같은 폴더 내에 모든 벤치마크 데이터가 저장됩니다.

---

#### LM Studio(Bionic) 활용 프레임워크 동작 검증

**legacy 6종 (override 플래그):**
  .aciarena/bin/python benchmark.py --mas camel --task_domain math --suite hijacking \
    --limit 2 \
    --execute \
    --model_config configs/lmstudio_model.yaml \
    --judge_config configs/lmstudio_judge.yaml \
    --experiment_id fw-check-lmstudio

**CrewAI (experiment_config 지정):**
  .aciarena/bin/python benchmark.py --mas crewai_seq_nodeleg --suite hijacking \
    --task_domain math --limit 2 --execute \
    --experiment_config configs/experiments/lmstudio_check.yaml \
    --experiment_id fw-check-lmstudio
