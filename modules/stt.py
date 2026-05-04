from __future__ import annotations

import logging
import subprocess
import tempfile
import wave
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from faster_whisper import WhisperModel


LOG = logging.getLogger(__name__)


class SpeechToText:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.recorder = config.get("recorder", "arecord")
        self.audio_device = config.get("audio_device", "default")
        self.model_size = config.get("model_size", "small")
        self.sample_rate = int(config.get("sample_rate", 16000))
        self.max_record_seconds = float(config.get("max_record_seconds", 8))
        self.silence_seconds = float(config.get("silence_seconds", 1.0))
        self.start_threshold = float(config.get("start_threshold", 0.012))
        self.silence_threshold = float(config.get("silence_threshold", 0.008))
        self.block_seconds = float(config.get("block_seconds", 0.1))
        self.pre_roll_seconds = float(config.get("pre_roll_seconds", 0.35))
        self.beam_size = int(config.get("beam_size", 1))
        self.best_of = int(config.get("best_of", self.beam_size))
        self.patience = float(config.get("patience", 1.0))
        self.temperature = config.get("temperature", 0.0)
        self.no_speech_threshold = config.get("no_speech_threshold", 0.6)
        self.language = config.get("language", "en")
        self.vad_filter = bool(config.get("vad_filter", True))
        self.vad_parameters = config.get("vad_parameters")
        self.initial_prompt = str(config.get("initial_prompt", "")).strip()
        self.hotwords = str(config.get("hotwords", "")).strip()
        self.retry_without_vad_on_empty = bool(config.get("retry_without_vad_on_empty", True))
        self.preload_model = bool(config.get("preload_model", True))
        self._model: WhisperModel | None = None

    def check(self) -> None:
        result = subprocess.run([self.recorder, "-L"], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"Microphone recorder check failed: {result.stderr.strip() or self.recorder}")
        if self.audio_device not in result.stdout:
            raise RuntimeError(f"ALSA input device '{self.audio_device}' was not listed by {self.recorder} -L")
        if self.preload_model:
            self.warm_up()

    def warm_up(self) -> None:
        try:
            _ = self.model
        except Exception as exc:
            raise RuntimeError(
                "Speech recognition model could not be loaded. On the first run, keep internet connected "
                "until the faster-whisper model download finishes. If it is too slow, set stt.model_size "
                "in config.json to 'base' or 'tiny.en'."
            ) from exc
        LOG.info("Speech recognition model is ready")

    @property
    def model(self) -> WhisperModel:
        if self._model is None:
            LOG.info("Loading faster-whisper model: %s", self.model_size)
            self._model = WhisperModel(
                self.model_size,
                device=self.config.get("device", "cpu"),
                compute_type=self.config.get("compute_type", "int8"),
            )
        return self._model

    def listen_once(self) -> str:
        audio = self._record_until_silence()
        if audio.size == 0:
            return ""
        wav_path = self._write_temp_wav(audio)
        try:
            text = self._transcribe_wav(wav_path, vad_filter=self.vad_filter)
            if not text and self.vad_filter and self.retry_without_vad_on_empty:
                LOG.info("No transcription with VAD enabled; retrying without VAD")
                text = self._transcribe_wav(wav_path, vad_filter=False)
            return text
        finally:
            wav_path.unlink(missing_ok=True)

    def _transcribe_wav(self, wav_path: Path, vad_filter: bool) -> str:
        kwargs: dict[str, Any] = {
            "beam_size": self.beam_size,
            "best_of": self.best_of,
            "patience": self.patience,
            "temperature": self.temperature,
            "language": self.language,
            "vad_filter": vad_filter,
            "condition_on_previous_text": False,
            "no_speech_threshold": self.no_speech_threshold,
        }
        if self.vad_parameters:
            kwargs["vad_parameters"] = self.vad_parameters
        if self.initial_prompt:
            kwargs["initial_prompt"] = self.initial_prompt
        if self.hotwords:
            kwargs["hotwords"] = self.hotwords

        segments, _info = self.model.transcribe(str(wav_path), **kwargs)
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
        LOG.debug("Transcription result: %r", text)
        return text

    def _record_until_silence(self) -> np.ndarray:
        block_size = int(self.sample_rate * self.block_seconds)
        max_blocks = max(1, int(self.max_record_seconds / self.block_seconds))
        silent_limit = max(1, int(self.silence_seconds / self.block_seconds))
        pre_roll_blocks = max(0, int(self.pre_roll_seconds / self.block_seconds))

        frames: list[np.ndarray] = []
        pre_roll: deque[np.ndarray] = deque(maxlen=pre_roll_blocks)
        started = False
        silent_blocks = 0

        LOG.info("Listening for speech")
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
            for _ in range(max_blocks):
                raw = process.stdout.read(block_size * 2)
                if len(raw) < block_size * 2:
                    break
                int_samples = np.frombuffer(raw, dtype=np.int16)
                samples = int_samples.astype(np.float32) / 32768.0
                level = float(np.sqrt(np.mean(np.square(samples))))

                if not started:
                    if pre_roll_blocks:
                        pre_roll.append(samples.copy())
                    if level >= self.start_threshold:
                        started = True
                        if pre_roll:
                            frames.extend(pre_roll)
                            pre_roll.clear()
                        else:
                            frames.append(samples.copy())
                    continue

                frames.append(samples.copy())
                if level < self.silence_threshold:
                    silent_blocks += 1
                    if silent_blocks >= silent_limit:
                        break
                else:
                    silent_blocks = 0
        finally:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()

        if not frames:
            return np.array([], dtype=np.float32)
        return np.concatenate(frames)

    def _write_temp_wav(self, audio: np.ndarray) -> Path:
        clipped = np.clip(audio, -1.0, 1.0)
        pcm = (clipped * 32767).astype(np.int16)
        handle = tempfile.NamedTemporaryFile(prefix="jarvis-stt-", suffix=".wav", delete=False)
        handle.close()
        path = Path(handle.name)
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(pcm.tobytes())
        return path
