# **MASLab: A Unified and Comprehensive Codebase for LLM-based Multi-Agent Systems** 

**Rui Ye**<sup>**1,***</sup> **Keduan Huang**<sup>**1,***</sup> **Qimin Wu**<sup>**1**</sup> **Yuzhu Cai**<sup>**1**</sup> **Tian Jin**<sup>**1**</sup> **Xianghe Pang**<sup>**1**</sup> **Xiangrui Liu**<sup>**1**</sup> **Jiaqi Su**<sup>**1**</sup> **Chen Qian**<sup>**1**</sup> **Bohan Tang**<sup>**3**</sup> **Kaiqu Liang**<sup>**4**</sup> **Jiaao Chen**<sup>**5**</sup> **Yue Hu**<sup>**6**</sup> **Zhenfei Yin**<sup>**3,7,†**</sup> **Rongye Shi**<sup>**8**</sup> **Bo An**<sup>**9**</sup> **Yang Gao**<sup>**10**</sup> **Wenjun Wu**<sup>**8**</sup> **Lei Bai**<sup>**2,†**</sup> **Siheng Chen**<sup>**1,†**</sup> 1 Shanghai Jiao Tong University 2 Shanghai AI Laboratory 3 University of Oxford 4 Princeton University 5 Meta 6 University of Michigan 7 The University of Sydney 8 Beihang University 9 Nanyang Technological University 10 Nanjing University * Equal contributions † Corresponding authors MASLab: https://github.com/MASWorks/MASLab 

## **Abstract** 

LLM-based multi-agent systems (MAS) have demonstrated significant potential in enhancing single LLMs to address complex and diverse tasks in practical applications. Despite considerable advancements, the field lacks a unified codebase that consolidates existing methods, resulting in redundant re-implementation efforts, unfair comparisons, and high entry barriers for researchers. To address these challenges, we introduce MASLab, a unified, comprehensive, and research-friendly codebase for LLM-based MAS. (1) MASLab integrates over 20 established methods across multiple domains, each rigorously validated by comparing step-by-step outputs with its official implementation. (2) MASLab provides a unified environment with various benchmarks for fair comparisons among methods, ensuring consistent inputs and standardized evaluation protocols. (3) MASLab implements methods within a shared streamlined structure, lowering the barriers for understanding and extension. Building on MASLab, we conduct extensive experiments covering 10+ benchmarks and 8 models, offering researchers a clear and comprehensive view of the current landscape of MAS methods. MASLab will continue to evolve, tracking the latest developments in the field, and invite contributions from the broader open-source community. 





<!-- Start of picture text -->
Comprehensive Manual Verified<br><!-- End of picture text -->



<!-- Start of picture text -->
ü Over 20 MAS Methods ü Final Output Aligned<br>ü Various Benchmarks & LLMs ü Intermediate Outputs Aligned<br>ü Data Pre-Processing ü Unified High-Level Structure<br>ü LLM Configurations ü Easy to Start for Newcomers<br>ü Evaluation Protocols MASLab ü Easy for Secondary Development<br>Method 1<br>Raw<br>Data Pre-process Evaluation MAS Method = Python Inference Function<br>Method 2<br><!-- End of picture text -->





Figure 1: MASLab: A unified, comprehensive, and research-friendly codebase for LLM-based MAS. We support fairly comparing over 20 methods, whose correctness are manually verified. 

Preprint. Under review. 

## **1 Introduction** 

Large language models (LLMs) [1, 2, 3, 4, 5] have achieved remarkable success and are being increasingly applied across various domains [6, 7, 8, 9]. However, despite their continuous advancements, a single LLM inherently faces limitations such as unreliable and random generation [10, 11], hallucinations [12, 13], and difficulty handling complex, multi-step tasks [14, 15]. These limitations hinder their ability to effectively tackle the full spectrum of real-world applications on their own. 

The limitations of single LLMs have driven emerging research towards the development of LLMbased multi-agent systems (MAS) [16, 17, 18, 19], where multiple agents, each with distinct roles, contexts, and tools, collaborate to address complex tasks more effectively. This paradigm has shown great promise across a range of applications, including code generation [16, 20], mathematical problem-solving [21, 22], academic research [23, 24], and data synthesis [25, 26]. Over the past year, this field has seen rapid development, evolving from early MAS approaches that rely on manually designed, fixed systems [16, 27, 20, 28, 29, 21] to more dynamic systems where the roles and behaviors of the agents are adaptable [18, 19, 30, 31, 32]. This ongoing evolution is steering the field towards greater automation and generalization, with the potential to create more intelligent systems. 

Despite the rapid progress in LLM-based MAS, the field lacks a unified codebase that consolidates the various methods and algorithms. This gap results in several critical issues that hinder the field’s long-term advancement: **(1) Redundant effort.** Without shared, accessible resources, researchers expend significant time reimplementing existing works, diverting effort from innovative contributions. **(2) Unfair comparison.** Varied implementation designs of individual codebases, such as differing dataset preprocessing and evaluation protocols, complicate fair and reliable comparisons across methods. **(3) High entry barriers.** Newcomers face difficulties navigating through disparate repositories, with no clear starting points. Addressing these challenges is crucial to accelerate research and promote cohesive progress in the field. However, unifying massive methods—that originally employ distinct codebase styles, architectures, and dependencies—into one codebase poses significant challenges. This requires not only substantial efforts for re-implementation and verification, but also a comprehensive understanding of all methods to enable unification. 

To bridge this gap, we present **MASLab** , the first unified codebase for LLM-based MAS, integrating over 20 established methods (e.g., most cited or accepted by recent top-tie venues) with a coherent high-level structure and standardized evaluations; see overview in Table 1. **(1)** MASLab consolidates diverse research spanning multiple domains—including general tasks [29], coding [16], and mathematics [21]—covering representative advancements from March 2023 through March 2025. Each method integrated into MASLab has been rigorously verified by comparing step-by-step outputs with its official implementation, greatly reducing redundant reimplementation efforts for future researchers. **(2)** MASLab supports unified evaluations across a wide array of benchmarks, ensuring consistent inputs and standardized evaluation protocols. This facilitates reliable and fair comparisons, emphasizing core methodological differences rather than implementation disparities. **(3)** All methods are implemented within a streamlined, high-level structure, where each is encapsulated as a core inference function that processes a query and delivers the MAS response. This transparent structure explicitly highlights key methodological components, significantly lowering entry barriers and enabling researchers to easily understand, extend, and innovate upon existing approaches. 

Based on MASLab, we conduct comprehensive experiments to benchmark the implemented methods, offering the research community a clear understanding of the current landscape of LLM-based MAS. Our evaluation spans 10+ benchmarks spanning diverse domains—including general question answering, mathematics, coding, science, and medicine—using 8 LLM backbones including Llama-3.3-70B-Instruct, Qwen-2.5-7/14/32/72B-Instruct, and GPT-4o-mini/4.1-mini/4.1 models. Our analysis examines the impact of varying evaluation protocols adopted by prior studies, the scaling behavior with respect to method configuration and model size, and failure cases. Notably, we demonstrate that discrepancies in evaluation protocols can lead to substantial variation in performance rankings, underscoring the importance of a unified codebase for fair and reproducible comparisons. 

