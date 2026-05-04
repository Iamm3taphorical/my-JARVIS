from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from collections.abc import Callable
from typing import Any

from modules.commands import CommandRouter
from modules.llm import OllamaClient
from modules.stt import SpeechToText
from modules.tts import PiperTTS
from modules.utils import configure_logging, load_config
from modules.wakeword import WakeWordDetector


LOG = logging.getLogger("jarvis")
AssistantEventSink = Callable[[dict[str, Any]], None]


class JarvisAssistant:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.llm = OllamaClient(config["llm"])
        self.tts = PiperTTS(config["tts"])
        self.stt = SpeechToText(config["stt"])
        self.wakeword = WakeWordDetector(config["wakeword"])
        self.commands = CommandRouter(config["commands"])
        self.name = config["assistant"].get("name", "JARVIS")
        self.wake_word_enabled = bool(config["assistant"].get("wake_word_enabled", True))
        self.keyboard_fallback = bool(config["assistant"].get("keyboard_fallback", True))
        self.rearm_delay_seconds = float(config["assistant"].get("rearm_delay_seconds", 1.2))
        self.follow_up_prompts = config["assistant"].get(
            "follow_up_prompts",
            [
                "I have executed the previous task. Do you want me to do anything else?",
                "That task is complete. What should I handle next?",
                "I have finished that. Do you need another action?",
                "The previous task has been executed. What is next?",
            ],
        )
        self._event_sink: AssistantEventSink | None = None

    def set_event_sink(self, event_sink: AssistantEventSink | None) -> None:
        self._event_sink = event_sink

    def emit(self, event_type: str, **payload: Any) -> None:
        if not self._event_sink:
            return
        self._event_sink({"type": event_type, "timestamp": time.time(), **payload})

    def check(self, voice: bool = True, mic: bool = True, wakeword: bool = True) -> None:
        self.emit("status", state="checking", message="Checking local services")
        self.llm.check()
        if voice:
            self.tts.check()
        if mic:
            self.stt.check()
        if wakeword and self.wake_word_enabled:
            self.wakeword.check()
        self.emit("status", state="ready", message="JARVIS is ready")

    def run_text_loop(self) -> None:
        LOG.info("%s online in text mode", self.name)
        print(f"{self.name} online. Type 'exit' to quit.")
        while True:
            try:
                user_text = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if user_text.lower() in {"exit", "quit", "bye"}:
                return
            self.respond(user_text)

    def run_voice_loop(self) -> None:
        LOG.info("%s online in voice mode", self.name)
        print(f"{self.name} online. Say 'Hey Jarvis' or press Enter for manual capture. Ctrl+C exits.")
        self.emit("status", state="online", message=f"{self.name} online")
        self.tts.speak(f"{self.name} online.")
        while True:
            try:
                if self.wake_word_enabled:
                    self.emit("status", state="waiting", message="Waiting for wake word")
                    self.wakeword.wait()
                elif self.keyboard_fallback:
                    self.emit("status", state="waiting", message="Waiting for manual capture")
                    input("Press Enter to speak...")

                self.emit("status", state="listening", message="Listening for speech")
                self.tts.speak("Yes?")
                user_text = self.stt.listen_once()
                if not user_text:
                    LOG.info("No speech detected")
                    self.emit("status", state="no_speech", message="No speech detected")
                    self.tts.speak("I did not hear that.")
                    continue
                print(f"You: {user_text}")
                if user_text.lower().strip() in {"exit", "quit", "shutdown", "goodbye"}:
                    self.tts.speak("Shutting down.")
                    return
                self.respond(user_text)
                time.sleep(self.rearm_delay_seconds)
            except KeyboardInterrupt:
                print()
                self.emit("status", state="shutdown", message="Shutting down")
                self.tts.speak("Shutting down.")
                return

    def respond(self, user_text: str) -> str:
        self.emit("transcript", text=user_text)
        try:
            self.emit("status", state="thinking", message="Processing request")
            command_response = self.commands.handle(user_text)
            if command_response is not None:
                response = self._with_follow_up(command_response)
            else:
                response = self.llm.ask(user_text)
        except Exception as exc:
            LOG.exception("Failed to respond")
            response = f"I could not complete that request: {exc}"
        print(f"{self.name}: {response}")
        self.emit("assistant", text=response)
        try:
            self.tts.speak(response)
        except Exception as exc:
            LOG.exception("Failed to speak response")
            print(f"{self.name} voice error: {exc}")
        self.emit("status", state="ready", message="Ready for the next request")
        return response

    def _with_follow_up(self, response: str) -> str:
        if not self._should_add_follow_up(response):
            return response
        prompt = random.choice(self.follow_up_prompts)
        return f"{response} {prompt}"

    def _should_add_follow_up(self, response: str) -> bool:
        lowered = response.lower()
        failure_markers = (
            "i could not",
            "i cannot",
            "could not",
            "cannot",
            "what should",
            "which ",
            "for safety",
            "not executable",
            "not found",
            "tell me",
        )
        return not any(marker in lowered for marker in failure_markers)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local JARVIS voice assistant")
    parser.add_argument("--config", default="config.json", help="Path to config JSON")
    parser.add_argument("--text", action="store_true", help="Run keyboard text mode")
    parser.add_argument("--no-wakeword", action="store_true", help="Skip wake word and use Enter-to-speak")
    parser.add_argument("--no-voice", action="store_true", help="Disable Piper speech output")
    parser.add_argument("--check", action="store_true", help="Run startup checks and exit")
    parser.add_argument("--mic-test", action="store_true", help="Record once and print the transcription")
    parser.add_argument("--list-tools", action="store_true", help="Print the local tool registry and exit")
    parser.add_argument("--gui", action="store_true", help="Run the local web GUI server")
    parser.add_argument("--gui-host", default="127.0.0.1", help="Host for the GUI API/static server")
    parser.add_argument("--gui-port", type=int, default=8765, help="Port for the GUI API/static server")
    parser.add_argument("--gui-no-voice-loop", action="store_true", help="Do not start wake-word voice loop behind the GUI")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    if args.no_wakeword:
        config["assistant"]["wake_word_enabled"] = False
    if args.no_voice:
        config["tts"]["enabled"] = False

    configure_logging(config["assistant"].get("log_level", "INFO"))
    assistant = JarvisAssistant(config)

    try:
        assistant.check(
            voice=not args.no_voice,
            mic=not args.text,
            wakeword=not args.text and not args.no_wakeword,
        )
    except RuntimeError as exc:
        LOG.error("%s", exc)
        return 1

    if args.check:
        print("Startup checks passed.")
        return 0
    if args.list_tools:
        print(assistant.commands.describe_tools())
        return 0
    if args.gui:
        from modules.gui_server import run_gui_server

        run_gui_server(
            assistant=assistant,
            host=args.gui_host,
            port=args.gui_port,
            start_voice_loop=not args.gui_no_voice_loop,
        )
        return 0
    if args.mic_test:
        print("Speak after the prompt. JARVIS will print what it heard.")
        text = assistant.stt.listen_once()
        print(f"Heard: {text or '[nothing detected]'}")
        return 0
    if args.text:
        assistant.run_text_loop()
    else:
        assistant.run_voice_loop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
