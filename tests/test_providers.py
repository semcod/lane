"""Tests for nxdo.providers."""

import json
import unittest
from unittest.mock import MagicMock, patch

from nxdo.providers.openai_compat import OpenAICompatProvider, _parse_response


_VALID_RAW = json.dumps({
    "project_name": "demo",
    "summary": "A good project.",
    "tasks": [
        {
            "number": 1,
            "title": "Add tests",
            "description": "Improve coverage.",
            "priority": "high",
            "task_type": "test",
            "estimated_hours": 3,
            "acceptance_criteria": ["Coverage > 80%"],
            "dependencies": [],
        }
    ],
})


class ParseResponseTests(unittest.TestCase):
    def test_valid_response_parsed(self) -> None:
        plan = _parse_response(_VALID_RAW, "demo", "model-x")
        self.assertEqual(plan.project_name, "demo")
        self.assertEqual(len(plan.tasks), 1)
        self.assertEqual(plan.tasks[0].title, "Add tests")

    def test_invalid_json_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            _parse_response("not json", "p", "m")
        self.assertIn("invalid JSON", str(ctx.exception))

    def test_non_object_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            _parse_response(json.dumps([1, 2, 3]), "p", "m")
        self.assertIn("JSON object", str(ctx.exception))

    def test_bad_task_priority_raises(self) -> None:
        raw = json.dumps({
            "project_name": "p",
            "summary": "s",
            "tasks": [{"number": 1, "title": "T", "description": "D", "priority": "NOPE"}],
        })
        with self.assertRaises(ValueError) as ctx:
            _parse_response(raw, "p", "m")
        self.assertIn("Invalid task data", str(ctx.exception))

    def test_fenced_code_block_stripped(self) -> None:
        raw = f"```json\n{_VALID_RAW}\n```"
        plan = _parse_response(raw, "demo", "m")
        self.assertEqual(plan.project_name, "demo")


class OpenAICompatProviderTests(unittest.TestCase):
    def test_no_api_key_raises_value_error(self) -> None:
        from nxdo.config import NxdoSettings

        # Clear the environment BEFORE building settings/provider so an ambient
        # OPENROUTER_API_KEY/OPENAI_API_KEY cannot leak in at construction time.
        # Combined with _env_file=None this deterministically exercises the
        # missing-key guard without ever touching the network.
        with patch.dict("os.environ", {}, clear=True):
            settings = NxdoSettings(_env_file=None)
            provider = OpenAICompatProvider(api_key=None, settings=settings)
            with self.assertRaises(ValueError) as ctx:
                provider._call_api("prompt")
        self.assertIn("API key", str(ctx.exception))

    def test_generate_plan_uses_parse_response(self) -> None:
        provider = OpenAICompatProvider(api_key="sk-test")
        with patch.object(provider, "_call_api", return_value=_VALID_RAW):
            plan = provider.generate_plan("prompt", "demo")
        self.assertEqual(plan.project_name, "demo")
        self.assertEqual(len(plan.tasks), 1)

    @patch("nxdo.providers.openai_compat.httpx.Client")
    def test_call_api_constructs_correct_payload(self, mock_client_class: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": _VALID_RAW}}]
        }
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client

        provider = OpenAICompatProvider(api_key="sk-test", model="test-model")
        provider._call_api("user prompt")

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        self.assertIn("json", call_args.kwargs)
        payload = call_args.kwargs["json"]
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(len(payload["messages"]), 2)
        self.assertEqual(payload["messages"][1]["content"], "user prompt")

    @patch("nxdo.providers.openai_compat.httpx.Client")
    def test_call_api_sets_correct_headers(self, mock_client_class: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": _VALID_RAW}}]
        }
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client

        provider = OpenAICompatProvider(api_key="sk-test", app_name="test-app")
        provider._call_api("prompt")

        call_args = mock_client.post.call_args
        headers = call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer sk-test")
        self.assertEqual(headers["X-OpenRouter-Title"], "test-app")

    @patch("nxdo.providers.openai_compat.httpx.Client")
    def test_call_api_handles_unexpected_response(self, mock_client_class: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"invalid": "structure"}
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client

        provider = OpenAICompatProvider(api_key="sk-test")
        with self.assertRaises(ValueError) as ctx:
            provider._call_api("prompt")
        self.assertIn("Unexpected LLM response", str(ctx.exception))

    @patch("nxdo.providers.openai_compat.httpx.Client")
    def test_call_api_raises_on_http_error(self, mock_client_class: MagicMock) -> None:
        """Test that _call_api raises ValueError on non-2xx response (lines 106-107)."""
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 401
        mock_response.text = '{"error": "Unauthorized"}'
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client

        provider = OpenAICompatProvider(api_key="sk-test")
        with self.assertRaises(ValueError) as ctx:
            provider._call_api("prompt")
        self.assertIn("401", str(ctx.exception))

    def test_create_task_from_dict_handles_string_dep(self) -> None:
        """Test _create_task_from_dict skips non-numeric string dependencies (lines 146-149)."""
        from nxdo.providers.openai_compat import _create_task_from_dict
        item = {
            "number": 1,
            "title": "T",
            "description": "",
            "priority": "medium",
            "task_type": "feature",
            "dependencies": ["1", "task-title-dep", 2],
        }
        task = _create_task_from_dict(item, 0)
        self.assertEqual(task.dependencies, [1, 2])


if __name__ == "__main__":
    unittest.main()