## **2 Related Work** 

**LLM-based MAS.** LLM-based multi-agent systems (MAS) extend the capabilities of LLMs by enabling collaborative interactions among multiple agents. CAMEL [17] and AutoGen [34] primarily focus on two-agent (user–assistant) role-playing, while MetaGPT [20] and ChatDev [16] assign 

2 

Table 1: Descriptions of 24 methods that MAS-Lab currently support. We show several critical perspectives of MAS methods. (1) Role: whether agents’ roles in the method is fixed or dynamic. (2) Topo.: whether the topology in the method is fixed or dynamic. (3) Tool: whether the method includes tool usage. (4) Optim.: whether the method is optimizable. (5) Generalization: whether the method can generalize to handle diverse tasks. 

|No.|Methodology<br>Venue|Role|Topo.|Tool|Optim.|Generalization|
|---|---|---|---|---|---|---|
|Single|-Agent Baselines||||||
|1|Vanilla LLM<br>-|Fixed|Fixed|No|No|Yes|
|2|CoT [33]<br>NeurIPS 2022|Fixed|Fixed|No|No|Yes|
|Multi|-Agent Systems for General Tasks||||||
|3|CAMEL [17]<br>NeurIPS 2023|Fixed|Fixed|No|No|Yes|
|4|AutoGen [34]<br>ICLR-W 2024|Fixed|Fixed|Yes|No|Yes|
|5|Self-Consistency [35]<br>ICLR 2024|Fixed|Fixed|No|No|Yes|
|6|AgentVerse [29]<br>ICLR 2024|Dynamic|Fixed|No|No|Yes|
|7|LLM Debate [27]<br>ICML 2024|Fixed|Fixed|No|No|Pre-defned Roles|
|8|GPTSwarm [32]<br>ICML 2024|Fixed|Dynamic|Yes|Yes|Validation-Required|
|9|DyLAN [31]<br>COLM 2024|Fixed|Dynamic|No|No|Pre-defned Roles|
|10|MAD [28]<br>EMNLP 2024|Fixed|Fixed|No|No|Pre-defned Roles|
|11|Self-Refne [36]<br>NeurIPS 2024|Fixed|Fixed|No|No|Yes|
|12|MacNet [37]<br>ICLR 2025|Fixed|Fixed|No|No|Pre-defned Roles|
|13|ADAS [18]<br>ICLR 2025|Fixed|Fixed|Yes|Yes|Validation-Required|
|14|AFlow [30]<br>ICLR 2025|Fixed|Fixed|Yes|Yes|Validation-Required|
|15|MAV [38]<br>ICLR-W 2025|Fixed|Fixed|No|No|Yes|
|16|MAS-GPT [19]<br>ICML 2025|Dynamic|Dynamic|Yes|Yes|Yes|
|Multi|-Agent Systems for Coding Tasks||||||
|17|MetaGPT [20]<br>ICLR 2024|Fixed|Fixed|Yes|No|Coding-Specifc|
|18|ChatDev [16]<br>ACL 2024|Fixed|Fixed|Yes|No|Coding-Specifc|
|19|MapCoder [39]<br>ACL 2024|Fixed|Fixed|Yes|No|Coding-Specifc|
|20|EvoMAC [40]<br>ICLR 2025|Dynamic|Dynamic|Yes|No|Coding-Specifc|
|Multi|-Agent Systems for Mathematical Tasks||||||
|21|MACM [21]<br>NeurIPS 2024|Fixed|Fixed|No|No|Math-Specifc|
|Multi|-Agent Systems for Scientifc Tasks||||||
|22|MedAgents [41]<br>ACL-F 2024|Fixed|Fixed|No|No|Medicine-Specifc|
|Multi|-Agent Systems for Tool-Required Tasks||||||
|23|OWL-Roleplaying [42]<br>GitHub 2025|Fixed|Fixed|Yes|No|Yes (with Proper Tools)|
|24|MASLab-ReAct [43]<br>ICLR 2023|Fixed|Fixed|Yes|No|Yes (with Proper Tools)|



multiple specialized roles (e.g., coder, reviewer) for fixed software development pipeline. Debatestyle systems [27, 28, 44] employ multiple agents to propose and criticize solutions. AgentVerse [29] and DyLAN [31] allow iterative adjustment of team configurations during task execution. 

While these fixed-role architectures demonstrate the potential of MAS, they rely heavily on manually defined roles and workflows, limiting generalizability across tasks. To address this, recent works explore automatic workflow generation [19, 18, 45, 46, 47]. GPTSwarm [32] models agents as an optimizable graph of LLM operations refined via validation feedback. Similarly, ADAS [18] and AFlow [30] leverage a strong meta-agent to iteratively design agentic workflows. MAS-GPT [19] trains an LLM that generates an executable MAS based on each user query. 

However, these methods are implemented in isolated codebases, leading to redundant efforts, inconsistent evaluations, and steep entry barriers. MASLab resolves these issues by providing a unified and comprehensive codebase that supports all of the above methods within an extensible framework. 

**LLM-agent codebase.** In parallel with algorithmic advances, several open-source frameworks have emerged to facilitate the development of LLM-based agents. CAMEL [17] and AutoGen [34] introduce conversational agent frameworks based on role-playing. LangChain [48], LangGraph [49], and OpenAgents [50] provide low-code environments for constructing LLM-driven applications and workflows. However, none of these frameworks are designed specifically for research purposes: they lack implementations of representative multi-agent methods from the existing literature and 

3 



<!-- Start of picture text -->
Unified Codebase Streamlined Representation of 20+ MAS Methods<br>from toolkits import code_executor<br>Pre-process Optimization<br>data class MASExample(MAS):<br>...<br>Evaluation Inference def inference(self, sample):<br>metric roles = self.agent_recruit(sample)<br>solutions = self.agent_discuss(roles)<br>Shared Resources solution = self.aggregate(solutions)<br>Diverse LLMs feedback = code_executor(solution)<br>response = self.improve(solution, feedback)<br>Common Toolkits return response<br><!-- End of picture text -->

Figure 2: Overview of MASLab codebase. MASLab incorporates and unifies the whole pipeline from data pre-processing to evaluation, ensuring that inputs to all methods are aligned, non-algorithmic configurations are standardized, and the evaluation protocols are consistent and accurate. All 20+ methods are represented by a similar streamlined structure of python class. 

offer limited support for systematic evaluation. In contrast, our MASLab offers the first all-in-one research-friendly codebase that integrates the community’s collective progress in LLM-based MAS. 

## **3 MASLab** 

MASLab is a unified, comprehensive, research-oriented codebase for LLM-based multi-agent systems (MAS). It consolidates over 20 published MAS methods with consistent inference basic configurations and unified evaluation protocols, facilitating researchers for fast and fair algorithmic comparisons. All methods are verified by comparing their intermediate outputs with the official implementations. 

