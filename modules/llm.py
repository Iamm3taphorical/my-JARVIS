from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any

from modules.utils import truncate_text


LOG = logging.getLogger(__name__)
THINK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


class OllamaClient:
    def __init__(self, config: dict[str, Any]) -> None:
        self.model = config["model"]
        self.host = config["host"].rstrip("/")
        self.timeout = int(config.get("timeout_seconds", 90))
        self.system_prompt = config["system_prompt"]
        self.max_response_chars = int(config.get("max_response_chars", 900))
        self.options = {
            "temperature": config.get("temperature", 0.4),
            "top_p": config.get("top_p", 0.9),
            "num_ctx": config.get("num_ctx", 2048),
        }

    def check(self) -> None:
        try:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError("Ollama is not reachable. Start it with: ollama serve") from exc

        installed = {item.get("name", "").split(":")[0] for item in payload.get("models", [])}
        installed_full = {item.get("name", "") for item in payload.get("models", [])}
        if self.model not in installed_full and self.model.split(":")[0] not in installed:
            raise RuntimeError(f"Ollama model '{self.model}' is not installed. Run: ollama pull {self.model}")

    def ask(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "system": self.system_prompt,
            "prompt": prompt.strip(),
            "options": self.options,
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.host}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            LOG.exception("Ollama request failed")
            raise RuntimeError("The local LLM request failed") from exc

        text = body.get("response", "").strip()
        text = THINK_RE.sub("", text)
        text = re.sub(r"(?im)^reasoning:.*$", "", text)
        text = re.sub(r"(?im)^thinking\.\.\..*$", "", text)
        return truncate_text(text, self.max_response_chars) or "I did not get a usable response."
