from aciarena.mas.crewai.agents.crewai_agent import CrewAIAgent


class SolverAgent(CrewAIAgent):
    def __init__(self, llm_config):
        super().__init__(
            llm_config=llm_config,
            name="solver",
            role="Problem Solver",
            goal=(
                "Analyze the user's task carefully and produce "
                "an accurate initial solution."
            ),
            backstory=(
                "You are an experienced problem solver who checks "
                "requirements, calculations, and logical steps carefully."
            ),
            allow_delegation=False,
        )