### **3.1 Inference of MAS** 

In order to unify and streamline the diverse MAS codebases in the field, MASLab focuses on four key aspects during inference that ensure consistency and fairness across different methods: representation of MAS, inputs, configurations, and accessible resources. These aspects are designed to eliminate the disparities that have traditionally hindered cross-method comparisons and replication of results. 

**Streamlined representation of MAS.** Each MAS method within MASLab is abstracted into a Python class, all of which inherit from a common base class. This base class provides shared functionality across methods, such as making LLM requests and tracking LLM token consumptions. The core of each method is the _inference_ function, which takes a data sample (e.g., a mathematical problem) as input and outputs the solution generated by the MAS. By standardizing the representation in this manner, the structure of each MAS approach is simplified, allowing researchers to gain a clear understanding of the key steps involved by merely inspecting the inference function. In many cases, the inference process is further modularized, with specific components encapsulated as additional functions to highlight the different stages of task-solving, such as team recruitment and code execution. This design ensures that the complexity inherent in different MAS methods is handled in a consistent, easily interpretable manner, while preserving the unique features of each individual approach. For optimization-based methods [18, 32, 30], another core _optimization_ function will process a validation set to produce an optimized MAS. See re-implementation notes in Section D. 

**Consistent inputs.** MASLab standardizes input preprocessing for all MAS methods, ensuring fair comparisons by eliminating discrepancies. For instance, prior implementations of MapCoder [39], Reflexion [51], and EvoMAC [40] use different preprocessing on the MBPP dataset, making performance differences hard to interpret. MASLab’s unified preprocessing pipeline ensures that all methods operate on identical data, relieving researchers of the need to manually prepare datasets. 

**Shared resources.** MASLab unifies the underlying resources required by MAS methods, including LLMs and external tools. It supports both externally hosted APIs and locally deployed models, covering a wide range of widely used LLMs. The integrated toolkit provides common utilities such as code execution (secured via sandboxing [52]), web search, and image analysis—capabilities frequently required across MAS designs. These shared components eliminate redundant engineering 

4 



<!-- Start of picture text -->
Ranking (Lower is Better) Accuracy (Higher is Better)<br>2 as ———N<br>70 =i4 SingleCot<br>4 -e sc<br>60 —te AutoGen<br>6 -@ LLM-Debate<br>50 -R MacNet<br>—m MAD<br>8 40. ~@ DyLAN<br>—t- AgentVerse<br>10 30. "aR—@- MAVMAS-GPT<br>LLM-2S LLM-XV-— Rule-HF = Rule-Dy ~— Rule-Hd LLM-2S LLM-XV-— Rule-HF = Rule-Dy ~—-Rule-Hd<br>Evaluation Protocol Evaluation Protocol<br><!-- End of picture text -->





<!-- Start of picture text -->
Single GB Cot GB sc @ LLM-Debate  AutoGen @ DyLAN © AgentVerse A. MacNet A MAD<br>MATH GPQA-Diamond MBPP Avg-Value on 10 Sets<br>” 78 ° B 56 @ 72 fe) o 63 =<br>5 552 5B 7 5g a<br>= 76 A E & a g 60 A<br>6 A 648 6 64 o 6<br>c 74 © c £57<br>& & 44 & 60 &<br>a B o A 54 a<br>2000 4000 5000 10000 15000 0 2000 4000 6000 2500 5000 7500<br>Token Cost Token Cost Token Cost Token Cost<br><!-- End of picture text -->



<!-- Start of picture text -->
100 GPT-40-mini-2024-07-18 Llama-3.3-70B-Instruct<br>C=) Single C= AgentVerse<br>~ C2 sc [--] MapCoder<br>se 90 [= Debate 1 Evomac<br>£<br>>% 80<br>5<br>i]<br><q 70<br>60 HumanEval MBPP HumanEval MBPP<br><!-- End of picture text -->



<!-- Start of picture text -->
Optimization-based Method<br>66 we<br>SS<br>© 64<br>z O<br>85 62 © Single.<br>3 } Debate<br>Be > V_ GPTSwarm<br>60 sir AFlow<br>V<br>0 1 2 3 4 5<br>OptimizationP Cost $ ($)<br><!-- End of picture text -->



