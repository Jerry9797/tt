import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage
from langgraph.errors import GraphInterrupt
from langgraph.types import Command

from src.fastapi.app import (
    ChatRequest,
    build_chat_response,
    build_initial_state,
    execute_chat_request,
    resolve_thread_id,
    serialize_step_results,
)
from src.models.execution_result import StepExecutionResult, StepStatus, ToolCall
from src.nodes.ask_human_node import ask_human
from src.nodes.plan_nodes import finalize_execution, plan_executor_node, replan_node
from src.nodes.response_generator_node import build_response_generation_payload


class AgentStateContractTests(unittest.TestCase):
    def test_build_initial_state_uses_minimal_contract(self):
        state = build_initial_state(ChatRequest(query=None, history=None))

        self.assertEqual(state["original_query"], "")
        self.assertEqual(state["plan"], [])
        self.assertEqual(state["current_step"], 0)
        self.assertEqual(state["messages"], [])
        self.assertNotIn("past_steps", state)
        self.assertNotIn("response", state)

    def test_build_chat_response_maps_final_response(self):
        response = build_chat_response(
            result={
                "original_query": "用户问题",
                "faq_response": "FAQ",
                "plan": ["step-1"],
                "final_response": "最终答案",
            },
            request=ChatRequest(query="用户问题"),
            thread_id="thread-1",
            status="success",
        )

        self.assertEqual(response.query, "用户问题")
        self.assertEqual(response.response, "最终答案")
        self.assertEqual(response.faq_response, "FAQ")

    def test_build_chat_response_maps_clarification_question(self):
        response = build_chat_response(
            result={
                "original_query": "用户问题",
                "clarification_question": "请补充商户ID",
            },
            request=ChatRequest(query="用户问题"),
            thread_id="thread-1",
            status="need_clarification",
        )

        self.assertEqual(response.status, "need_clarification")
        self.assertEqual(response.response, "请补充商户ID")

    def test_response_generation_payload_prefers_original_query(self):
        payload = build_response_generation_payload(
            {
                "original_query": "原始问题",
                "rewritten_query": "改写问题",
                "step_results": [],
            }
        )

        self.assertEqual(payload["query"], "原始问题")

    def test_finalize_execution_uses_original_query_and_final_response(self):
        step_result = StepExecutionResult(
            step_index=0,
            step_description="检查数据",
            status=StepStatus.SUCCESS,
            output_result="完成",
        )

        result = finalize_execution(
            {
                "original_query": "原始问题",
                "intent": "other",
                "plan": ["检查数据"],
                "step_results": [step_result],
                "final_response": "最终答案",
            }
        )

        summary = result["execution_summary"]
        self.assertEqual(summary.query, "原始问题")
        self.assertEqual(summary.final_response, "最终答案")

    def test_resolve_thread_id_generates_unique_value(self):
        with patch("src.fastapi.app.uuid4", return_value=SimpleNamespace(hex="abc123")):
            self.assertEqual(resolve_thread_id(None), "thread_abc123")

    def test_serialize_step_results_includes_tool_calls(self):
        step_result = StepExecutionResult(
            step_index=0,
            step_description="检查数据",
            status=StepStatus.SUCCESS,
            tool_calls=[ToolCall(tool_name="lookup", arguments={"shop_id": 1})],
        )

        serialized = serialize_step_results([step_result])

        self.assertEqual(serialized[0].tool_calls[0]["tool_name"], "lookup")


