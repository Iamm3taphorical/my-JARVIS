from __future__ import annotations

import logging
import subprocess
import time
import warnings
from typing import Any

import numpy as np


LOG = logging.getLogger(__name__)


class WakeWordDetector:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.enabled = config.get("engine", "openwakeword") == "openwakeword"
        self.recorder = config.get("recorder", "arecord")
        self.audio_device = config.get("audio_device", "default")
        self.model_name = config.get("model_name", "hey_jarvis")
        self.threshold = float(config.get("threshold", 0.55))
        self.sample_rate = int(config.get("sample_rate", 16000))
        self.chunk_samples = int(config.get("chunk_samples", 1280))
        self.cooldown_seconds = float(config.get("cooldown_seconds", 1.5))
        self._model = None

    def check(self) -> None:
        if not self.enabled:
            return
        result = subprocess.run([self.recorder, "-L"], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"Wake word recorder check failed: {result.stderr.strip() or self.recorder}")
        if self.audio_device not in result.stdout:
            raise RuntimeError(f"ALSA input device '{self.audio_device}' was not listed by {self.recorder} -L")
        self._load_model()

    def wait(self) -> None:
        if not self.enabled:
            return

        model = self._load_model()
        LOG.info("Waiting for wake word: %s", self.model_name)
        command = [
            self.recorder,
            "-q",
            "-D",
            self.audio_device,
            "-f",
            "S16_LE",
            "-r",
            str(self.sample_rate),
            "-c",
            "1",
            "-t",
            "raw",
        ]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            assert process.stdout is not None
            while True:
                raw = process.stdout.read(self.chunk_samples * 2)
                if len(raw) < self.chunk_samples * 2:
                    raise RuntimeError("Microphone stream ended while waiting for wake word")
                block = np.frombuffer(raw, dtype=np.int16)
                prediction = model.predict(block)
                score = self._score(prediction)
                if score >= self.threshold:
                    LOG.info("Wake word detected with score %.2f", score)
                    time.sleep(self.cooldown_seconds)
                    return
        finally:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()

    def _load_model(self):
        if self._model is not None:
            return self._model

        import openwakeword
        from openwakeword.model import Model

        warnings.filterwarnings(
            "ignore",
            message=r"Specified provider 'CUDAExecutionProvider'.*",
            category=UserWarning,
        )
        model_info = openwakeword.models.get(self.model_name)
        if not model_info:
            raise RuntimeError(f"Unknown openWakeWord model: {self.model_name}")

        self._model = Model(wakeword_model_paths=[model_info["model_path"]])
        return self._model

    def _score(self, prediction: dict[str, float]) -> float:
        if self.model_name in prediction:
            return float(prediction[self.model_name])
        prefix = f"{self.model_name}_"
        matches = [float(value) for key, value in prediction.items() if key.startswith(prefix)]
        return max(matches, default=0.0)