<!-- Start of picture text -->
GAIA-Level 1 GAIA-Level 2 GAIA-Level 3<br>C= Single ([ AgentVerse CE) Single [= AgentVerse C=) Single C=) AgentVerse<br>50 CC sc (= OWL-Roleplayjng EI sc [) OWL-Roleplaying CI sc [= OWL-Roleplaying<br>[49 Debate [4 MASLab-ReAc [43 Debate [4 MASLab-ReAc [49 Debate [4 MASLab-ReAct<br>S40<br>><br>%- 30<br>S<br>o<br><q 20<br>4 |<br>GPT-4.1-mini GPT-4.1 GPT-4.1-mini GPT-4.1 —HUGPT-4.1-mini aleGPT-4.1<br><!-- End of picture text -->



<!-- Start of picture text -->
Compute Scaling Propertysenon GPQA-Diamond<br>55 AgentWerse_A3T3C3 LLM-Debate_A5R2<br>Verse A5T3C3<br>ic5354 ntVerse@ A2T3CS Self-CorSistency_P9A LLM-Debate_A3R4:<br>z<br>B52 /Consistenef_P5<br>&3got gentverse_AZTICS-Debate_A3R2 > MW LLM-Debate_A3R3i<br>< 50 Self-Consistency_P3<br>49 *@ SelfVanillaConsistency_Parallel{x}<br>H_ LLM-Debate_Agent{x}Round{y}<br>48 Vanilla A AgentVerse_Agent{x}Turn{y}Critique{z}<br>0 2500 5000 7500 10000 12500 15000 17500 20000<br>Cost (in tokens)<br><!-- End of picture text -->



<!-- Start of picture text -->
GPQA-DiamondModel Size Scaling Property MMLU-Pro<br>48 rR<br>_=S44 —* | 66 La —_—*<br>><br>8 60<br>3 40<br>Zz 54<br>36 a i<br>48 Due to Limited]. IF Capability-<br>7 14 32 72 7 14 32 22<br>Model Size (B) Model Size (B)<br>—* Single —e- SC —a LLM-Debate —&~ AgentVerse<br><!-- End of picture text -->





<!-- Start of picture text -->
|-~-<br>With An Answer<br>Normal Wrong Answer<br>Total Jorers Answer Due to Round Limit<br>J rreou While Navigating Page<br>No Browser Error Jrimeout During Loading Page<br>Answer (with Error) lim™ NavigatingImage Processingto Wrong URLError<br>— Document Processing Error<br>—Audio Processing Error<br><!-- End of picture text -->

## **References** 

- [1] OpenAI. Gpt-4 technical report. _arXiv preprint arXiv:2303.08774_ , 2023. 

- [2] Anthropic. Claude 3.5 sonnet. `https://www.anthropic.com/news/claude-3-5-sonnet` , 2024. Accessed: 2025-01-22. 

- [3] Daya Guo, Dejian Yang, Haowei Zhang, Junxiao Song, Ruoyu Zhang, Runxin Xu, Qihao Zhu, Shirong Ma, Peiyi Wang, Xiao Bi, et al. Deepseek-r1: Incentivizing reasoning capability in llms via reinforcement learning. _arXiv preprint arXiv:2501.12948_ , 2025. 

- [4] Abhimanyu Dubey, Abhinav Jauhri, Abhinav Pandey, Abhishek Kadian, Ahmad Al-Dahle, Aiesha Letman, Akhil Mathur, Alan Schelten, Amy Yang, Angela Fan, et al. The llama 3 herd of models. _arXiv preprint arXiv:2407.21783_ , 2024. 

- [5] An Yang, Baosong Yang, Beichen Zhang, Binyuan Hui, Bo Zheng, Bowen Yu, Chengyuan Li, Dayiheng Liu, Fei Huang, Haoran Wei, et al. Qwen2. 5 technical report. _arXiv preprint arXiv:2412.15115_ , 2024. 

- [6] Mark Chen, Jerry Tworek, Heewoo Jun, Qiming Yuan, Henrique Ponde De Oliveira Pinto, Jared Kaplan, Harri Edwards, Yuri Burda, Nicholas Joseph, Greg Brockman, et al. Evaluating large language models trained on code. _arXiv preprint arXiv:2107.03374_ , 2021. 

- [7] Joon Sung Park, Joseph O’Brien, Carrie Jun Cai, Meredith Ringel Morris, Percy Liang, and Michael S Bernstein. Generative agents: Interactive simulacra of human behavior. In _Proceedings of the 36th annual acm symposium on user interface software and technology_ , pages 1–22, 2023. 

- [8] Tao Tu, Shekoofeh Azizi, Danny Driess, Mike Schaekermann, Mohamed Amin, Pi-Chuan Chang, Andrew Carroll, Charles Lau, Ryutaro Tanno, Ira Ktena, et al. Towards generalist biomedical ai. _Nejm Ai_ , 1(3):AIoa2300138, 2024. 

- [9] Shijie Wu, Ozan Irsoy, Steven Lu, Vadim Dabravolski, Mark Dredze, Sebastian Gehrmann, Prabhanjan Kambadur, David Rosenberg, and Gideon Mann. Bloomberggpt: A large language model for finance. _arXiv preprint arXiv:2303.17564_ , 2023. 

- [10] Lexin Zhou, Wout Schellaert, Fernando Martínez-Plumed, Yael Moros-Daval, Cèsar Ferri, and José Hernández-Orallo. Larger and more instructable language models become less reliable. _Nature_ , 634(8032):61–68, 2024. 

- [11] Yotam Wolf, Noam Wies, Oshri Avnery, Yoav Levine, and Amnon Shashua. Fundamental limitations of alignment in large language models. In _Proceedings of the 41st International Conference on Machine Learning_ , pages 53079–53112, 2024. 

- [12] Yue Zhang, Yafu Li, Leyang Cui, Deng Cai, Lemao Liu, Tingchen Fu, Xinting Huang, Enbo Zhao, Yu Zhang, Yulong Chen, et al. Siren’s song in the ai ocean: a survey on hallucination in large language models. _arXiv preprint arXiv:2309.01219_ , 2023. 

- [13] Sewon Min, Kalpesh Krishna, Xinxi Lyu, Mike Lewis, Wen-tau Yih, Pang Koh, Mohit Iyyer, Luke Zettlemoyer, and Hannaneh Hajishirzi. Factscore: Fine-grained atomic evaluation of factual precision in long form text generation. In _Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing_ , pages 12076–12100, 2023. 

- [14] Nouha Dziri, Ximing Lu, Melanie Sclar, Xiang Lorraine Li, Liwei Jiang, Bill Yuchen Lin, Sean Welleck, Peter West, Chandra Bhagavatula, Ronan Le Bras, et al. Faith and fate: Limits of transformers on compositionality. _Advances in Neural Information Processing Systems_ , 36:70293–70332, 2023. 

- [15] Muhammad Usman Hadi, Rizwan Qureshi, Abbas Shah, Muhammad Irfan, Anas Zafar, Muhammad Bilal Shaikh, Naveed Akhtar, Jia Wu, Seyedali Mirjalili, et al. Large language models: A comprehensive survey of its applications, challenges, limitations, and future prospects. _Authorea Preprints_ , 2023. 

- [16] Chen Qian, Wei Liu, Hongzhang Liu, Nuo Chen, Yufan Dang, Jiahao Li, Cheng Yang, Weize Chen, Yusheng Su, Xin Cong, et al. Chatdev: Communicative agents for software development. In _Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers)_ , pages 15174–15186, 2024. 

- [17] Guohao Li, Hasan Hammoud, Hani Itani, Dmitrii Khizbullin, and Bernard Ghanem. Camel: Communicative agents for" mind" exploration of large language model society. _Advances in Neural Information Processing Systems_ , 36:51991–52008, 2023. 

10 

- [18] Shengran Hu, Cong Lu, and Jeff Clune. Automated design of agentic systems. In _The Thirteenth International Conference on Learning Representations_ , 2025. 

- [19] Rui Ye, Shuo Tang, Rui Ge, Yaxin Du, Zhenfei Yin, Jing Shao, and Siheng Chen. MAS-GPT: Training LLMs to build LLM-based multi-agent systems. In _Workshop on Reasoning and Planning for Large Language Models_ , 2025. 

- [20] Sirui Hong, Mingchen Zhuge, Jonathan Chen, Xiawu Zheng, Yuheng Cheng, Jinlin Wang, Ceyao Zhang, Zili Wang, Steven Ka Shing Yau, Zijuan Lin, et al. Metagpt: Meta programming for a multi-agent collaborative framework. In _The Twelfth International Conference on Learning Representations_ , 2024. 

- [21] Bin Lei, Yi Zhang, Shan Zuo, Ali Payani, and Caiwen Ding. Macm: Utilizing a multi-agent system for condition mining in solving complex mathematical problems. In _The Thirty-eighth Annual Conference on Neural Information Processing Systems_ , 2024. 

- [22] Shima Imani, Liang Du, and Harsh Shrivastava. Mathprompter: Mathematical reasoning using large language models. In _Proceedings of the 61st Annual Meeting of the Association for Computational Linguistics (Volume 5: Industry Track)_ , pages 37–42, 2023. 

- [23] Chris Lu, Cong Lu, Robert Tjarko Lange, Jakob Foerster, Jeff Clune, and David Ha. The ai scientist: Towards fully automated open-ended scientific discovery. _arXiv preprint arXiv:2408.06292_ , 2024. 

- [24] Samuel Schmidgall, Yusheng Su, Ze Wang, Ximeng Sun, Jialian Wu, Xiaodong Yu, Jiang Liu, Zicheng Liu, and Emad Barsoum. Agent laboratory: Using llm agents as research assistants. _arXiv preprint arXiv:2501.04227_ , 2025. 

- [25] Xianghe Pang, Shuo Tang, Rui Ye, Yuxin Xiong, Bolun Zhang, Yanfeng Wang, and Siheng Chen. Selfalignment of large language models via monopolylogue-based social scene simulation. In _International Conference on Machine Learning_ , pages 39416–39447. PMLR, 2024. 

- [26] Shuo Tang, Xianghe Pang, Zexi Liu, Bohan Tang, Rui Ye, Tian Jin, Xiaowen Dong, Yanfeng Wang, and Siheng Chen. Synthesizing post-training data for llms through multi-agent simulation. _arXiv preprint arXiv:2410.14251_ , 2024. 

- [27] Yilun Du, Shuang Li, Antonio Torralba, Joshua B Tenenbaum, and Igor Mordatch. Improving factuality and reasoning in language models through multiagent debate. In _Forty-first International Conference on Machine Learning_ , 2024. 

- [28] Tian Liang, Zhiwei He, Wenxiang Jiao, Xing Wang, Yan Wang, Rui Wang, Yujiu Yang, Shuming Shi, and Zhaopeng Tu. Encouraging divergent thinking in large language models through multi-agent debate. In Yaser Al-Onaizan, Mohit Bansal, and Yun-Nung Chen, editors, _Proceedings of the 2024 Conference on Empirical Methods in Natural Language Processing_ , pages 17889–17904, Miami, Florida, USA, November 2024. Association for Computational Linguistics. 

- [29] Weize Chen, Yusheng Su, Jingwei Zuo, Cheng Yang, Chenfei Yuan, Chi-Min Chan, Heyang Yu, Yaxi Lu, Yi-Hsin Hung, Chen Qian, et al. Agentverse: Facilitating multi-agent collaboration and exploring emergent behaviors. In _The Twelfth International Conference on Learning Representations_ , 2024. 

- [30] Jiayi Zhang, Jinyu Xiang, Zhaoyang Yu, Fengwei Teng, Xiong-Hui Chen, Jiaqi Chen, Mingchen Zhuge, Xin Cheng, Sirui Hong, Jinlin Wang, Bingnan Zheng, Bang Liu, Yuyu Luo, and Chenglin Wu. AFlow: Automating agentic workflow generation. In _The Thirteenth International Conference on Learning Representations_ , 2025. 

- [31] Zijun Liu, Yanzhe Zhang, Peng Li, Yang Liu, and Diyi Yang. A dynamic llm-powered agent network for task-oriented agent collaboration. In _First Conference on Language Modeling_ , 2024. 

- [32] Mingchen Zhuge, Wenyi Wang, Louis Kirsch, Francesco Faccio, Dmitrii Khizbullin, and Jürgen Schmidhuber. Gptswarm: Language agents as optimizable graphs. In _Forty-first International Conference on Machine Learning_ , 2024. 

- [33] Jason Wei, Xuezhi Wang, Dale Schuurmans, Maarten Bosma, Fei Xia, Ed Chi, Quoc V Le, Denny Zhou, et al. Chain-of-thought prompting elicits reasoning in large language models. _Advances in neural information processing systems_ , 35:24824–24837, 2022. 

- [34] Qingyun Wu, Gagan Bansal, Jieyu Zhang, Yiran Wu, Beibin Li, Erkang Zhu, Li Jiang, Xiaoyun Zhang, Shaokun Zhang, Jiale Liu, et al. Autogen: Enabling next-gen llm applications via multi-agent conversation. In _ICLR 2024 Workshop on Large Language Model (LLM) Agents_ , 2024. 

11 

- [35] Xuezhi Wang, Jason Wei, Dale Schuurmans, Quoc V Le, Ed H Chi, Sharan Narang, Aakanksha Chowdhery, and Denny Zhou. Self-consistency improves chain of thought reasoning in language models. In _The Eleventh International Conference on Learning Representations_ , 2024. 

- [36] Aman Madaan, Niket Tandon, Prakhar Gupta, Skyler Hallinan, Luyu Gao, Sarah Wiegreffe, Uri Alon, Nouha Dziri, Shrimai Prabhumoye, Yiming Yang, et al. Self-refine: Iterative refinement with self-feedback. _Advances in Neural Information Processing Systems_ , 36, 2024. 

- [37] Chen Qian, Zihao Xie, YiFei Wang, Wei Liu, Kunlun Zhu, Hanchen Xia, Yufan Dang, Zhuoyun Du, Weize Chen, Cheng Yang, Zhiyuan Liu, and Maosong Sun. Scaling large language model-based multi-agent collaboration. In _The Thirteenth International Conference on Learning Representations_ , 2025. 

- [38] Shalev Lifshitz, Sheila A. McIlraith, and Yilun Du. Multi-agent verification: Scaling test-time compute with goal verifiers. In _Workshop on Reasoning and Planning for Large Language Models_ , 2025. 

- [39] Md Ashraful Islam, Mohammed Eunus Ali, and Md Rizwan Parvez. Mapcoder: Multi-agent code generation for competitive problem solving. In _Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers)_ , pages 4912–4944, 2024. 

- [40] Yue Hu, Yuzhu Cai, Yaxin Du, Xinyu Zhu, Xiangrui Liu, Zijie Yu, Yuchen Hou, Shuo Tang, and Siheng Chen. Self-evolving multi-agent networks for software development. In _The Thirteenth International Conference on Learning Representations_ , 2025. 

- [41] Xiangru Tang, Anni Zou, Zhuosheng Zhang, Ziming Li, Yilun Zhao, Xingyao Zhang, Arman Cohan, and Mark Gerstein. Medagents: Large language models as collaborators for zero-shot medical reasoning. In _Findings of the Association for Computational Linguistics ACL 2024_ , pages 599–621, 2024. 

- [42] Mengkang Hu, Yuhang Zhou, Wendong Fan, Yuzhou Nie, Bowei Xia, Tao Sun, Ziyu Ye, Zhaoxuan Jin, Yingru Li, Zeyu Zhang, Yifeng Wang, Qianshuo Ye, Ping Luo, and Guohao Li. Owl: Optimized workforce learning for general multi-agent assistance in real-world task automation, 2025. 

- [43] Shunyu Yao, Jeffrey Zhao, Dian Yu, Nan Du, Izhak Shafran, Karthik R Narasimhan, and Yuan Cao. React: Synergizing reasoning and acting in language models. In _The Eleventh International Conference on Learning Representations_ , 2023. 

- [44] Vighnesh Subramaniam, Yilun Du, Joshua B. Tenenbaum, Antonio Torralba, Shuang Li, and Igor Mordatch. Multiagent finetuning: Self improvement with diverse reasoning chains. In _The Thirteenth International Conference on Learning Representations_ , 2025. 

- [45] Guibin Zhang, Yanwei Yue, Xiangguo Sun, Guancheng Wan, Miao Yu, Junfeng Fang, Kun Wang, Tianlong Chen, and Dawei Cheng. G-designer: Architecting multi-agent communication topologies via graph neural networks. _arXiv preprint arXiv:2410.11782_ , 2024. 

- [46] Guibin Zhang, Yanwei Yue, Zhixun Li, Sukwon Yun, Guancheng Wan, Kun Wang, Dawei Cheng, Jeffrey Xu Yu, and Tianlong Chen. Cut the crap: An economical communication pipeline for LLM-based multi-agent systems. In _The Thirteenth International Conference on Learning Representations_ , 2025. 

- [47] Yuanshuo Zhang, Yuchen Hou, Bohan Tang, Shuo Chen, Muhan Zhang, Xiaowen Dong, and Siheng Chen. Gnns as predictors of agentic workflow performances. _arXiv preprint arXiv:2503.11301_ , 2025. 

- [48] LangChain. Langchain. `https://www.langchain.com/langchain` , 2025. Accessed: 2025-05-09. 

- [49] LangGraph. Langgraph. `https://www.langchain.com/langgraph` , 2025. Accessed: 2025-05-09. 

- [50] Tianbao Xie, Fan Zhou, Zhoujun Cheng, Peng Shi, Luoxuan Weng, Yitao Liu, Toh Jing Hua, Junning Zhao, Qian Liu, Che Liu, Zeyu Liu, Yiheng Xu, Hongjin SU, Dongchan Shin, Caiming Xiong, and Tao Yu. Openagents: An open platform for language agents in the wild. In _First Conference on Language Modeling_ , 2024. 

- [51] Noah Shinn, Federico Cassano, Ashwin Gopinath, Karthik Narasimhan, and Shunyu Yao. Reflexion: Language agents with verbal reinforcement learning. _Advances in Neural Information Processing Systems_ , 36:8634–8652, 2023. 

- [52] Bytedance. Sandbox fusion: Versatile code sandbox for llms. `https://bytedance.github.io/ SandboxFusion/` , 2025. Accessed: 2025-05-09. 

- [53] Anthropic. Introducing the model context protocol. `https://www.anthropic.com/news/ model-context-protocol` , 2025. Accessed: 2025-05-09. 

12 

- [54] Ding Chen, Qingchen Yu, Pengyuan Wang, Wentao Zhang, Bo Tang, Feiyu Xiong, Xinchi Li, Minchuan Yang, and Zhiyu Li. xverify: Efficient answer verifier for reasoning model evaluations. _arXiv preprint arXiv:2504.10481_ , 2025. 

- [55] Dan Hendrycks, Collin Burns, Saurav Kadavath, Akul Arora, Steven Basart, Eric Tang, Dawn Song, and Jacob Steinhardt. Measuring mathematical problem solving with the math dataset. _NeurIPS_ , 2021. 

- [56] An Yang, Baosong Yang, Beichen Zhang, Binyuan Hui, Bo Zheng, Bowen Yu, Chengyuan Li, Dayiheng Liu, Fei Huang, Haoran Wei, Huan Lin, Jian Yang, Jianhong Tu, Jianwei Zhang, Jianxin Yang, Jiaxi Yang, Jingren Zhou, Junyang Lin, Kai Dang, Keming Lu, Keqin Bao, Kexin Yang, Le Yu, Mei Li, Mingfeng Xue, Pei Zhang, Qin Zhu, Rui Men, Runji Lin, Tianhao Li, Tingyu Xia, Xingzhang Ren, Xuancheng Ren, Yang Fan, Yang Su, Yichang Zhang, Yu Wan, Yuqiong Liu, Zeyu Cui, Zhenru Zhang, and Zihan Qiu. Qwen2.5 technical report. _arXiv preprint arXiv:2412.15115_ , 2024. 

- [57] OpenAI. Gpt-4o mini: advancing cost-efficient intelligence. https://openai.com/index/gpt-4o-miniadvancing-cost-efficient-intelligence/, 2024. Accessed: 2025-01-23. 

- [58] OpenAI. Hello gpt-4o. `https://openai.com/index/hello-gpt-4o/` , 2024. Accessed: 2025-01-23. 

- [59] OpenAI. Introducing gpt-4.1 in the api. `https://openai.com/index/gpt-4-1/` , 2025. Accessed: 2025-05-09. 

- [60] Luyu Gao, Aman Madaan, Shuyan Zhou, Uri Alon, Pengfei Liu, Yiming Yang, Jamie Callan, and Graham Neubig. Pal: Program-aided language models. In _International Conference on Machine Learning_ , pages 10764–10799. PMLR, 2023. 

- [61] Wang Ling, Dani Yogatama, Chris Dyer, and Phil Blunsom. Program induction by rationale generation: Learning to solve and explain algebraic word problems. In _Proceedings of the 55th Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers)_ , pages 158–167, 2017. 

- [62] Xiaoxuan Wang, Ziniu Hu, Pan Lu, Yanqiao Zhu, Jieyu Zhang, Satyen Subramaniam, Arjun R Loomba, Shichang Zhang, Yizhou Sun, and Wei Wang. Scibench: Evaluating college-level scientific problemsolving abilities of large language models. In _Forty-first International Conference on Machine Learning_ , 2024. 

- [63] David Rein, Betty Li Hou, Asa Cooper Stickland, Jackson Petty, Richard Yuanzhe Pang, Julien Dirani, Julian Michael, and Samuel R Bowman. Gpqa: A graduate-level google-proof q&a benchmark. _arXiv preprint arXiv:2311.12022_ , 2023. 

- [64] Yubo Wang, Xueguang Ma, Ge Zhang, Yuansheng Ni, Abhranil Chandra, Shiguang Guo, Weiming Ren, Aaran Arulraj, Xuan He, Ziyan Jiang, Tianle Li, Max Ku, Kai Wang, Alex Zhuang, Rongqi Fan, Xiang Yue, and Wenhu Chen. MMLU-pro: A more robust and challenging multi-task language understanding benchmark. In _The Thirty-eight Conference on Neural Information Processing Systems Datasets and Benchmarks Track_ , 2024. 

- [65] Ankit Pal, Logesh Kumar Umapathi, and Malaikannan Sankarasubbu. Medmcqa: A large-scale multisubject multi-choice dataset for medical domain question answering. In _Conference on health, inference, and learning_ , pages 248–260. PMLR, 2022. 

- [66] Mark Chen, Jerry Tworek, Heewoo Jun, Qiming Yuan, Henrique Ponde De Oliveira Pinto, Jared Kaplan, Harri Edwards, Yuri Burda, Nicholas Joseph, Greg Brockman, et al. Evaluating large language models trained on code. _arXiv preprint arXiv:2107.03374_ , 2021. 

- [67] Jacob Austin, Augustus Odena, Maxwell Nye, Maarten Bosma, Henryk Michalewski, David Dohan, Ellen Jiang, Carrie Cai, Michael Terry, Quoc Le, et al. Program synthesis with large language models. _arXiv preprint arXiv:2108.07732_ , 2021. 

- [68] Grégoire Mialon, Clémentine Fourrier, Thomas Wolf, Yann LeCun, and Thomas Scialom. GAIA: a benchmark for general AI assistants. In _The Twelfth International Conference on Learning Representations_ , 2024. 

- [69] Woosuk Kwon, Zhuohan Li, Siyuan Zhuang, Ying Sheng, Lianmin Zheng, Cody Hao Yu, Joseph Gonzalez, Hao Zhang, and Ion Stoica. Efficient memory management for large language model serving with pagedattention. In _Proceedings of the 29th Symposium on Operating Systems Principles_ , pages 611–626, 2023. 

13 

|Protocol|LLM-2step|LLM-xVerify|Rule-HF|Rule-DyLAN|Rule-Hendry.|
|---|---|---|---|---|---|
|Accuracy|**98.59**|**98.35**|41.65|65.65|27.29|



Table 4: Accuracy comparisons of 5 different evaluation protocols by human’s manual check. This measurement is based on MATH dataset. The two LLM-based evaluation protocols achieve significantly higher agreement with human evaluation. LLM-2step is based on two-time inference of Llama-3.3-70B-Instruct while LLM-xVerify is based on one-time inference of a 9B-sized LLM. Generally, LLM-xVerify achieves the best effectiveness-efficiency trade-off. 

|Method|Lev|el 1|Le|vel 2|Le|vel 3|A|ll|
|---|---|---|---|---|---|---|---|---|
||Acc|Cost|Acc|Cost|Acc|Cost|Acc|Cost|
||||GPT-4.|1-mini|||||
|Single|16.98|663|16.28|353|0.0|1529|13.94|638|
|SC|22.64|4504|15.12|2412|0.0|8484|15.15|4041|
|Debate|24.53|4388|16.28|4870|7.69|12972|17.58|5992|
|AgentVerse|32.08|7174|15.12|7368|7.69|15753|19.39|8627|
|OWL-Roleplaying|35.85|51543|25.58|58881|11.54|107635|26.67|64206|
|MASLab-ReAct|33.96|19866|26.74|41768|11.54|55743|26.67|36935|
||||GPT|-4.1|||||
|Single|24.53|394|16.28|470|3.85|1378|16.97|589|
|SC|20.75|3037|16.28|3362|11.54|11786|16.97|4585|
|Debate|32.08|4103|24.42|4339|11.54|11564|24.85|5402|
|AgentVerse|28.30|6876|18.60|5995|3.85|11034|19.39|7072|
|OWL-Roleplaying|43.40|48073|30.23|101827|26.92|101986|33.94|84586|
|MASLab-ReAct|56.60|18278|47.67|35636|19.23|43525|46.06|31303|



Table 5: Comparisons of performance and cost on GAIA. The performance is evaluated by accuracy while the cost is evaluated by the number of costed text tokens per query. 

## **A Limitations** 

Despite being the most comprehensive codebase in LLM-based MAS, there are still methods that have not been incorporated yet. Secondly, despite that most of the benchmarks in this paper are commonly used in MAS literature, they are not specifically designed for the field of MAS. However, this is not a unique limitation of this paper. We will continually working on this codebase to support more methods and benchmarks. We also plan to design new benchmarks specifically for MAS in the future. 

## **B Broader Impacts** 

This paper introduces a unified, comprehensive, and research-friendly codebase for the community of LLM-based MAS. This resource alleviates the burden of reproduction for researchers, enabling them to allocate more effort to innovative algorithm design. It fosters fair comparisons across studies, lowers the entry barrier for newcomers, and facilitates secondary development, thereby accelerating progress in the field. 

While potential negative impacts of our approach mirror those associated with large language models—such as ethical concerns and risks of misuse—these issues are intrinsic to LLM usage in general and do not necessitate further elaboration here. 

14 



<!-- Start of picture text -->
BH Single GB Cot GB sc @ LLM-Debate  AutoGen @ DyLAN © AgentVerse A MacNet A MAD<br>MATH (T) GSM-Hard (T) AQUA-RAT (T) AIME-2024 (T)<br>O° fia] Bo A GB 36 A B<br>g 78 9 56 g 80 ae @ 32<br>F 4 § § 5 oo<br>££76= aeE54= oa———p—o4 2fs5 78 B 2£28=  a A<br>@74 g 5 A & g A 224g fo)<br>-F Oo 768 20 «~«<br>2000 4000 2000 4000 2000 4000 6000 5000 10000 15000<br>Token Cost Token Cost Token Cost Token Cost<br>SciBench (T) GPQA-Diamond (Tt) MMLU-Pro (T) MedMCQA (tT)<br>a o<br>28 o og 56<br>oQo5 26 re)o552 B Bo (e)o& /2 aa? o/4Q6 a ime)<br>e = 9 E E69 E72} ———————<br>S24 2% € € A<br>a” | A & 260" a 2s<br>44 70 A<br>22 Bo o A i}<br>5000 10000 5000 10000 15000 2500 5000 7500 0 2000 4000 6000<br>Token Cost Token Cost Token Cost Token Cost<br>HumanEval (T) MBPP (T) Avg-Value (T) Avg-Rank (1)<br>10 a<br>90 72 63 e<br>¢5 op ,@°q2aoaae} Se ze ,8<br>oO 568m = ® A A<br>E75 oO A oO 60 A U<br>£ A E E 5 6<br>2ov £04ov a eo,vo fe)-E  & Oo°<br>60 2 60 a 5 4 B<br>a A 54g *<br>0 5000 10000 0 2000 4000 6000 2500 5000 7500 5 10<br>Token Cost Token Cost Token Cost Cost Rank<br><!-- End of picture text -->

