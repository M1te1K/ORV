"""Проверка регистрации macOS LaunchAgent без запуска эффектов."""

import importlib.util
import plistlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1] / "mac" / "orvi_mac.py"


def load_mac_module():
    spec = importlib.util.spec_from_file_location("orvi_mac_under_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MacAutostartTest(unittest.TestCase):
    def test_source_and_bundled_targets(self):
        module = load_mac_module()
        with mock.patch.object(module.sys, "frozen", False, create=True), \
             mock.patch.object(module.sys, "executable", "/opt/python3"):
            self.assertEqual(module._agent_target(), ["/opt/python3", str(SOURCE)])
        with mock.patch.object(module.sys, "frozen", True, create=True), \
             mock.patch.object(module.sys, "executable", "/Applications/ORVI.app/Contents/MacOS/ORVI"):
            self.assertEqual(module._agent_target(), ["/Applications/ORVI.app/Contents/MacOS/ORVI"])

    def test_install_is_visible_idempotent_and_uninstall_removes_agent(self):
        module = load_mac_module()
        calls = []
        loaded = False

        def launchctl(*args, check=True):
            nonlocal loaded
            calls.append(args)
            if args[0] == "print":
                return subprocess.CompletedProcess(args, 0 if loaded else 113)
            if args[0] == "bootstrap":
                loaded = True
            if args[0] == "bootout":
                loaded = False
            return subprocess.CompletedProcess(args, 0)

        with tempfile.TemporaryDirectory() as directory:
            agent_path = Path(directory) / "com.orvi.simulator.plist"
            with mock.patch.object(module, "AGENT_PATH", str(agent_path)), \
                 mock.patch.object(module, "_agent_target", return_value=["/opt/python3", str(SOURCE)]), \
                 mock.patch.object(module, "_launchctl", side_effect=launchctl), \
                 mock.patch.object(module.os, "getuid", return_value=501):
                module.enable_autostart()
                data = plistlib.loads(agent_path.read_bytes())
                self.assertEqual(data, {
                    "Label": "com.orvi.simulator",
                    "ProgramArguments": ["/opt/python3", str(SOURCE)],
                    "RunAtLoad": True,
                })
                self.assertEqual(calls[-1], ("bootstrap", "gui/501", str(agent_path)))
                bootstrap_count = sum(call[0] == "bootstrap" for call in calls)
                module.enable_autostart()
                self.assertEqual(sum(call[0] == "bootstrap" for call in calls), bootstrap_count)

                module.disable_autostart()
                self.assertFalse(agent_path.exists())
                self.assertIn(("bootout", "gui/501/com.orvi.simulator"), calls)


if __name__ == "__main__":
    unittest.main()
