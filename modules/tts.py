from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from modules.utils import require_binary, resolve_project_path


LOG = logging.getLogger(__name__)


class PiperTTS:
    def __init__(self, config: dict[str, Any]) -> None:
        self.enabled = bool(config.get("enabled", True))
        piper_binary = config.get("piper_binary", "piper")
        self.piper_binary = str(resolve_project_path(piper_binary)) if "/" in piper_binary else piper_binary
        self.player = config.get("player", "aplay")
        self.voice_model = resolve_project_path(config["voice_model"])
        self.output_file = Path(config.get("output_file", "/tmp/jarvis-response.wav")).expanduser()
        self.speaker_id = config.get("speaker_id")
        self.length_scale = config.get("length_scale")

    def check(self) -> None:
        if not self.enabled:
            return
        require_binary(self.piper_binary)
        require_binary(self.player)
        if not self.voice_model.exists():
            raise RuntimeError(f"Piper voice model is missing: {self.voice_model}")
        config_file = self.voice_model.with_suffix(self.voice_model.suffix + ".json")
        if not config_file.exists():
            raise RuntimeError(f"Piper voice config is missing: {config_file}")

    def speak(self, text: str) -> None:
        if not self.enabled or not text.strip():
            return

        command = [
            self.piper_binary,
            "--model",
            str(self.voice_model),
            "--output_file",
            str(self.output_file),
        ]
        if self.speaker_id is not None:
            command.extend(["--speaker", str(self.speaker_id)])
        if self.length_scale is not None:
            command.extend(["--length_scale", str(self.length_scale)])

        LOG.debug("Synthesizing speech with Piper")
        subprocess.run(command, input=text, text=True, check=True)
        subprocess.run([self.player, str(self.output_file)], check=False)