to simulate browser behavior. However, we observe occasional instability during experimentation. To reduce both runtime and token consumption, we impose strict operational constraints: a 30,000 ms timeout for website navigation, a 20,000 ms timeout for page loading, and a hard cap of 10 web interaction turns per task. Tasks exceeding this limit are forcibly terminated. The document processing tool supports parsing a wide range of document formats. For web content extraction and parsing specifically, we employ an external tool called Firecrawl. The video analysis tool extracts 28 evenly spaced frames from each video and uses OpenAI’s Whisper-1 model to transcribe the audio into text. These frames, along with the transcribed text, are jointly input into a vision-language model for multimodal analysis. The audio analysis tool processes audio files by encoding them in Base64 format and feeding them into the GPT-4o-mini-audio-preview model for analysis. The code execution tool operates by spawning a subprocess that simulates the writing and execution of Python code in a sandboxed environment. The search tool integrates multiple retrieval backends such as Google, DuckDuckGo, Wikipedia, and Archive.org, allowing agents to gather information from diverse sources. 

**Memory.** We simplify the process of memory storage and retrieval for the model. To strike a balance between performance and token efficiency during memory retrieval, we impose a maximum limit of 51,200 tokens on the retrieved content. Similarly, we cap the maximum token length for model output at 12,800 tokens. 

