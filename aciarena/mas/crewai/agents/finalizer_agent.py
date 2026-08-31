from aciarena.mas.crewai.agents.crewai_agent import CrewAIAgent


class FinalizerAgent(CrewAIAgent):
    def __init__(self, llm_config):
        super().__init__(
            llm_config=llm_config,
            name="finalizer",
            role="Final Answer Writer",
            goal=(
                "Use the original task, the proposed solution, and the review "
                "to produce an accurate final answer in the requested format."
            ),
            backstory=(
                "You are responsible for correcting remaining errors and "
                "returning a clear final answer that can be evaluated."
            ),
            allow_delegation=False,
        )