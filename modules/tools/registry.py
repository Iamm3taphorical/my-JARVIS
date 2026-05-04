from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from modules.tools.apps import AppTools
from modules.tools.system import SystemTools
from modules.tools.weather import WeatherTools
from modules.utils import PROJECT_ROOT, resolve_project_path


@dataclass
class ToolSpec:
    name: str
    description: str


class LocalToolRegistry:
    OPEN_VERB_RE = r"(?:open|opin|oppen|oh\s+pen|o\s+pen|oven|happen|launch|lunch|start|bring\s+up|pull\s+up)"
    MEDIA_PLATFORM_RE = r"youtube\s+music|you\s+tube\s+music|youtube|you\s+tube|spotify"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.system = SystemTools()
        self.weather = WeatherTools(config.get("weather_location", ""))
        self.apps = AppTools(
            browser=config.get("browser", "xdg-open"),
            browser_url=config.get("browser_url", "https://www.google.com"),
            allowed_apps=config.get("allowed_apps", {}),
            websites=config.get("websites", {}),
            scripts_dir=resolve_project_path(config.get("scripts_dir", "scripts")),
            notes_dir=resolve_project_path(config.get("notes_dir", "notes")),
            project_root=PROJECT_ROOT,
            code_editor=config.get("code_editor", "vs code"),
        )
        self._tools = [
            ToolSpec("time", "Tell the current time."),
            ToolSpec("weather", "Get the current weather for a city."),
            ToolSpec("battery", "Report battery level and state."),
            ToolSpec("system_stats", "Report CPU load, memory, and disk usage."),
            ToolSpec("open_app", "Open a browser, app, website, or desktop entry."),
            ToolSpec("search_web", "Search Google, YouTube, or GitHub."),
            ToolSpec("play_media", "Open music or video search on YouTube, YouTube Music, or Spotify."),
            ToolSpec("write_note", "Write dictated text into a note file and open it in an editor."),
            ToolSpec("open_project_file", "Open a project file in the configured code editor."),
            ToolSpec("run_script", "Run an executable script from the scripts directory."),
        ]

    def describe(self) -> str:
        return "\n".join(f"- {tool.name}: {tool.description}" for tool in self._tools)

    def handle(self, text: str) -> str | None:
        normalized = self._normalize_text(text)
        if not normalized:
            return None

        if self._is_greeting(normalized):
            return "Good morning. I am online and ready."
        script_name = self._extract_script_name(normalized)
        if script_name is not None:
            if not script_name:
                return "Which script should I run?"
            return self.apps.run_script(script_name)
        write_request = self._extract_write_request(normalized)
        if write_request is not None:
            content, editor = write_request
            return self.apps.write_note(content, editor=editor)
        file_query = self._extract_project_file_query(normalized)
        if file_query is not None:
            return self.apps.open_project_file(file_query)
        play_request = self._extract_play_request(normalized)
        if play_request is not None:
            query, platform = play_request
            return self.apps.play_media(query, platform=platform)
        search_request = self._extract_search_request(normalized)
        if search_request is not None:
            query, provider = search_request
            return self.apps.search_web(query, provider=provider)
        open_target = self._extract_open_target(normalized)
        if open_target is not None:
            if not open_target:
                return "What should I open?"
            return self.apps.open_target(open_target)
        if normalized.startswith("run "):
            return "For safety, I only run executable scripts from the configured scripts directory. Say: run script name.sh."
        if self._asks_time(normalized):
            return self.system.current_time()
        if "weather" in normalized:
            return self.weather.weather(normalized)
        if "battery" in normalized:
            return self.system.battery_status()
        if any(phrase in normalized for phrase in ("system stats", "system status", "cpu", "memory", "ram")):
            return self.system.system_stats()
        if normalized in {"help", "what can you do", "list tools"}:
            return f"I can use these tools:\n{self.describe()}"
        if self._looks_like_unsupported_local_action(normalized):
            return (
                "I cannot perform that desktop action yet. I can open allowlisted apps or websites, "
                "and I can run executable scripts from the configured scripts directory."
            )
        return None

    def _normalize_text(self, text: str) -> str:
        normalized = " ".join(text.lower().strip().split())
        normalized = self._strip_invocation(normalized)
        normalized = self._strip_terminal_punctuation(normalized)
        normalized = self._strip_polite_prefixes(normalized)
        normalized = self._strip_terminal_punctuation(normalized)
        return normalized

    def _strip_invocation(self, text: str) -> str:
        return re.sub(r"^(hey\s+jarvis|jarvis)[,\s]+", "", text).strip()

    def _strip_polite_prefixes(self, text: str) -> str:
        previous = None
        while previous != text:
            previous = text
            text = re.sub(r"^(?:please|kindly)[,\s]+", "", text).strip()
            text = re.sub(r"^(?:can|could|would|will)\s+you\s+(?:please\s+)?", "", text).strip()
            text = re.sub(r"^(?:could|would)\s+you\s+kindly\s+", "", text).strip()
        return text

    def _strip_terminal_punctuation(self, text: str) -> str:
        return re.sub(r"[,\.\!\?;:]+$", "", text).strip()

    def _is_greeting(self, text: str) -> bool:
        return bool(re.search(r"\b(good morning|good afternoon|good evening|hello|hi jarvis|hey jarvis)\b", text))

    def _asks_time(self, text: str) -> bool:
        return bool(re.search(r"\b(time|what time|tell me the time)\b", text))

    def _extract_script_name(self, text: str) -> str | None:
        if text in {"run script", "run a script", "run the script"}:
            return ""
        match = re.match(r"^run\s+(?:a\s+|the\s+)?script\s+(.+)$", text)
        if match:
            return match.group(1).strip()
        match = re.match(r"^run\s+(.+?\.sh)\s+script$", text)
        if match:
            return match.group(1).strip()
        return None

    def _extract_open_target(self, text: str) -> str | None:
        if re.fullmatch(self.OPEN_VERB_RE, text):
            return ""
        patterns = [
            rf"^{self.OPEN_VERB_RE}(?:\s+up)?(?:\s+(?:the|my|a|an))?\s+(.+)$",
            r"^(?:go\s+to|visit|browse\s+to)(?:\s+(?:the|my|a|an))?\s+(.+)$",
        ]
        for pattern in patterns:
            match = re.match(pattern, text)
            if match:
                return self._strip_terminal_punctuation(match.group(1)).strip()
        return None

    def _extract_search_request(self, text: str) -> tuple[str, str] | None:
        patterns = [
            r"^(?:search|look\s+up|find)(?:\s+(?:the\s+)?(?:web|internet|online))?(?:\s+for)?\s+(.+)$",
            r"^(?:google)\s+(.+)$",
        ]
        for pattern in patterns:
            match = re.match(pattern, text)
            if not match:
                continue
            query = self._strip_terminal_punctuation(match.group(1)).strip()
            provider = "google"
            provider_match = re.match(r"^(youtube|github)\s+for\s+(.+)$", query)
            if provider_match:
                provider = provider_match.group(1)
                query = provider_match.group(2).strip()
            return query, provider
        return None

    def _extract_play_request(self, text: str) -> tuple[str, str] | None:
        match = re.match(
            rf"^play(?:\s+(?:music|song|songs))?(?:\s+(.+?))?"
            rf"(?:\s+(?:on|in|from|at)\s+({self.MEDIA_PLATFORM_RE}))?$",
            text,
        )
        if not match:
            return None
        query = self._strip_terminal_punctuation(match.group(1) or "").strip()
        platform = match.group(2) or "youtube"
        trailing_platform = re.search(rf"\s+(?:on|in|from|at|and)\s+({self.MEDIA_PLATFORM_RE})$", query)
        if trailing_platform:
            platform = trailing_platform.group(1)
            query = query[: trailing_platform.start()].strip()
        return query, platform

    def _extract_write_request(self, text: str) -> tuple[str, str] | None:
        patterns = [
            r"^open\s+(word\s+editor|writer|text\s+editor)\s+and\s+(?:write|type)\s+(.+)$",
            r"^(?:write|type|create\s+(?:a\s+)?note|make\s+(?:a\s+)?note)(?:\s+down)?\s+(.+?)(?:\s+in\s+(word\s+editor|writer|text\s+editor))?$",
        ]
        for index, pattern in enumerate(patterns):
            match = re.match(pattern, text)
            if not match:
                continue
            groups = match.groups()
            if index == 0:
                editor = groups[0]
                content = groups[1]
            else:
                content = groups[0]
                editor = groups[1] or "word editor"
            return self._strip_terminal_punctuation(content).strip(), editor
        return None

    def _extract_project_file_query(self, text: str) -> str | None:
        patterns = [
            r"^open\s+(?:the\s+)?(?:code\s+)?file\s+(.+)$",
            r"^open\s+(.+?)\s+in\s+(?:vs\s+code|vscode|code|the\s+editor)$",
        ]
        for pattern in patterns:
            match = re.match(pattern, text)
            if match:
                return self._strip_terminal_punctuation(match.group(1)).strip()
        return None

    def _looks_like_unsupported_local_action(self, text: str) -> bool:
        return bool(
            re.match(
                r"^(?:close|quit|install|uninstall|delete|remove|move|copy|click|press|"
                r"change\s+settings|set\s+up|turn\s+on|turn\s+off)\b",
                text,
            )
        )
