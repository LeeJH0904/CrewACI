from aciarena.agent_components import BaseAgent


class CrewAIAgent(BaseAgent):
    def __init__(
        self,
        llm_config,
        name: str,
        role: str,
        goal: str,
        backstory: str,
        allow_delegation: bool = False,
    ):
        self.role = role
        self.goal = goal
        self.backstory = backstory
        self.allow_delegation = allow_delegation

        profile = self.render_profile(
            role=role,
            goal=goal,
            backstory=backstory,
        )

        super().__init__(
            llm_config=llm_config,
            name=name,
            profile=profile,
            tools=[],
        )

        self.update_memory(role="system", content=self.profile)

    @staticmethod
    def render_profile(role: str, goal: str, backstory: str) -> str:
        return (
            f"You are {role}.\n"
            f"Your backstory is: {backstory}\n"
            f"Your personal goal is: {goal}"
        )

    def step(self, query: str, *args, **kwargs) -> str:
        self.memory.conversation[0]["content"] = self.profile
        self.update_memory(role="user", content=query)

        messages = self.retrieve_memory()
        response = self.llm.call_llm(messages)

        self.update_memory(role="assistant", content=response)
        return response