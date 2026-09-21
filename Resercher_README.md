모든 구현 단계가 끝났고, 이제 벤치마크를 진행할 차례입니다.

실제 유료 벤치마크를 진행할 때 선택할 옵션은 아래와 같습니다.

## 실제 벤치마크 시행 (openai api 활용)

- 각자의 api를 env에 삽입


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
  
  .aciarena/bin/python benchmark.py --mas crewai_seq_nodeleg --task_domain math --suite hijacking \
    [--limit 2] \
    --execute \
    [--model_config configs/g7_model.yaml] \
    [--judge_config configs/g7_judge.yaml] \
    --experiment_id fw-check-lmstudio




## 하나의 mas 당 실행할 명령어 리스트
 - **camel의 경우**
```
.aciarena/bin/python benchmark.py --mas camel --task_domain math --suite benign --execute --experiment_id camel
.aciarena/bin/python benchmark.py --mas camel --task_domain math --suite hijacking --execute --experiment_id camel
.aciarena/bin/python benchmark.py --mas camel --task_domain math --suite disruption --execute --experiment_id camel
.aciarena/bin/python benchmark.py --mas camel --task_domain math --suite disclosure --execute --experiment_id camel

.aciarena/bin/python benchmark.py --mas camel --task_domain code --suite benign --execute --experiment_id camel
.aciarena/bin/python benchmark.py --mas camel --task_domain code --suite hijacking --execute --experiment_id camel
.aciarena/bin/python benchmark.py --mas camel --task_domain code --suite disruption --execute --experiment_id camel
.aciarena/bin/python benchmark.py --mas camel --task_domain code --suite disclosure --execute --experiment_id camel
```


이때, --limit 옵션은 유료 상한 제한으로 필수 옵션이 아니라 제거하고 진행해도 무방합니다.

--model_config 옵션과 --judge_config 옵션도 필수 옵션이 아닙니다.
기본적으로 configs/g7_model.yaml과 configs/g7_judge.yaml 를 참조하기 때문에, 명시하지 않아도 무방합니다.

또한 --malicious_agents 옵션도 측정 시 기입할 필요 없습니다. 
--malicious_agents 옵션을 주지 않으면 디폴트로 사전 지정해둔 malicious_agents로 벤치마크가 진행되기 때문입니다.

--execute 옵션을 포함해야 실제 api 호출을 통한 벤치마크가 진행되기 때문에, 꼭 포함해주시길 바랍니다.

--experiment_id 옵션은, **mas별**로 따로따로 지정해주세요. (같은 이름으로 권장)

**벤치마크 데이터는 ./outputs 폴더에 저장되며, 이전의 /logs 폴더는 레거시로써 더이상 사용하지 않는 경로입니다.**
