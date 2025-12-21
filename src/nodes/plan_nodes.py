from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate

from src.config.llm import q_max
from src.graph_state import AgentState, Plan
from src.prompt.plan import planner_prompt_template

def planning_node(state: AgentState):
    faq_query = state['faq_query']
    plan_parser = JsonOutputParser(pydantic_object=Plan)
    planner_prompt = PromptTemplate(
        template=planner_prompt_template,
        input_variables=["query"],
        partial_variables={"format_instructions": plan_parser.get_format_instructions()},
    )

    chain = planner_prompt | q_max | JsonOutputParser()
    result = chain.invoke({"query": faq_query, "past_steps": ""})
    return {"plan": result.get('steps', []), "current_step": 0}

def plan_executor_node(state: AgentState):
    # 此处为示例占位，实际需根据 plan 执行
    return {"completed_steps": ["executed_step"]}

def replan_node(state: AgentState):
    pass
