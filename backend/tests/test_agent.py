"""
Tests for agent routing logic — verifying the no-auth fast path and the
tool-call detection path, without requiring real MCP or Claude connections.
"""

import pytest
from app.agent.agent import _is_write_tool


class TestWriteToolClassification:
    """Verify that write-action detection works correctly."""

    write_tools = [
        "create_bucket",
        "delete_object",
        "update_lambda_function",
        "put_object",
        "start_instances",
        "stop_instances",
        "terminate_instances",
        "reboot_instance",
        "invoke_lambda",
        "publish_message",
        "send_message",
        "tag_resource",
        "untag_resource",
        "modify_db_instance",
        "attach_policy",
        "detach_role",
        "enable_versioning",
        "disable_logging",
    ]

    read_tools = [
        "list_buckets",
        "get_object",
        "describe_instances",
        "get_metric_statistics",
        "get_log_events",
        "describe_stack",
        "get_role",
        "list_policies",
        "describe_db_instances",
        "get_function",
        "get_rest_api",
        "search_documentation",
    ]

    @pytest.mark.parametrize("tool_name", write_tools)
    def test_write_tools_detected(self, tool_name):
        assert _is_write_tool(tool_name), f"{tool_name} should be classified as write"

    @pytest.mark.parametrize("tool_name", read_tools)
    def test_read_tools_not_detected(self, tool_name):
        assert not _is_write_tool(tool_name), f"{tool_name} should NOT be classified as write"

    def test_case_insensitive(self):
        assert _is_write_tool("CREATE_BUCKET")
        assert _is_write_tool("Delete_Object")

    def test_empty_string_is_read(self):
        assert not _is_write_tool("")