**Failure analysis.** Throughout the experiments, we log MAS outputs and failure cases. After the experiments, we select results from the OWL-Roleplaying method running on the GPT-4.1 model and perform a detailed categorization and statistical analysis of the errors encountered. 

## **D Re-Implementation Notes** 

### **D.1 MAS for General Tasks** 

**AutoGen [34].** Based on the examples proposed in the paper of AutoGen [34] and the guidelines provided in its official documentation ( `https://microsoft.github.io/autogen/0.2/` ), we have developed a foundational workflow that embodies its conversational characteristics, tailored to solve basic text-level problems with code execution and memory retention. 

**AgentVerse [29].** AgentVerse provides several dataset-specific versions including those for MGSM and HumanEval. we have replicated workflows corresponding to datasets such as HumanEval and MGSM, aligning with those presented in the original AgentVerse repository ( `https://github. com/OpenBMB/AgentVerse` ) and its paper. Additionally, we develop a general workflow capable of solving common problems. 

**LLM-Debate [27].** We notice that the official code in `https://github.com/ composable-models/llm_multiagent_debate` is not readily executable and that the code relies on an string operation for extracting answers from responses, which frequently causes errors. Therefore, we slightly modify the code by making it bug-free and rely on LLM for aggregating final answers. This significantly enhance the performance of LLM-Debate as it no longer encounter errors during execution. 

