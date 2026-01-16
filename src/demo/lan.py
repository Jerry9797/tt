import operator
from typing import Annotated, List, TypedDict
from langgraph.graph import StateGraph, END, START
# ✅ 关键导入：Send 用于动态分发任务
from langgraph.types import Send


# ==========================================
# 1. 定义状态 (State)
# ==========================================

# 主状态：贯穿整个流程的上下文
class OverallState(TypedDict):
    topic: str  # 用户输入的主题
    sub_topics: List[str]  # 拆解后的子任务列表
    # ✅ 关键点：使用 operator.add。
    # 因为多个 Worker 会同时往这里写数据，必须告诉图“请追加，不要覆盖”
    final_paragraphs: Annotated[List[str], operator.add]


# 子状态：专门传给 Worker 的小状态
# Worker 不需要知道整个大纲，只需要知道自己负责哪个子主题
class WorkerState(TypedDict):
    section_topic: str


# ==========================================
# 2. 定义节点 (Nodes)
# ==========================================

def planner_node(state: OverallState):
    """规划节点：接收主题，生成子大纲"""
    print(f"--- [1. Planner] 正在拆解主题: {state['topic']} ---")

    # 这里模拟 LLM 生成了 3 个子主题
    # 实际场景中这里调用 LLM
    generated_topics = [
        f"{state['topic']} 的历史",
        f"{state['topic']} 的核心语法",
        f"{state['topic']} 的未来趋势"
    ]
    return {"sub_topics": generated_topics}


def worker_node(state: WorkerState):
    """工人节点：并行执行的单元"""
    # 注意：这里的 state 是 WorkerState，不是 OverallState
    topic = state["section_topic"]
    print(f"   >>> [2. Worker] 正在并行撰写: {topic}")

    # 模拟耗时写作
    import time
    time.sleep(1)  # 休息1秒，证明是并行的（如果串行需要3秒）

    result = f"【段落内容：关于 {topic} 的详细介绍...】"

    # 返回的内容会被加到 OverallState 的 final_paragraphs 列表里
    return {"final_paragraphs": [result]}


def reducer_node(state: OverallState):
    """汇总节点：合并所有结果"""
    print(f"--- [3. Reducer] 收到所有稿件，正在合并 ---")

    # 将列表拼接成字符串
    full_article = "\n".join(state["final_paragraphs"])
    return {"final_article": full_article}  # 这里其实可以直接打印，为了演示返回空


# ==========================================
# 3. 定义动态路由逻辑 (Map Step)
# ==========================================

def map_sub_topics(state: OverallState):
    """这是核心逻辑：决定要启动多少个 Worker"""
    topics = state["sub_topics"]

    # 这里的 List[Send] 就是告诉 LangGraph：
    # "请并行启动 3 个 worker_node，并分别喂给它们不同的 section_topic"
    return [
        Send("worker_node", {"section_topic": t}) for t in topics
    ]


# ==========================================
# 4. 构建图 (Graph)
# ==========================================

workflow = StateGraph(OverallState)

# 添加节点
workflow.add_node("planner_node", planner_node)
workflow.add_node("worker_node", worker_node)  # 这个节点会被复用多次
workflow.add_node("reducer_node", reducer_node)

# 设置入口
workflow.add_edge(START, "planner_node")

# ✅ 关键步骤：添加条件边 (Map)
# 从 planner 出来后，根据 map_sub_topics 的返回结果(List[Send])，动态分发给 worker
workflow.add_conditional_edges("planner_node", map_sub_topics)

# ✅ 关键步骤：汇聚 (Fan-in)
# 所有 worker 执行完后，统一去 reducer
workflow.add_edge("worker_node", "reducer_node")

workflow.add_edge("reducer_node", END)

# 编译
app = workflow.compile()

# ==========================================
# 5. 运行测试
# ==========================================

if __name__ == "__main__":
    inputs = {"topic": "Python编程"}

    print("🚀 开始执行工作流...")
    # invoke 会阻塞直到所有并行任务完成
    final_state = app.invoke(inputs)

    print("\n✅ 最终结果:\n")
    for idx, p in enumerate(final_state["final_paragraphs"]):
        print(f"段落 {idx + 1}: {p}")