class HumanInTheLoopFlowTests(unittest.IsolatedAsyncioTestCase):
    @patch("src.nodes.ask_human_node.interrupt", return_value="商户1002")
    async def test_ask_human_returns_resume_command(self, interrupt_mock):
        command = await ask_human(
            {
                "original_query": "查询商户",
                "messages": [],
                "plan": [],
                "current_step": 0,
                "clarification_question": "请补充商户ID",
                "resume_target": "plan_executor_node",
            }
        )

        self.assertIsInstance(command, Command)
        self.assertEqual(command.goto, "plan_executor_node")
        self.assertFalse(command.update["awaiting_user_input"])
        self.assertIsNone(command.update["clarification_question"])
        self.assertIsNone(command.update["resume_target"])
        self.assertEqual(command.update["resume_input"], "商户1002")
        self.assertEqual(len(command.update["messages"]), 2)
        interrupt_mock.assert_called_once_with("请补充商户ID")

    async def test_plan_executor_interrupts_without_persisting_running_step(self):
        mock_agent = SimpleNamespace(
            ainvoke=AsyncMock(
                return_value={"messages": [AIMessage(content="ask_human 请补充商户ID")]}
            )
        )
        mcp_manager = SimpleNamespace(get_all_tools=lambda: [])

        with patch("src.nodes.plan_nodes.build_executor_prompt", return_value="prompt"), \
             patch("src.nodes.plan_nodes.get_gpt_model", return_value=object()), \
             patch("src.nodes.plan_nodes.create_agent", return_value=mock_agent), \
             patch("src.mcp.get_mcp_manager", return_value=mcp_manager):
            command = await plan_executor_node(
                {
                    "original_query": "查询商户",
                    "rewritten_query": "查询商户",
                    "messages": [],
                    "plan": ["检查召回"],
                    "current_step": 0,
                }
            )

        self.assertIsInstance(command, Command)
        self.assertEqual(command.goto, "ask_human")
        self.assertTrue(command.update["awaiting_user_input"])
        self.assertEqual(command.update["clarification_question"], "请补充商户ID")
        self.assertEqual(command.update["resume_target"], "plan_executor_node")
        self.assertNotIn("step_results", command.update)

    async def test_plan_executor_consumes_resume_input_on_success(self):
        mock_agent = SimpleNamespace(
            ainvoke=AsyncMock(return_value={"messages": [AIMessage(content="处理完成")]})
        )
        mcp_manager = SimpleNamespace(get_all_tools=lambda: [])

        with patch("src.nodes.plan_nodes.build_executor_prompt", return_value="prompt"), \
             patch("src.nodes.plan_nodes.get_gpt_model", return_value=object()), \
             patch("src.nodes.plan_nodes.create_agent", return_value=mock_agent), \
             patch("src.mcp.get_mcp_manager", return_value=mcp_manager):
            result = await plan_executor_node(
                {
                    "original_query": "查询商户",
                    "rewritten_query": "查询商户",
                    "messages": [],
                    "plan": ["检查召回"],
                    "current_step": 0,
                    "resume_input": "商户1002",
                }
            )

        self.assertEqual(result["current_step"], 1)
        self.assertFalse(result["awaiting_user_input"])
        self.assertIsNone(result["clarification_question"])
        self.assertIsNone(result["resume_target"])
        self.assertIsNone(result["resume_input"])
        self.assertEqual(result["step_results"][0].status, StepStatus.SUCCESS)
        self.assertTrue(result["messages"][0].content.startswith("▶️"))

    async def test_plan_executor_routes_to_finalize_when_plan_is_done(self):
        result = await plan_executor_node(
            {
                "original_query": "查询商户",
                "rewritten_query": "查询商户",
                "messages": [],
                "plan": ["检查召回"],
                "current_step": 1,
            }
        )

        self.assertIsInstance(result, Command)
        self.assertEqual(result.goto, "finalize_execution_node")

    async def test_replan_routes_to_finalize_on_respond(self):
        mock_llm = SimpleNamespace(
            ainvoke=AsyncMock(return_value=AIMessage(content='{"decision":"respond","reasoning":"enough"}'))
        )

        with patch("src.prompt.prompt_loader.get_prompt", return_value="{query}\n{plan_list}\n{completed_steps}\n{remaining_steps}\n{sop_note}"), \
             patch("src.nodes.plan_nodes.get_gpt_model", return_value=mock_llm):
            result = await replan_node(
                {
                    "rewritten_query": "查询商户",
                    "plan": ["检查召回"],
                    "current_step": 1,
                    "step_results": [
                        StepExecutionResult(
                            step_index=0,
                            step_description="检查召回",
                            status=StepStatus.SUCCESS,
                            output_result="完成",
                        )
                    ],
                    "intent": "other",
                }
            )

        self.assertIsInstance(result, Command)
        self.assertEqual(result.goto, "finalize_execution_node")


class ExecuteChatRequestSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_chat_request_success_smoke(self):
        result_state = {
            "original_query": "用户问题",
            "final_response": "最终答案",
            "messages": [],
            "plan": [],
            "current_step": 0,
        }
        fake_graph = SimpleNamespace(
            ainvoke=AsyncMock(return_value=result_state),
            aget_state=AsyncMock(return_value=SimpleNamespace(tasks=[], values=result_state)),
        )

        with patch("src.fastapi.app.build_graph", new=AsyncMock(return_value=fake_graph)), \
             patch("src.fastapi.app.cleanup_runtime", new=AsyncMock()):
            result, status, thread_id = await execute_chat_request(
                ChatRequest(query="用户问题", thread_id="thread-1")
            )

        self.assertEqual(status, "success")
        self.assertEqual(thread_id, "thread-1")
        self.assertEqual(result["final_response"], "最终答案")

    async def test_execute_chat_request_interrupt_smoke(self):
        interrupt_task = SimpleNamespace(interrupts=[SimpleNamespace(value="请补充商户ID")])
        fake_graph = SimpleNamespace(
            ainvoke=AsyncMock(side_effect=GraphInterrupt()),
            aget_state=AsyncMock(return_value=SimpleNamespace(tasks=[interrupt_task], values={})),
        )

        with patch("src.fastapi.app.build_graph", new=AsyncMock(return_value=fake_graph)), \
             patch("src.fastapi.app.cleanup_runtime", new=AsyncMock()):
            result, status, thread_id = await execute_chat_request(
                ChatRequest(query="用户问题", thread_id="thread-1")
            )

        self.assertEqual(status, "need_clarification")
        self.assertEqual(thread_id, "thread-1")
        self.assertEqual(result["clarification_question"], "请补充商户ID")


if __name__ == "__main__":
    unittest.main()
