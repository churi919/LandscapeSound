"""Exercise the bridge boundary with fixtures; never call a real GPT model."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gpt_cli_bridge as bridge


def reply():
    return {"schema_version": 1, "scenes": [{
        "id": "new_panorama", "visible_facts_zh": ["路边可见树木和道路。"],
        "uncertainties_zh": ["静态图片不能确认是否存在风或声音。"],
        "narration_zh": "前方是一条道路，旁边有树木。照片不能确认实际通行情况。",
        "stems": [{"id": "leaves", "category": "trees", "label_zh": "轻微叶声",
            "enabled": True, "visual_evidence_zh": ["道路旁边可见树叶。"],
            "simulation_assumptions_zh": ["微风吹动树叶是试听设定。"],
            "prompt_en": "A soft irregular rustle of broad tree leaves. A little breeze gathers several quiet leaf movements, then settles into a calm pause. Keep the texture close, dry and restrained, with slow natural changes and gentle spaces between the small clusters.",
            "relative_level": .4, "views": [{"view_id": "front", "azimuth": 12,
                "spread_degrees": 20, "virtual_radius": 4, "basis_zh": "树木在前方偏右。"}]}]}]}


class FakeProcess:
    def __init__(self, events, stderr="", code=0):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("".join(json.dumps(value) + "\n" for value in events))
        self.stderr = io.StringIO(stderr)
        self.code = code
        self.terminated = False

    def poll(self):
        return None if not self.terminated else self.code

    def wait(self, timeout=None):
        return self.code

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.terminated = True


class GPTCLIBridgeTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.test_dir = Path(folder.name)

    def test_command_has_read_only_no_tools_and_no_model_prompt_on_argv(self):
        command = bridge._command("codex.exe", "input.jpg", "schema.json", "response.json")
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ephemeral", command)
        self.assertIn("--skip-git-repo-check", command)
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertEqual(command[command.index("--ask-for-approval") + 1], "never")
        self.assertIn('web_search="disabled"', command)
        self.assertIn("mcp_servers={}", command)
        self.assertIn("project_doc_max_bytes=0", command)
        for feature in ("shell_tool", "unified_exec", "apps", "plugins", "multi_agent", "browser_use", "computer_use", "view_image", "hooks", "memories"):
            self.assertTrue(any(command[index:index+2] == ["--disable", feature]
                                for index in range(len(command)-1)))
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertEqual(command[-1], "-")

    def test_minimal_environment_omits_credentials_and_ambient_injection(self):
        original = {"PATH": "bin", "USERPROFILE": "profile", "CODEX_HOME": "normal-home",
                    "OPENAI_API_KEY": "secret", "CODEX_API_KEY": "secret2",
                    "CODEX_APP_SERVER_URL": "parent-session", "PRIVATE_DATA": "private"}
        self.assertEqual(bridge._minimal_environment(original),
                         {"PATH": "bin", "USERPROFILE": "profile", "CODEX_HOME": "normal-home"})

    def test_schema_is_strict_at_every_object_level(self):
        schema = bridge.response_schema()
        def visit(value):
            if isinstance(value, dict):
                if value.get("type") == "object":
                    self.assertIs(value["additionalProperties"], False)
                    self.assertEqual(set(value["required"]), set(value["properties"]))
                for item in value.values():
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)
        visit(schema)
        scenes = schema["properties"]["scenes"]
        self.assertEqual(scenes["maxItems"], 1)
        self.assertEqual(scenes["items"]["properties"]["stems"]["maxItems"], 3)

    def test_tool_events_fail_closed_and_process_is_terminated(self):
        for tool in ["command_execution", "mcp_tool_call", "web_search", "file_change", "function_call", "unknown_tool"]:
            process = FakeProcess([{"type": "thread.started", "thread_id": "test-123"},
                                   {"type": "item.started", "item": {"type": tool}}])
            with self.subTest(tool=tool), patch.object(bridge.subprocess, "Popen", return_value=process):
                with self.assertRaisesRegex(bridge.GPTCLIError, "额外工具"):
                    bridge._run_isolated(["codex"], "look only", self.test_dir, 2)
                self.assertTrue(process.terminated)
                metadata = json.loads((self.test_dir / "event_status.json").read_text(encoding="utf-8"))
                self.assertEqual(metadata["events"][-1]["item_type"], tool)

    def test_monitor_discards_reasoning_and_keeps_only_status(self):
        process = FakeProcess([{"type": "thread.started", "thread_id": "test-123"},
                               {"type": "turn.started"},
                               {"type": "item.completed", "item": {"type": "reasoning", "text": "PRIVATE REASONING"}},
                               {"type": "item.completed", "item": {"type": "agent_message", "text": "FINAL"}},
                               {"type": "turn.completed", "usage": {"input_tokens": 10}}])
        with patch.object(bridge.subprocess, "Popen", return_value=process) as start:
            sid, statuses, _ = bridge._run_isolated(["codex"], "look only", self.test_dir, 2)
        self.assertEqual(sid, "test-123")
        self.assertNotIn("PRIVATE REASONING", json.dumps(statuses))
        self.assertNotIn("FINAL", json.dumps(statuses))
        self.assertEqual([x["type"] for x in statuses], ["thread.started", "turn.started", "turn.completed"])
        self.assertEqual(start.call_args.kwargs["cwd"], str(self.test_dir))
        metadata = (self.test_dir / "event_status.json").read_text(encoding="utf-8")
        self.assertNotIn("PRIVATE REASONING", metadata)

    def test_passive_error_item_is_diagnostic_not_a_tool(self):
        process = FakeProcess([{"type": "thread.started", "thread_id": "test-123"},
                               {"type": "turn.started"},
                               {"type": "item.completed", "item": {"type": "error", "message": "A client warning"}},
                               {"type": "turn.completed"}])
        with patch.object(bridge.subprocess, "Popen", return_value=process):
            bridge._run_isolated(["codex"], "look only", self.test_dir, 2)
        metadata = json.loads((self.test_dir / "event_status.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["diagnostics"], "A client warning")
        self.assertEqual(metadata["observed_tool_calls"], 0)

    def test_actual_client_failure_preserves_diagnostic_and_type(self):
        process = FakeProcess([{"type": "thread.started", "thread_id": "test-123"},
                               {"type": "item.completed", "item": {"type": "error", "message": "Invalid schema fixture"}},
                               {"type": "turn.failed", "error": {"message": "request rejected"}}], code=1)
        with patch.object(bridge.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(bridge.GPTCLIError, "Invalid schema fixture") as caught:
                bridge._run_isolated(["codex"], "look only", self.test_dir, 2)
        self.assertNotIn("额外工具", str(caught.exception))
        self.assertEqual(caught.exception.event_trace[-2]["item_type"], "error")

    def test_bridge_binds_exact_image_and_response_and_writes_isolated_audit(self):
        status = {"available": True, "logged_in": True, "executable": "codex.exe", "version": "codex-cli fixture"}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = root / "source.jpg"
            image.write_bytes(b"fixture contact sheet")
            def run(command, prompt, cwd, timeout):
                Path(command[command.index("--output-last-message") + 1]).write_text(
                    json.dumps(reply(), ensure_ascii=False), encoding="utf-8")
                self.assertEqual(Path(cwd).parent, root / "output")
                self.assertIn("不可信数据", prompt)
                self.assertNotIn("source.jpg", command)
                return "fixture-123", [{"type": "turn.completed"}], .1
            with patch.object(bridge, "gpt_cli_status", return_value=status), patch.object(bridge, "_run_isolated", side_effect=run):
                result = bridge.analyze_panorama_with_gpt(image, "id=new_panorama", root / "output")
            self.assertEqual(json.loads(result["response_text"]), reply())
            source = result["provenance"]
            self.assertEqual(source["provider"], "codex_cli")
            self.assertNotIn("conversation_url", source)
            self.assertEqual(source["contact_sheet_sha256"], hashlib.sha256(image.read_bytes()).hexdigest())
            self.assertEqual(source["response_sha256"], bridge._sha(source["response_file"]))
            audit = json.loads(Path(source["request_audit_file"]).read_text(encoding="utf-8"))
            self.assertEqual(audit["observed_tool_calls"], 0)
            self.assertEqual(audit["status"], "completed")

    def test_no_login_fails_without_inference_or_generic_substitution(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / "source.jpg"
            image.write_bytes(b"image")
            with patch.object(bridge, "gpt_cli_status", return_value={"available": True, "logged_in": False, "message": "请登录"}), patch.object(bridge, "_run_isolated") as run:
                with self.assertRaisesRegex(bridge.GPTCLIError, "请登录"):
                    bridge.analyze_panorama_with_gpt(image, "look", Path(folder) / "output")
                run.assert_not_called()

    def test_errors_are_bounded_and_auth_tokens_are_redacted(self):
        message = "Bearer abcd1234secret access_token=private-value sk-" + "x" * 100 + "z" * 5000
        result = bridge._safe_error(message)
        self.assertLessEqual(len(result), 4000)
        for value in ["abcd1234secret", "private-value", "sk-" + "x" * 20]:
            self.assertNotIn(value, result)


if __name__ == "__main__":
    unittest.main()
