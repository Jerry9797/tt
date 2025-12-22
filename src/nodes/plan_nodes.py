from langchain.agents import create_agent
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate

from src.config.llm import q_max
from src.graph_state import AgentState, Plan
from src.prompt.plan import planner_prompt_template
from src.tools import check_low_star_merchant, check_sensitive_merchant


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
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)
    
    if current_step < len(plan):
        step_description = plan[current_step]
        print("正在执行：", step_description)
        print(f"Executing step {current_step + 1}/{len(plan)}: {step_description}")
        # 模拟执行结果
        agent = create_agent(
            system_prompt="严格按照输入执行步骤。如果信息缺失，输出你需要的信息，向human询问",
            model=q_max,
            tools=[check_low_star_merchant, check_sensitive_merchant],
        )

        execution_result = agent.invoke({"messages": step_description})
        return {
            "current_step": current_step + 1,
            "past_steps": [(step_description, execution_result)]
        }
    
    return {"current_step": current_step}

def replan_node(state: AgentState):
    pass
