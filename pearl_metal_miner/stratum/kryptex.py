"""Kryptex dialect, as observed live on prl-eu.kryptex.network:7048
(2026-08-09, tools/pool_survey.py — reverse-engineered from wire traffic,
consistent with ascend_prl's independent description):

  → mining.subscribe  params: [agent]
  → mining.authorize  params: ["<address>.<worker>", "x"]     (v1 session)
  ← {"id":3,"result":true}                                     authorize ack
  ← mining.notify     params OBJECT:
        header: 152 hex chars = the 76-byte IncompleteBlockHeader, verbatim
        height, job_id ("<hex8>_<difficulty>"), target (big-endian hex),
        cert_version
  → mining.submit     params OBJECT: {worker, job_id, plain_proof: base64}
  ← {"id":N,"result":true|false-or-error}

The miner chooses m, n, k, rank and the patterns; they travel inside the
PlainProof and the pool grades against them.

Verification depth, stated exactly: subscribe/authorize/notify are observed
live (survey above). The submit framing is the same family as
luckypool/k1pool but has NOT yet been exercised by an accepted share — at
this pool's fixed difficulty a share is roughly hourly, so verifying is
slow. LuckyPool is the default pool until someone closes this gap.
"""

from __future__ import annotations

import json

from .. import __version__
from .dialect import Dialect, Job, ShareResult


class KryptexDialect(Dialect):
    name = "kryptex"
    miner_chooses_params = True

    def handshake_lines(self, address, worker):
        return [
            {"id": 1, "method": "mining.subscribe",
             "params": [f"pearl-metal-miner/{__version__}"]},
            {"id": 3, "method": "mining.authorize",
             "params": [f"{address}.{worker}", "x"]},
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
                cert_version=int(p.get("cert_version", 2)),
            )
        if "result" in msg and msg.get("id") is not None:
            ok = msg.get("result") is True and not msg.get("error")
            return ShareResult(msg_id=int(msg["id"]), accepted=ok, raw=line)
        return None

    def submit_line(self, msg_id, address, worker, job_id, proof_b64):
        return {"id": msg_id, "method": "mining.submit",
                "params": {"worker": f"{address}.{worker}", "job_id": job_id,
                           "plain_proof": proof_b64}}