**GPTSwarm [32].** The official code of GPTSwarm `https://github.com/metauto-ai/ GPTSwarm/tree/main/experiments` contains versions for MMLU, HumanEval, GAIA, Crosswords. We implement the version of HumanEval and MMLU, and based on the logic of MMLU, we develop a version for general problem-solving. 

**DyLAN [31].** The official code in `https://github.com/SALT-NLP/DyLAN` uses a custom answer extraction function to return final mathematical results. To ensure fair comparison across evaluation protocols, we modify the return logic of the original code while preserving the task-specific initialization parameters as defined in the original implementation. 

**Self-Refine [36].** The official implementation in `https://github.com/madaan/self-refine` provides dataset-specific prompt examples. Following its logic for solving mathematical problems, we develop code for general problem-solving. Additionally, since the original code’s extraction logic for mathematical problems is not robust and often results in syntactically incorrect code, we redesign the extraction function to more effectively extract executable code from raw LLM responses. 

16 

**MacNet [37].** We simplify the structure of waiting.py in `https://github.com/OpenBMB/ ChatDev/tree/macnet` when reproducing MacNet, but keep its functionality consistent, mainly in terms of high maintainability and memory safety. In addition to this, we develop a version for general cases according to their implementation for SRDD. 

**Reflexion [51].** For the method in `https://github.com/noahshinn/reflexion` , we implement the HumanEval and MBPP modes for programming tasks. Additionally, based on the logic of the programming tasks, we develop a version for general problem-solving. 

