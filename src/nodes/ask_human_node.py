from langchain_core.messages import HumanMessage
from langgraph.types import Command, interrupt

from src.graph_state import AgentState


async def ask_human_node(state: AgentState):
    question = state.get("human_question")
    resume_node = state.get("human_resume_node")

    if not question:
        raise ValueError("ask_human_node requires human_question")
    if not resume_node:
        raise ValueError("ask_human_node requires human_resume_node")

    user_response = interrupt(question)

    return Command(
        goto=resume_node,
        update={
            "messages": [HumanMessage(content=user_response)],
            "human_question": None,
            "human_resume_node": None,
        },
    )
