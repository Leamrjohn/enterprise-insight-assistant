"""测试 Tool 协议和两个工具实现"""
from app.tools.protocol import ToolInput
from app.tools.rag import RAGTool


def test_rag_tool_name_and_description():
    tool = RAGTool()
    assert tool.name == "rag_search"
    assert isinstance(tool.description, str)
    assert len(tool.description) > 0


def test_rag_tool_missing_parameters():
    tool = RAGTool()
    result = tool.execute(ToolInput(parameters={"question": "test"}))
    assert result.success is False
    assert result.error is not None


def test_sql_tool_name_and_description():
    from app.tools.sql import SQLTool
    tool = SQLTool()
    assert tool.name == "sql_query"
    assert isinstance(tool.description, str)
    assert len(tool.description) > 0


def test_sql_tool_missing_parameters():
    from app.tools.sql import SQLTool
    tool = SQLTool()
    result = tool.execute(ToolInput(parameters={}))
    assert result.success is False
    assert result.error is not None