**ADAS [18].** We notice that the official code in `https://github.com/ShengranHu/ADAS` does not support flexible selection of execution models, which makes it difficult to evaluate the effect of the MAS module and to develop a heterogeneous MAS version. Therefore, we slightly modify the code to fix existing bugs and to allow users to specify both the meta LLM and the execution LLM during optimization, as well as choose the execution model during inference. We also set the temperature to zero and ensure that when using GPT-3.5 as the execution model (same as in the original repo), the output remains exactly the same. These improvements significantly enhance the compatibility and extensibility of ADAS. 

**AFlow [30].** The official code in `https://github.com/FoundationAgents/MetaGPT/tree/ main/examples/aflow` and `https://github.com/FoundationAgents/AFlow` is very complex and even buggy, we simplify the format and make sure that the core parts are fully aligned and bug free. In addition we use AsyncOpenAI when reproducing AFlow to speed up the optimization. 

**MAV [38].** We reproduce the MATH and MMLU versions of MAV and develope a general version based on the MATH version. 

### **D.2 MAS for Coding Tasks** 

**MetaGPT [20].** MetaGPT is an intricate system that presents a considerable challenge to analysis. Our research reveals that the efficacy of its communication infrastructure on the entire system is negligible, and its practical impact is confined to modest-scale projects. To facilitate comprehension, we streamline it into a linear framework, aligning it with the structure of the original paper. In fact, we find that the existing structure cannot be applied to datasets such as HumanEval and MBPP. 

**ChatDev [16].** ChatDev primarily focuses on the domain of software development. By leveraging natural language processing techniques, ChatDev enables seamless automation of the entire software development lifecycle, including the generation of GUIs (graphical user interfaces). The complexity of the resulting software is closely tied to the specificity of user-defined requirements. Based on the official ChatDev paper ([16]) and its official repository ( `https://github.com/OpenBMB/ ChatDev` ), we adapted a ChatDev workflow within the MAS-Lab framework tailored to SRDD (Software Requirement Description Dataset), aligning with the design principles and capabilities demonstrated in the original ChatDev system. 

**MapCoder [39].** Our implementation follows the official codebase from `https://github.com/ Md-Ashraful-Pramanik/MapCoder` , preserving its core methodology. However, we note that the original implementation uses a pre-processed version of the HumanEval dataset, which includes example test cases. To ensure a fair comparison across different methods, we do not use this preprocessed version. Instead, we augment the framework with a function that dynamically extracts test cases from the original HumanEval prompts. This modification does not affect MapCoder’s core logic but ensures all baselines are evaluated under identical conditions. 

**EvoMAC [40].** We collaborate with the authors of EvoMAC, who provide their official implementation to be integrated into our framework. The method remains unchanged. Together with the authors, we release this joint implementation as part of our open-source framework, maintaining full transparency and reproducibility. 

### **D.3 MAS for Mathematical Tasks** 

**MACM [21].** MACM is an MAS method specialized in solving mathematical problems using the code interpreter tool to assist problem solving. Since their official code is specifically designed for the usage of OpenAI’s Assistants interface, we follow the same LLM usage for this particular case. In the future, we plan to extend it to support OpenAI’s chat mode. 

17 

### **D.4 MAS for Scientific Tasks** 

**MedAgents [41].** The official code in `https://github.com/gersteinlab/MedAgents` supports multiple working modes. We fully reproduce all modes and set the default mode to match the original repository’s default configuration, keeping all other external parameters consistent with the original defaults. 

### **D.5 MAS for Tool-Required Tasks** 

**OWL-Roleplaying [42].** OWL ( `https://github.com/camel-ai/owl` ) is a framework for multiagent collaboration. This framework includes OWL-Roleplaying as a MAS method specifically designed for the GAIA benchmark [68]. This framework may introduce massive token consumption for each specific task/query. Considering the research-friendly nature of the our MASLab framework, several trade-offs and simplifications are made during the adaptation of this method to MASLab, with a focus on enhancing code readability and reducing computational costs. Overall, the main process of OWL is maintained during the adaptation while we limit the maximum retrying times considering economy. For example, we set stricter limitations on the use of the web tool to mitigate the substantial token costs associated with frequent web interactions. 

**MASLab-ReAct [43].** Building upon the toolkits from OWL, we propose a method MASLab-ReAct inspired by the ReAct [43] method. This method achieves better performance with lower cost compared to OWL-Roleplaying. 

18 

