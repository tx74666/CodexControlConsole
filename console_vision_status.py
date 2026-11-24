"""Read-only integration receipt for the local desktop Console.
No process launch, tool execution, network access or permission grants.
A receipt is historical evidence, not a live health check.
"""
import json
from pathlib import Path
import os
import re

def vision_status(*, enabled=False, receipt=None):
    result = {"enabled": enabled is True, "executionEnabled": False,
              "liveVerified": False, "state": "disabled"}
    if enabled is not True:
        return result
    result["state"] = "not_verified"
    try:
        p = Path(receipt) if receipt is not None else Path(os.environ["LOCALAPPDATA"]) / "ConsoleVisionIntegration" / "0.1.0" / "installation.json"
        if not p.is_file() or p.is_symlink() or p.stat().st_size > 8192:
            return result
        with p.open("rb") as stream:
            raw = stream.read(8193)
        if len(raw) > 8192:
            return result
        data = json.loads(raw)
        if not isinstance(data, dict):
            return result
        if data.get("mode") != "read-only development component" or data.get("liveMcpVerified") is not True:
            return result
        count = data.get("discoveredTools")
        commit = data.get("sourceCommit")
        version = data.get("version")
        if type(count) is not int or not 0 < count <= 10000 or not isinstance(commit, str) or not re.fullmatch("[0-9a-f]{40}", commit) or not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
            return result
        result.update(state="previous_discovery_reported", reportedToolCount=count,
                      componentVersion=version, sourceCommit=commit)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return result
