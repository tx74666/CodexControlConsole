import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import tempfile
from pathlib import Path
from console_vision_status import vision_status

with tempfile.TemporaryDirectory() as d:
    p=Path(d)/"receipt.json"
    valid=dict(mode="read-only development component",liveMcpVerified=True,discoveredTools=76,sourceCommit="a"*40,version="0.1.0")
    p.write_text(json.dumps(valid))
    assert vision_status(receipt=p)["state"]=="disabled"
    print("PASS default disabled")
    r=vision_status(enabled=True,receipt=p)
    assert r["reportedToolCount"]==76 and not r["liveVerified"] and not r["executionEnabled"]
    print("PASS historical receipt only")
    for bad in ({**valid,"discoveredTools":True},{**valid,"sourceCommit":"bad"},{**valid,"liveMcpVerified":False},[],None):
        p.write_text(json.dumps(bad))
        assert vision_status(enabled=True,receipt=p)["state"]=="not_verified"
    print("PASS malformed receipts")
    p.write_bytes(b"x"*8193)
    assert vision_status(enabled=True,receipt=p)["state"]=="not_verified"
    p.unlink()
    assert vision_status(enabled=True,receipt=p)["state"]=="not_verified"
    print("PASS oversized and missing receipt")
