"""Release-bundle checks; own native host runs only with empty temporary data."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HOST_NAME = "com.tx74666.codex_console_chat_relay"
EXTENSION_ID = "ggjlmdfnbknlicnibfngaenlakeabkfk"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def disabled_frame(executable, origin, environment):
    hello = json.dumps({"protocol": "console_chat_relay/v1", "type": "hello", "hostName": HOST_NAME}).encode()
    result = subprocess.run([str(executable), origin], input=struct.pack("<I", len(hello)) + hello,
                            capture_output=True, env=environment, timeout=30,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    require(len(result.stdout) >= 4, "Native host did not emit a binary status frame")
    size = struct.unpack("<I", result.stdout[:4])[0]
    require(0 < size <= 1024 * 1024 and len(result.stdout) == 4 + size,
            "Native host stdout contains incomplete framing or unrelated text")
    status = json.loads(result.stdout[4:].decode("utf-8"))
    require(set(status) == {"protocol", "type", "hostName", "enabled", "approved", "configured", "clientReady", "message"},
            "Native host status fields changed")
    require(status["protocol"] == "console_chat_relay/v1" and status["type"] == "status" and status["hostName"] == HOST_NAME,
            "Native host protocol identity changed")
    require(all(status[key] is False for key in ("enabled", "approved", "configured", "clientReady")),
            "Unapproved native host became ready")
    require(not result.stderr, "Native host emitted unexpected stderr")
    return result.returncode, status["message"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", type=Path, default=ROOT / "build" / "console-installer" / "dist" / "Codex Console")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("relay_package_preparation", ROOT / "tools" / "prepare-console-chat-relay.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.inspect_bundle(args.app_dir)
    executable = args.app_dir.resolve() / "_internal" / "tools" / "Codex Chat Relay.exe"
    with tempfile.TemporaryDirectory(prefix="console-relay-package-disabled-") as directory:
        environment = dict(os.environ, LOCALAPPDATA=directory, CODEX_CONTROL_DATA_DIR=directory)
        before = set(Path(directory).rglob("*"))
        code, message = disabled_frame(executable, "chrome-extension://" + EXTENSION_ID + "/", environment)
        require((code, message) == (3, "not_approved_or_product_unavailable"), "Unapproved host did not fail closed")
        code, message = disabled_frame(executable, "chrome-extension://" + "a" * 32 + "/", environment)
        require((code, message) == (2, "native_extension_origin_invalid"), "Wrong extension origin was accepted")
        require(set(Path(directory).rglob("*")) == before, "Disabled host created approval or a new data store")
    print("PASS packaged relay: actual AMD64 console host, frozen minimal extension resources, binary disabled status, no data created")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
