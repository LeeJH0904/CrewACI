"""Run with .native-crewai to exercise the official runtime without an API."""

import os
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import PackageNotFoundError, version
import threading
import unittest

from native_reference.calibration_contract import load_calibration_tasks, load_model_config
from native_reference.crew_factory import run_native

try:
    NATIVE_RUNTIME_AVAILABLE = version("crewai") == "1.15.21"
except PackageNotFoundError:
    NATIVE_RUNTIME_AVAILABLE = False


class CompletionHandler(BaseHTTPRequestHandler):
    requests = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length))
        type(self).requests.append(request)
        prompt = json.dumps(request.get("messages", []))
        if "Final Answer Writer" in prompt:
            response = "Final Answer: 320"
        elif "Solution Reviewer" in prompt:
            response = "Final Answer: review marker"
        else:
            response = "Final Answer: draft marker"
        body = json.dumps({
            "id": "g3-smoke",
            "object": "chat.completion",
            "created": 1,
            "model": "scripted-g3",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": response},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


@unittest.skipUnless(
    NATIVE_RUNTIME_AVAILABLE,
    "run this smoke test with the isolated crewai==1.15.21 environment",
)
class NativeReferenceSmokeTests(unittest.TestCase):
    def test_official_sequential_factory_and_capture(self):
        os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
        os.environ.setdefault("CREWAI_STORAGE_DIR", "/tmp/crewai-g3-reference-test")
        CompletionHandler.requests = []
        task = dict(load_calibration_tasks()[0])
        task["ground_truth"] = "320"
        server = ThreadingHTTPServer(("127.0.0.1", 0), CompletionHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        model = load_model_config()
        model["base_url"] = f"http://127.0.0.1:{server.server_port}/v1"
        os.environ["OPENAI_API_KEY"] = "g3-local-test"
        try:
            record = run_native(
                experiment_id="g3-native-smoke", task=task,
                model_config=model,
            )
        finally:
            server.shutdown()
            thread.join(timeout=2)
        self.assertEqual(record["status"], "success", record)
        self.assertEqual(record["runtime_version"], "1.15.21")
        self.assertEqual(record["response_agent"], "finalizer")
        self.assertEqual(record["raw_response"], "320")
        self.assertEqual([item["agent"] for item in record["task_outputs"]],
                         ["solver", "reviewer", "finalizer"])
        self.assertEqual([call["agent"] for call in record["llm_calls"]],
                         ["solver", "reviewer", "finalizer"])
        self.assertEqual(len(CompletionHandler.requests), 3)
        self.assertEqual(
            {request["model"] for request in CompletionHandler.requests},
            {model["model_name"]},
        )
        self.assertIn("draft marker", str(record["llm_calls"][1]["messages"]))
        self.assertIn("review marker", str(record["llm_calls"][2]["messages"]))


if __name__ == "__main__":
    unittest.main()
