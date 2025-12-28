import json
import logging
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from langgraph.store.base import BaseStore, GetOp, IndexConfig, Item, Op, PutOp, SearchOp
from pymysql.connections import Connection

from src.config.mysql import get_connection

logger = logging.getLogger(__name__)

class MySQLStore(BaseStore):
    """
    A LangGraph Store implementation using MySQL.
    """

    def __init__(self, conn: Optional[Connection] = None):
        """
        Initialize the MySQLStore.
        
        Args:
            conn: A pymysql connection object. If None, a new connection will be created using config.
        """
        self.conn = conn or get_connection()
        self.setup()

    def setup(self):
        """
        Create the necessary table if it doesn't exist.
        """
        with self.conn.cursor() as cursor:
            # Create table for store items
            create_table_query = """
            CREATE TABLE IF NOT EXISTS store_items (
                namespace VARCHAR(255) NOT NULL,
                `key` VARCHAR(255) NOT NULL,
                value JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (namespace, `key`),
                INDEX idx_namespace (namespace)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            """
            cursor.execute(create_table_query) 

    def _get_namespace_str(self, namespace: tuple) -> str:
        return "/".join(namespace)

    def batch(self, ops: Iterable[Op]) -> List[Any]:
        results = []
        with self.conn.cursor() as cursor:
            for op in ops:
                if isinstance(op, GetOp):
                    namespace_str = self._get_namespace_str(op.namespace)
                    cursor.execute(
                        "SELECT * FROM store_items WHERE namespace = %s AND `key` = %s",
                        (namespace_str, op.key)
                    )
                    row = cursor.fetchone()
                    if row:
                        results.append(Item(
                            value=json.loads(row['value']) if isinstance(row['value'], str) else row['value'],
                            key=row['key'],
                            namespace=op.namespace,
                            created_at=row['created_at'],
                            updated_at=row['updated_at']
                        ))
                    else:
                        results.append(None)
                        
                elif isinstance(op, PutOp):
                    namespace_str = self._get_namespace_str(op.namespace)
                    value_json = json.dumps(op.value)
                    
                    query = """
                    INSERT INTO store_items (namespace, `key`, value)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE value = %s
                    """
                    cursor.execute(query, (namespace_str, op.key, value_json, value_json))
                    results.append(None)
                    
                elif isinstance(op, SearchOp):
                    namespace_str = self._get_namespace_str(op.namespace_prefix)
                    if not op.namespace_prefix:
                        query = "SELECT * FROM store_items LIMIT %s"
                        params = (op.limit or 10,)
                    else:
                        query = "SELECT * FROM store_items WHERE namespace LIKE %s LIMIT %s"
                        params = (f"{namespace_str}%", op.limit or 10)
                        
                    cursor.execute(query, params)
                    rows = cursor.fetchall()
                    items = []
                    for row in rows:
                        ns_tuple = tuple(row['namespace'].split('/'))
                        items.append(Item(
                            value=json.loads(row['value']) if isinstance(row['value'], str) else row['value'],
                            key=row['key'],
                            namespace=ns_tuple,
                            created_at=row['created_at'],
                            updated_at=row['updated_at']
                        ))
                    results.append(items)
                
        return results

    async def abatch(self, ops: Iterable[Op]) -> List[Any]:
        """
        Async batch operation.
        Since we are using synchronous pymysql, we just call self.batch() directly.
        For a true async integration, we would need to use aiomysql.
        """
        return self.batch(ops)
