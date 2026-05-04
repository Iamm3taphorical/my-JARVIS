from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules.tools.apps import AppTools
from modules.tools.registry import LocalToolRegistry


def command_config(scripts_dir: str) -> dict:
    return {
        "browser": "xdg-open",
        "browser_url": "https://www.google.com",
        "weather_location": "Dhaka",
        "allowed_apps": {
            "chrome": "google-chrome",
            "google chrome": "google-chrome",
            "vs code": "code",
            "visual studio code": "code",
            "code": "code",
            "terminal": "x-terminal-emulator",
            "text editor": "gnome-text-editor",
            "word editor": "libreoffice --writer",
        },
        "websites": {
            "github": "https://github.com",
            "youtube": "https://www.youtube.com",
        },
        "scripts_dir": scripts_dir,
        "notes_dir": scripts_dir,
        "code_editor": "vs code",
    }


class CommandRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.launches: list[tuple[list[str], str | None]] = []
        self.registry = LocalToolRegistry(command_config(self.temp_dir.name))

        def fake_launch(command: list[str], cwd: str | None = None) -> None:
            self.launches.append((command, cwd))

        self.registry.apps._launch = fake_launch

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_open_browser_target_is_not_stripped(self) -> None:
        response = self.registry.handle("open browser")

        self.assertEqual(response, "Opening browser.")
        self.assertEqual(self.launches, [(["xdg-open", "https://www.google.com"], None)])

    def test_natural_website_open_phrase(self) -> None:
        response = self.registry.handle("can you please open the youtube website?")

        self.assertEqual(response, "Opening youtube.")
        self.assertEqual(self.launches, [(["xdg-open", "https://www.youtube.com"], None)])

    def test_open_phrase_ignores_trailing_for_me(self) -> None:
        response = self.registry.handle("open youtube for me")

        self.assertEqual(response, "Opening youtube.")
        self.assertEqual(self.launches, [(["xdg-open", "https://www.youtube.com"], None)])

    def test_app_open_phrase_ignores_trailing_for_me(self) -> None:
        response = self.registry.handle("can you open vs code for me")

        self.assertEqual(response, "Opening vs code.")
        self.assertEqual(self.launches, [(["code"], None)])

    def test_misheard_open_and_target_alias(self) -> None:
        response = self.registry.handle("Jarvis, oven chrome browser")

        self.assertEqual(response, "Opening chrome.")
        self.assertEqual(self.launches, [(["google-chrome"], None)])

    def test_navigation_phrase_opens_website(self) -> None:
        response = self.registry.handle("go to github")

        self.assertEqual(response, "Opening github.")
        self.assertEqual(self.launches, [(["xdg-open", "https://github.com"], None)])

    def test_search_web_opens_google_search(self) -> None:
        response = self.registry.handle("search the web for bengali accent speech recognition")

        self.assertEqual(response, "Opening Google search.")
        self.assertEqual(
            self.launches,
            [(["xdg-open", "https://www.google.com/search?q=bengali+accent+speech+recognition"], None)],
        )

    def test_play_music_opens_youtube_search(self) -> None:
        response = self.registry.handle("play lofi music on youtube")

        self.assertEqual(response, "Opening YouTube.")
        self.assertEqual(self.launches, [(["xdg-open", "https://www.youtube.com/results?search_query=lofi+music"], None)])

    def test_write_note_opens_editor_with_created_file(self) -> None:
        response = self.registry.handle("write buy milk in text editor")

        self.assertIn("I wrote that to jarvis-note-", response)
        command, _cwd = self.launches[0]
        self.assertEqual(command[0], "gnome-text-editor")
        self.assertTrue(command[1].endswith(".txt"))

    def test_open_project_file_in_code_editor(self) -> None:
        response = self.registry.handle("open config json in vs code")

        self.assertEqual(response, "Opening config.json.")
        command, _cwd = self.launches[0]
        self.assertEqual(command[0], "code")
        self.assertTrue(command[1].endswith("config.json"))

    def test_unknown_open_target_does_not_fall_through_to_llm(self) -> None:
        response = self.registry.handle("open definitely not a real app")

        self.assertIsInstance(response, str)
        self.assertIn("I could not find", response)
        self.assertEqual(self.launches, [])

    def test_arbitrary_run_command_is_rejected(self) -> None:
        response = self.registry.handle("run rm command")

        self.assertIsInstance(response, str)
        self.assertIn("For safety", response)
        self.assertEqual(self.launches, [])

    def test_unsupported_desktop_action_is_rejected(self) -> None:
        response = self.registry.handle("click the install button")

        self.assertIsInstance(response, str)
        self.assertIn("I cannot perform that desktop action yet", response)
        self.assertEqual(self.launches, [])


class AppLaunchTests(unittest.TestCase):
    def test_missing_allowlisted_executable_reports_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            apps = AppTools(
                browser="xdg-open",
                browser_url="https://www.google.com",
                allowed_apps={"missing": "definitely-not-installed-jarvis"},
                websites={},
                scripts_dir=Path(temp_dir),
                notes_dir=Path(temp_dir),
                project_root=Path(temp_dir),
                code_editor="vs code",
            )

            response = apps.open_target("missing")

        self.assertIn("could not open it", response)
        self.assertIn("executable not found", response)


if __name__ == "__main__":
    unittest.main()
