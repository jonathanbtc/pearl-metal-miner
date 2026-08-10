"""LuckyPool dialect, reverse-engineered from live wire traffic on
pearl-eu1.luckypool.io:3360 (2026-08-09/10, tools/pool_survey.py + probes).
Never derived from any barred source (ADR-0005).

Observed:
  → mining.authorize  params OBJECT {wallet, worker, agent}   (no subscribe;
      array params rejected with "params must be an object")
  ← {"error":null,"id":2,"result":true,"type":"plain"}
  ← mining.notify     params OBJECT:
        diff (pool difficulty, varDiff), header (76-byte hex), height,
        job_id ("<hex8>_<diff>"), target (big-endian hex)
  → mining.submit     params OBJECT {wallet, worker, job_id, plain_proof}
      (same family as kryptex/k1pool; framing not yet exercised by an
      accepted share — their starting difficulty 888888 is in diff1 units,
      ≈6.5e9 tiles/share, hours at current speed)
"""

from __future__ import annotations

import json

from .. import __version__
from .dialect import Dialect, Job, ShareResult


class LuckyPoolDialect(Dialect):
    name = "luckypool"
    miner_chooses_params = True

    def handshake_lines(self, address, worker):
        return [
            {"id": 2, "method": "mining.authorize",
             "params": {"wallet": address, "worker": worker,
                        "agent": f"pearl-metal-miner/{__version__}"}},
        ]

    def parse(self, line: str):
        msg = json.loads(line)
        if msg.get("method") == "mining.notify":
            p = msg["params"]
            return Job(
                job_id=str(p["job_id"]),
                header_bytes=bytes.fromhex(p["header"]),
                target=int(p["target"], 16),
                height=int(p.get("height", 0)),
            )
        if "result" in msg and msg.get("id") is not None:
            ok = msg.get("result") is True and not msg.get("error")
            return ShareResult(msg_id=int(msg["id"]), accepted=ok, raw=line)
        return None

    def submit_line(self, msg_id, address, worker, job_id, proof_b64):
        return {"id": msg_id, "method": "mining.submit",
                "params": {"wallet": address, "worker": worker, "job_id": job_id,
                           "plain_proof": proof_b64}}
