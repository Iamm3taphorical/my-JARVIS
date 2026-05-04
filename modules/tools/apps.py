from __future__ import annotations

import difflib
import logging
import os
import re
import shlex
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


LOG = logging.getLogger(__name__)


class LaunchError(RuntimeError):
    pass


class AppTools:
    YOUTUBE_TOP_VIDEO_FILTER = "CAMSAhAB"
    YOUTUBE_VIDEO_ID_RE = re.compile(r'"videoRenderer"\s*:\s*\{\s*"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"')

    TARGET_ALIASES = {
        "b s code": "vs code",
        "brave": "brave browser",
        "browse": "browser",
        "brouser": "browser",
        "calculator app": "calculator",
        "chrome browser": "chrome",
        "code editor": "vs code",
        "crhome": "chrome",
        "file": "files",
        "file manager": "files",
        "folder": "files",
        "gmail website": "gmail",
        "googlechrome": "google chrome",
        "settings app": "settings",
        "system monitor": "monitor",
        "terminal app": "terminal",
        "u tube": "youtube",
        "visual studio": "visual studio code",
        "visual studio code editor": "visual studio code",
        "vs": "vs code",
        "vs cold": "vs code",
        "vs court": "vs code",
        "word": "word editor",
        "word processor": "word editor",
        "youtube website": "youtube",
        "youtube music": "youtube music",
        "you tube music": "youtube music",
        "you tube": "youtube",
        "you too": "youtube",
    }

    def __init__(
        self,
        browser: str,
        browser_url: str,
        allowed_apps: dict[str, str],
        websites: dict[str, str],
        scripts_dir: Path,
        notes_dir: Path,
        project_root: Path,
        code_editor: str,
    ) -> None:
        self.browser = browser
        self.browser_url = browser_url
        self.allowed_apps = allowed_apps
        self.websites = websites
        self.scripts_dir = scripts_dir
        self.notes_dir = notes_dir
        self.project_root = project_root
        self.code_editor = code_editor
        self._desktop_apps: dict[str, str] | None = None

    def open_target(self, target: str) -> str:
        target = self._normalize_target(target)
        if not target:
            return "What should I open?"
        target = self._resolve_fuzzy_target(target)

        if target in ("browser", "web", "internet"):
            return self._launch_response("browser", [self.browser, self.browser_url])
        if target in self.websites:
            return self._launch_response(target, [self.browser, self.websites[target]])

        command = self.allowed_apps.get(target)
        if command:
            return self._launch_response(target, shlex.split(command))

        desktop_id = self._find_desktop_app(target)
        if desktop_id:
            try:
                self._launch_desktop(desktop_id)
            except LaunchError as exc:
                return f"I found {target}, but could not open it: {exc}"
            return f"Opening {target}."

        binary = target.replace(" ", "-")
        if self._binary_exists(binary):
            return self._launch_response(target, [binary])

        known = ", ".join(sorted(set(self.allowed_apps) | set(self.websites)))
        return f"I could not find '{target}' as an installed app. Known shortcuts include: {known}."

    def run_script(self, script_name: str) -> str:
        safe_name = Path(script_name).name
        script = self.scripts_dir / safe_name
        if not script.exists() or not script.is_file():
            return f"I could not find script '{safe_name}' in {self.scripts_dir}."
        if not os.access(script, os.X_OK):
            return f"Script '{safe_name}' exists but is not executable."

        try:
            self._launch([str(script)], cwd=str(self.scripts_dir.parent))
        except LaunchError as exc:
            return f"I found script {safe_name}, but could not run it: {exc}"
        return f"Running script {safe_name}."

    def search_web(self, query: str, provider: str = "google") -> str:
        query = query.strip()
        if not query:
            return "What should I search for?"

        provider = self._normalize_target(provider)
        encoded = urllib.parse.quote_plus(query)
        if provider in {"youtube", "you tube"}:
            url = f"https://www.youtube.com/results?search_query={encoded}"
            label = "YouTube"
        elif provider in {"github"}:
            url = f"https://github.com/search?q={encoded}"
            label = "GitHub"
        else:
            url = f"https://www.google.com/search?q={encoded}"
            label = "Google"
        return self._launch_response(f"{label} search", [self.browser, url])

    def play_media(self, query: str, platform: str = "youtube") -> str:
        query = self._strip_terminal_punctuation(query.strip())
        platform = self._normalize_target(platform or "youtube")

        if platform in {"spotify"}:
            url = "https://open.spotify.com/search"
            if query:
                url = f"{url}/{urllib.parse.quote(query)}"
            return self._launch_response("Spotify", [self.browser, url])

        if platform in {"youtube music", "music"}:
            url = "https://music.youtube.com"
            if query:
                url = f"{url}/search?q={urllib.parse.quote_plus(query)}"
            return self._launch_response("YouTube Music", [self.browser, url])

        if query and query not in {"music", "song", "songs"}:
            watch_url = self._resolve_youtube_top_video_url(query)
            if watch_url:
                return self._launch_response("top YouTube video", [self.browser, watch_url])

            url = self._youtube_search_url(query, sort_by_views=True)
            return self._launch_response("YouTube search", [self.browser, url])

        url = "https://www.youtube.com"
        return self._launch_response("YouTube", [self.browser, url])

    def write_note(self, content: str, editor: str = "word editor") -> str:
        content = content.strip()
        if not content:
            return "What should I write?"

        self.notes_dir.mkdir(parents=True, exist_ok=True)
        note_path = self.notes_dir / f"jarvis-note-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
        note_path.write_text(content + "\n", encoding="utf-8")

        editor_target = self._normalize_target(editor)
        fallback_targets = [editor_target, "text editor", "word editor"]
        seen_targets: set[str] = set()
        last_error = ""
        for target in fallback_targets:
            if target in seen_targets:
                continue
            seen_targets.add(target)
            command = self.allowed_apps.get(target)
            if not command:
                continue
            try:
                self._launch(shlex.split(command) + [str(note_path)])
            except LaunchError as exc:
                last_error = str(exc)
                continue
            return f"I wrote that to {note_path.name} and opened it in {target}."

        try:
            self._launch(["xdg-open", str(note_path)])
        except LaunchError as exc:
            reason = last_error or str(exc)
            return f"I wrote the note to {note_path}, but could not open it: {reason}"
        return f"I wrote that to {note_path.name} and opened it."

    def open_project_file(self, query: str) -> str:
        query = self._normalize_file_query(query)
        if not query:
            return "Which project file should I open?"

        file_path = self._find_project_file(query)
        if file_path is None:
            return f"I could not find a project file matching '{query}'."

        command = self.allowed_apps.get(self.code_editor) or self.allowed_apps.get("vs code") or self.allowed_apps.get("code")
        if command:
            return self._launch_response(file_path.name, shlex.split(command) + [str(file_path)])
        return self._launch_response(file_path.name, ["xdg-open", str(file_path)])

    def _normalize_target(self, target: str) -> str:
        normalized = self._strip_terminal_punctuation(target.lower().strip())
        normalized = re.sub(r"\b(?:please|kindly)\b", " ", normalized)
        normalized = re.sub(r"^(?:open|launch|start)\s+", " ", normalized)
        normalized = re.sub(r"\s+(?:for\s+me|for\s+us|now|please|kindly|thanks|thank\s+you)$", " ", normalized)
        normalized = re.sub(r"\b(?:the|my)\b", " ", normalized)
        normalized = " ".join(normalized.split())

        tokens = normalized.split()
        if len(tokens) > 1 and tokens[-1] in {"app", "application", "website", "site"}:
            tokens = tokens[:-1]
        if len(tokens) > 1 and tokens[-1] in {"browser", "brouser"}:
            tokens = tokens[:-1]
        normalized = " ".join(tokens)
        return self.TARGET_ALIASES.get(normalized, normalized)

    def _normalize_file_query(self, query: str) -> str:
        normalized = self._strip_terminal_punctuation(query.lower().strip())
        normalized = re.sub(r"\b(?:please|kindly|for\s+me|in\s+vs\s+code|in\s+code|in\s+the\s+editor)\b", " ", normalized)
        normalized = normalized.replace(" dot ", ".").replace(" slash ", "/")
        normalized = normalized.replace(" config json", " config.json")
        normalized = normalized.replace(" read me", "readme").replace(" readme", "readme")
        return " ".join(normalized.split()).strip("'\" ")

    def _strip_terminal_punctuation(self, text: str) -> str:
        return re.sub(r"[,\.\!\?;:]+$", "", text).strip()

    def _launch_response(self, target: str, command: list[str]) -> str:
        try:
            self._launch(command)
        except LaunchError as exc:
            return f"I found {target}, but could not open it: {exc}"
        return f"Opening {target}."

    def _youtube_search_url(self, query: str, sort_by_views: bool = False) -> str:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.youtube.com/results?search_query={encoded}"
        if sort_by_views:
            url = f"{url}&sp={self.YOUTUBE_TOP_VIDEO_FILTER}"
        return url

    def _resolve_youtube_top_video_url(self, query: str) -> str | None:
        search_url = self._youtube_search_url(query, sort_by_views=True)
        request = urllib.request.Request(
            search_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                html = response.read(3_000_000).decode("utf-8", errors="ignore")
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            LOG.info("Could not resolve YouTube top video for %r: %s", query, exc)
            return None

        video_id = self._extract_youtube_video_id(html)
        if not video_id:
            LOG.info("Could not find a YouTube video id in search results for %r", query)
            return None
        return f"https://www.youtube.com/watch?v={video_id}"

    def _extract_youtube_video_id(self, html: str) -> str | None:
        match = self.YOUTUBE_VIDEO_ID_RE.search(html)
        if match:
            return match.group(1)
        return None

    def _launch(self, command: list[str], cwd: str | None = None) -> None:
        if not command:
            raise LaunchError("empty launch command")
        executable = command[0]
        if "/" in executable:
            path = Path(executable).expanduser()
            if not path.exists():
                raise LaunchError(f"executable not found: {path}")
        elif not self._binary_exists(executable):
            raise LaunchError(f"executable not found on PATH: {executable}")

        try:
            process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            raise LaunchError(str(exc)) from exc

        try:
            return_code = process.wait(timeout=0.75)
        except subprocess.TimeoutExpired:
            return
        if return_code != 0:
            raise LaunchError(f"command exited with status {return_code}")

    def _launch_desktop(self, desktop_id: str) -> None:
        launcher = shutil.which("gtk-launch")
        if launcher:
            self._launch([launcher, desktop_id])
            return
        desktop_path = self._desktop_path(desktop_id)
        if desktop_path:
            self._launch(["xdg-open", str(desktop_path)])
            return
        raise LaunchError(f"desktop entry not found: {desktop_id}")

    def _binary_exists(self, binary: str) -> bool:
        return shutil.which(binary) is not None

    def _resolve_fuzzy_target(self, target: str) -> str:
        if target in self._known_targets():
            return target

        candidates = sorted(self._known_targets())
        compact_target = target.replace(" ", "")
        cutoff = 0.88 if len(compact_target) < 5 else 0.76
        matches = difflib.get_close_matches(target, candidates, n=1, cutoff=cutoff)
        if matches:
            return self.TARGET_ALIASES.get(matches[0], matches[0])

        best = ""
        best_score = 0.0
        for candidate in candidates:
            score = difflib.SequenceMatcher(None, compact_target, candidate.replace(" ", "")).ratio()
            if score > best_score:
                best = candidate
                best_score = score
        if best and best_score >= cutoff:
            return self.TARGET_ALIASES.get(best, best)
        return target

    def _known_targets(self) -> set[str]:
        return (
            {"browser", "web", "internet", "youtube music", "spotify"}
            | set(self.allowed_apps)
            | set(self.websites)
            | set(self.TARGET_ALIASES)
            | set(self.TARGET_ALIASES.values())
        )

    def _find_project_file(self, query: str) -> Path | None:
        direct = (self.project_root / query).resolve()
        try:
            direct.relative_to(self.project_root)
        except ValueError:
            return None
        if direct.exists() and direct.is_file():
            return direct

        query_compact = query.replace(" ", "").lower()
        ignored = {".git", "venv", ".venv", "__pycache__", "node_modules", "dist", "voices"}
        best: tuple[float, Path] | None = None
        for path in self.project_root.rglob("*"):
            if not path.is_file() or any(part in ignored for part in path.parts):
                continue
            rel = path.relative_to(self.project_root).as_posix().lower()
            name = path.name.lower()
            candidates = {
                rel,
                name,
                name.replace(".", " "),
                rel.replace("/", " "),
                rel.replace("/", " ").replace(".", " "),
            }
            if query in candidates or query_compact in {candidate.replace(" ", "") for candidate in candidates}:
                return path
            score = max(difflib.SequenceMatcher(None, query_compact, candidate.replace(" ", "")).ratio() for candidate in candidates)
            if score >= 0.78 and (best is None or score > best[0]):
                best = (score, path)
        return best[1] if best else None

    def _find_desktop_app(self, target: str) -> str:
        apps = self._load_desktop_apps()
        return apps.get(target, "")

    def _load_desktop_apps(self) -> dict[str, str]:
        if self._desktop_apps is not None:
            return self._desktop_apps

        apps: dict[str, str] = {}
        directories = [
            Path.home() / ".local/share/applications",
            Path("/usr/local/share/applications"),
            Path("/usr/share/applications"),
            Path("/var/lib/flatpak/exports/share/applications"),
            Path.home() / ".local/share/flatpak/exports/share/applications",
        ]
        for directory in directories:
            if not directory.exists():
                continue
            for desktop_file in directory.glob("*.desktop"):
                desktop_id = desktop_file.name.removesuffix(".desktop")
                for name in self._desktop_names(desktop_file):
                    apps.setdefault(name, desktop_id)
        self._desktop_apps = apps
        return apps

    def _desktop_names(self, desktop_file: Path) -> set[str]:
        names: set[str] = {desktop_file.stem.lower().replace(".", " ").replace("-", " ")}
        try:
            for line in desktop_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith(("Name=", "GenericName=")):
                    value = line.split("=", 1)[1].strip().lower()
                    if value:
                        names.add(value)
        except OSError:
            pass
        return {" ".join(name.split()) for name in names}

    def _desktop_path(self, desktop_id: str) -> Path | None:
        filename = f"{desktop_id}.desktop"
        for directory in (
            Path.home() / ".local/share/applications",
            Path("/usr/local/share/applications"),
            Path("/usr/share/applications"),
        ):
            candidate = directory / filename
            if candidate.exists():
                return candidate
        return None
