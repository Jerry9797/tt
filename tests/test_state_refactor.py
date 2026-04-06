import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from langchain_core.messages import AIMessage, HumanMessage
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
from src.nodes.ask_human_node import ask_human_node
from src.nodes.plan_nodes import (
    _extract_token_usage,
    finalize_execution,
    plan_executor_node,
    replan_node,
)
from src.nodes.query_rewrite_node import query_rewrite_node
from src.nodes.response_generator_node import build_response_generation_payload


class AgentStateContractTests(unittest.TestCase):
    def test_build_initial_state_uses_minimal_contract(self):
        state = build_initial_state(ChatRequest(query=None, history=None))

        self.assertEqual(state["original_query"], "")
        self.assertEqual(state["plan"], [])
        self.assertEqual(state["current_step"], 0)
        self.assertEqual(state["messages"], [])

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
    async def test_ask_human_node_appends_response_and_resumes(self, interrupt_mock):
        command = await ask_human_node(
            {
                "original_query": "查询商户",
                "messages": [],
                "plan": [],
                "current_step": 0,
                "human_question": "请补充商户ID",
                "human_resume_node": "plan_executor_node",
            }
        )

        self.assertIsInstance(command, Command)
        self.assertEqual(command.goto, "plan_executor_node")
        self.assertIsNone(command.update["human_question"])
        self.assertIsNone(command.update["human_resume_node"])
        self.assertEqual(len(command.update["messages"]), 1)
        self.assertEqual(command.update["messages"][0].content, "商户1002")
        interrupt_mock.assert_called_once_with("请补充商户ID")

    async def test_plan_executor_routes_to_ask_human(self):
        mock_llm_response = AIMessage(content="")
        mock_llm_response.tool_calls = [
            {"name": "ask_human", "args": {"question": "请补充商户ID"}, "id": "tool_ask_human_1"}
        ]
        mock_llm = AsyncMock()
        mock_llm.bind_tools = Mock(return_value=mock_llm)
        mock_llm.ainvoke = AsyncMock(return_value=mock_llm_response)

        with patch("src.nodes.plan_nodes.get_gpt_model", return_value=mock_llm), \
             patch("src.prompt.prompt_loader.get_prompt", return_value="{query} {step_index} {task} {context} {chat_history}"):
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
        self.assertEqual(command.goto, "ask_human_node")
        self.assertEqual(command.update["human_question"], "请补充商户ID")
        self.assertEqual(command.update["human_resume_node"], "plan_executor_node")
        self.assertNotIn("step_results", command.update)
        self.assertTrue(any(msg.content.startswith("⏸️ 步骤") for msg in command.update["messages"]))

    async def test_plan_executor_skips_ask_human_tool_in_tool_results(self):
        mock_ai_response = AIMessage(content="")
        mock_ai_response.tool_calls = [
            {"name": "lookup", "args": {"id": 1}, "id": "tc1"},
            {"name": "ask_human", "args": {"question": "请补充商户ID"}, "id": "tc2"},
        ]
        mock_final_response = AIMessage(content="处理完成")
        mock_final_response.tool_calls = []

        mock_llm = AsyncMock()
        mock_llm.bind_tools = Mock(return_value=mock_llm)
        mock_llm.ainvoke = AsyncMock(side_effect=[mock_ai_response, mock_final_response])

        mock_tool = AsyncMock()
        mock_tool.name = "lookup"
        mock_tool.ainvoke = AsyncMock(return_value="result")

        with patch("src.nodes.plan_nodes.get_gpt_model", return_value=mock_llm), \
             patch("src.prompt.prompt_loader.get_prompt", return_value="{query} {step_index} {task} {context} {chat_history}"):
            command = await plan_executor_node(
                {
                    "original_query": "查询商户",
                    "rewritten_query": "查询商户",
                    "messages": [],
                    "plan": ["检查召回"],
                    "current_step": 0,
                },
                tools=[mock_tool],
            )

        self.assertIsInstance(command, Command)
        self.assertEqual(command.goto, "ask_human_node")
        mock_tool.ainvoke.assert_not_called()

    async def test_plan_executor_accumulates_token_usage(self):
        mock_ai_response = AIMessage(content="调用工具")
        mock_ai_response.tool_calls = [{"name": "lookup", "args": {"id": 1}, "id": "tc1"}]
        mock_ai_response.response_metadata = {
            "token_usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        }

        mock_final_response = AIMessage(content="处理完成")
        mock_final_response.tool_calls = []
        mock_final_response.response_metadata = {
            "token_usage": {"prompt_tokens": 80, "completion_tokens": 40, "total_tokens": 120}
        }

        mock_llm = AsyncMock()
        mock_llm.bind_tools = Mock(return_value=mock_llm)
        mock_llm.ainvoke = AsyncMock(side_effect=[mock_ai_response, mock_final_response])

        mock_tool = AsyncMock()
        mock_tool.name = "lookup"
        mock_tool.ainvoke = AsyncMock(return_value="result")

        with patch("src.nodes.plan_nodes.get_gpt_model", return_value=mock_llm), \
             patch("src.prompt.prompt_loader.get_prompt", return_value="{query} {step_index} {task} {context} {chat_history}"):
            result = await plan_executor_node(
                {
                    "original_query": "查询商户",
                    "rewritten_query": "查询商户",
                    "messages": [],
                    "plan": ["检查召回"],
                    "current_step": 0,
                },
                tools=[mock_tool],
            )

        step_result = result["step_results"][0]
        self.assertEqual(result["current_step"], 1)
        self.assertEqual(step_result.token_usage.total_tokens, 270)
        self.assertEqual(step_result.token_usage.prompt_tokens, 180)
        self.assertEqual(step_result.token_usage.completion_tokens, 90)

    async def test_plan_executor_can_reconsume_latest_human_message_after_resume(self):
        mock_llm_response = AIMessage(content="处理完成")
        mock_llm_response.tool_calls = []
        mock_llm = AsyncMock()
        mock_llm.bind_tools = Mock(return_value=mock_llm)
        mock_llm.ainvoke = AsyncMock(return_value=mock_llm_response)

        with patch("src.nodes.plan_nodes.get_gpt_model", return_value=mock_llm), \
             patch("src.prompt.prompt_loader.get_prompt", return_value="{query} {step_index} {task} {context} {chat_history}"):
            result = await plan_executor_node(
                {
                    "original_query": "查询商户",
                    "rewritten_query": "查询商户",
                    "messages": [HumanMessage(content="商户1002")],
                    "plan": ["检查召回"],
                    "current_step": 0,
                }
            )

        self.assertEqual(result["current_step"], 1)
        self.assertEqual(result["step_results"][0].status, StepStatus.SUCCESS)

    async def test_query_rewrite_routes_to_ask_human(self):
        mock_llm = SimpleNamespace(
            ainvoke=AsyncMock(
                return_value=AIMessage(
                    content='{"need_clarification": true, "clarifying_question": "请补充商户ID", "rewritten_query": "", "keywords": []}'
                )
            )
        )

        with patch("src.nodes.query_rewrite_node.get_gpt_model", return_value=mock_llm), \
             patch("src.nodes.query_rewrite_node.get_prompt", return_value="{query} {history}"):
            command = await query_rewrite_node(
                {
                    "original_query": "查询商户",
                    "messages": [],
                    "plan": [],
                    "current_step": 0,
                }
            )

        self.assertIsInstance(command, Command)
        self.assertEqual(command.goto, "ask_human_node")
        self.assertEqual(command.update["human_question"], "请补充商户ID")
        self.assertEqual(command.update["human_resume_node"], "query_rewrite_node")

    async def test_query_rewrite_consumes_latest_human_message(self):
        mock_llm = SimpleNamespace(
            ainvoke=AsyncMock(
                return_value=AIMessage(
                    content='{"need_clarification": false, "clarifying_question": "", "rewritten_query": "查询商户\\n补充信息：商户1002", "keywords": ["商户1002"]}'
                )
            )
        )

        with patch("src.nodes.query_rewrite_node.get_gpt_model", return_value=mock_llm), \
             patch("src.nodes.query_rewrite_node.get_prompt", return_value="{query} {history}"):
            result = await query_rewrite_node(
                {
                    "original_query": "查询商户",
                    "messages": [HumanMessage(content="商户1002")],
                    "plan": [],
                    "current_step": 0,
                }
            )

        self.assertEqual(result["rewritten_query"], "查询商户\n补充信息：商户1002")
        self.assertEqual(result["keywords"], ["商户1002"])

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


class PlanningNodeTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_plan_prompt_does_not_error(self):
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content='{"steps": ["step1"]}'))

        mock_parser = Mock()
        mock_parser.get_format_instructions = Mock(return_value="format")

        with patch("src.nodes.plan_nodes.sop_loader") as mock_sop_loader, \
             patch("src.nodes.plan_nodes.get_gpt_model", return_value=mock_llm), \
             patch("src.nodes.plan_nodes.JsonOutputParser", return_value=mock_parser), \
             patch("src.nodes.plan_nodes.ChatPromptTemplate") as mock_template, \
             patch("src.prompt.prompt_loader.get_prompt", return_value="system"):
            mock_sop_loader.get_planning_prompt.return_value = ""

            mock_chain = AsyncMock()
            mock_chain.ainvoke = AsyncMock(return_value={"steps": ["step1"]})
            mock_template.from_messages.return_value.__or__ = Mock(return_value=Mock(__or__=Mock(return_value=mock_chain)))

            from src.nodes.plan_nodes import planning_node
            result = await planning_node({
                "rewritten_query": "测试查询",
                "intent": "default",
            })

            self.assertIn("plan", result)


class TokenUsageAccumulationTests(unittest.TestCase):
    def test_extract_token_usage_defaults_to_zero(self):
        usage = _extract_token_usage(SimpleNamespace(response_metadata={}))
        self.assertEqual(usage.total_tokens, 0)


if __name__ == "__main__":
    unittest.main()
