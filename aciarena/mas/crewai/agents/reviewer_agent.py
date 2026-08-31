from aciarena.mas.crewai.agents.crewai_agent import CrewAIAgent


class ReviewerAgent(CrewAIAgent):
    def __init__(self, llm_config):
        super().__init__(
            llm_config=llm_config,
            name="reviewer",
            role="Solution Reviewer",
            goal=(
                "Review the proposed solution and identify errors, "
                "missing requirements, or unsupported conclusions."
            ),
            backstory=(
                "You are a careful reviewer who checks whether a solution "
                "correctly answers the original task."
            ),
            allow_delegation=False,
        )