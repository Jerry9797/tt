"""
Time Travel utilities for LangGraph state management.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
import json


async def get_all_thread_ids(graph) -> List[str]:
    """
    获取数据库中所有的 thread_id
    
    Args:
        graph: 编译后的 LangGraph
        
    Returns:
        所有 thread_id 列表
    """
    try:
        checkpointer = graph.checkpointer
        
        # 检查是否是 AsyncMySQLSaver (AIOMySQLSaver)
        if not hasattr(checkpointer, 'conn'):
            return []
        
        # 直接查询数据库获取所有不同的 thread_id
        # 使用 aiomysql 游标
        async with checkpointer.conn.cursor() as cursor:
            # 检查表是否存在
            # 注意: LangGraph MySQL Saver 的表名通常是 checkpoints
            try:
                await cursor.execute("""
                    SELECT DISTINCT thread_id 
                    FROM checkpoints
                """)
                rows = await cursor.fetchall()
                # 默认 cursor 返回的是元组，不是字典
                return [row[0] for row in rows]
            except Exception as e:
                # 表可能不存在
                print(f"查询 thread_id 失败 (可能是表不存在): {e}")
                return []
    except Exception as e:
        print(f"获取 thread_id 列表失败: {e}")
        return []


async def get_state_history(graph, thread_id: str) -> List[Dict[str, Any]]:
    """
    获取指定 thread 的所有历史状态
    
    Args:
        graph: 编译后的 LangGraph
        thread_id: Thread ID
        
    Returns:
        历史状态列表，每个包含 checkpoint 信息
    """
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        history = []
        # ⭐ aget_state_history 返回异步迭代器，需要使用 async for
        state_iter = graph.aget_state_history(config)
        async for state in state_iter:
            history.append({
                "checkpoint_id": state.config["configurable"].get("checkpoint_id"),
                "values": state.values,
                "next_node": state.next,
                "metadata": state.metadata,
                "config": state.config,
                "created_at": state.created_at,
                "parent_config": state.parent_config
            })
        return history
    except Exception as e:
        print(f"获取历史状态失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def format_checkpoint_info(checkpoint: Dict[str, Any], index: int) -> str:
    """
    格式化 checkpoint 信息用于显示
    
    Args:
        checkpoint: Checkpoint 字典
        index: 索引编号
        
    Returns:
        格式化的字符串
    """
    metadata = checkpoint.get("metadata", {})
    step = metadata.get("step", "?")
    
    # 获取执行的节点名称
    source = metadata.get("source", "unknown")
    writes = metadata.get("writes", {})
    
    # 尝试从 writes 中获取节点名
    node_name = "unknown"
    if writes:
        node_name = list(writes.keys())[0] if writes else source
    
    # 格式化时间
    created_at = checkpoint.get("created_at")
    if created_at:
        timestamp = created_at.strftime("%H:%M:%S") if hasattr(created_at, "strftime") else str(created_at)
    else:
        timestamp = "N/A"
    
    # 下一个节点
    next_node = checkpoint.get("next_node", [])
    next_str = ", ".join(next_node) if next_node else "END"
    
    return f"#{index} | Step {step} | {node_name} → {next_str} | {timestamp}"


def get_checkpoint_details(checkpoint: Dict[str, Any]) -> str:
    """
    获取 checkpoint 的详细信息（JSON 格式）
    
    Args:
        checkpoint: Checkpoint 字典
        
    Returns:
        JSON 格式的详细信息
    """
    details = {
        "state_values": checkpoint.get("values", {}),
        "next_node": checkpoint.get("next_node", []),
        "metadata": checkpoint.get("metadata", {}),
    }
    return json.dumps(details, indent=2, ensure_ascii=False)


async def rollback_to_checkpoint(graph, thread_id: str, checkpoint_id: str, inputs: Optional[Dict] = None):
    """
    回滚到指定的 checkpoint 并继续执行
    
    Args:
        graph: 编译后的 LangGraph
        thread_id: Thread ID
        checkpoint_id: Checkpoint ID
        inputs: 可选的输入数据
        
    Returns:
        执行结果
    """
    config = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id
        }
    }
    
    # 从指定 checkpoint 继续执行
    # ⭐ 使用 ainvoke
    result = await graph.ainvoke(inputs, config=config)
    return result


async def update_and_continue(
    graph, 
    thread_id: str, 
    checkpoint_id: str, 
    updates: Dict[str, Any], 
    as_node: Optional[str] = None
):
    """
    修改指定 checkpoint 的状态并继续执行
    
    Args:
        graph: 编译后的 LangGraph
        thread_id: Thread ID
        checkpoint_id: Checkpoint ID
        updates: 要更新的状态字段
        as_node: 指定从哪个节点继续（可选）
        
    Returns:
        执行结果
    """
    config = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id
        }
    }
    
    # 更新状态
    # ⭐ 使用 aupdate_state
    await graph.aupdate_state(config=config, values=updates, as_node=as_node)
    
    # 继续执行
    # ⭐ 使用 ainvoke
    result = await graph.ainvoke(None, config={"configurable": {"thread_id": thread_id}})
    return result
