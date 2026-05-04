from __future__ import annotations

import datetime as dt
import os
import subprocess
from pathlib import Path

from modules.utils import PROJECT_ROOT


class SystemTools:
    def current_time(self) -> str:
        return f"The time is {dt.datetime.now().strftime('%I:%M %p').lstrip('0')}."

    def battery_status(self) -> str:
        supplies = Path("/sys/class/power_supply")
        batteries = sorted(supplies.glob("BAT*")) if supplies.exists() else []
        if not batteries:
            return "I could not find a battery on this system."

        battery = batteries[0]
        capacity = self._read_file(battery / "capacity")
        status = self._read_file(battery / "status")
        if capacity:
            return f"Battery is at {capacity}%{f' and {status.lower()}' if status else ''}."
        return "I found the battery, but could not read its charge level."

    def system_stats(self) -> str:
        load = os.getloadavg()
        memory = self._memory_status()
        disk = self._disk_status(PROJECT_ROOT)
        return f"Load average is {load[0]:.2f}, {load[1]:.2f}, {load[2]:.2f}. {memory} {disk}"

    def _memory_status(self) -> str:
        meminfo = {}
        try:
            with Path("/proc/meminfo").open("r", encoding="utf-8") as handle:
                for line in handle:
                    key, value = line.split(":", 1)
                    meminfo[key] = int(value.strip().split()[0])
        except OSError:
            return "Memory status is unavailable."

        total = meminfo.get("MemTotal", 0)
        available = meminfo.get("MemAvailable", 0)
        if not total:
            return "Memory status is unavailable."
        used_pct = 100 - (available / total * 100)
        return f"Memory usage is about {used_pct:.0f}%."

    def _disk_status(self, path: Path) -> str:
        usage = subprocess.run(["df", "-h", str(path)], capture_output=True, text=True, check=False).stdout.strip().splitlines()
        if len(usage) < 2:
            return "Disk status is unavailable."
        columns = usage[1].split()
        return f"Disk usage for this project drive is {columns[4]}."

    def _read_file(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
