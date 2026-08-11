"""The money line: per-machine economics from the user's OWN assumptions.

Fully offline by design — the miner contacts nothing but the pool, so the
three inputs (electricity price, assumed PRL price, assumed network
hashrate) come from config.toml, and every figure derived here is an
estimate resting on them. Watts are a per-chip-family table of rough public
figures, never a measurement: measuring real GPU power needs root, and this
miner never asks for a password.
"""

from __future__ import annotations

# Constants, each carrying its source:
BLOCK_TIME_S = 120        # block target ~120 s — pool survey 2026-08-10
BLOCK_REWARD_PRL = 2460   # hashrate.no, figure dated 2026-08-02
DIFF1_TARGET = 0xFFFF << 208  # the diff1 convention observed on the wire
                              # (pool survey 2026-08-10, Kryptex section)
HASHES_PER_DIFF1 = float(2 ** 256) / float(DIFF1_TARGET)  # ≈ 2^32

# Rough public GPU-power figures per chip family, watts at full tilt.
# Estimates, clearly labeled as such everywhere they surface; longest
# match wins ("M1 Max" before "M1"). Unknown chips fall back to 20 W.
GPU_WATTS_EST = {
    "M1 Ultra": 60, "M1 Max": 40, "M1 Pro": 17, "M1": 10,
    "M2 Ultra": 75, "M2 Max": 40, "M2 Pro": 20, "M2": 12,
    "M3 Ultra": 80, "M3 Max": 45, "M3 Pro": 20, "M3": 12,
    "M4 Ultra": 80, "M4 Max": 45, "M4 Pro": 22, "M4": 14,
    "M5 Ultra": 80, "M5 Max": 45, "M5 Pro": 22, "M5": 14,
}
FALLBACK_WATTS_EST = 20


def gpu_watts_est(device_name: str, intensity: int) -> float:
    """Estimated GPU watts for this chip at this duty cycle."""
    full = FALLBACK_WATTS_EST
    for chip in sorted(GPU_WATTS_EST, key=len, reverse=True):
        if chip in device_name:
            full = GPU_WATTS_EST[chip]
            break
    return full * max(1, min(intensity, 100)) / 100


def prl_per_day(tiles_per_s: float, factor: int,
                network_hashrate_ehs: float) -> float:
    """Estimated PRL/day, derived so a reader can audit every step:

    1. A share at pool difficulty D means a digest below target(D) =
       DIFF1_TARGET / D (the diff1 convention observed on the wire).
    2. One TILE wins with probability target × factor / 2^256, where
       factor = h·w·(k−k%rank) — the bound formula proved at consensus
       (pool survey, "the bar"). So one tile does the work of `factor`
       plain hashes, and this machine's rate in hash units is
       tiles/s × factor.
    3. The network finds one block (BLOCK_REWARD_PRL) every BLOCK_TIME_S
       at the ASSUMED network hashrate. Your long-run expected share of
       emission is your fraction of that hashrate:

       PRL/day = (tiles/s × factor / net_H/s) × (86400/BLOCK_TIME_S) × reward

    The result is proportional to 1/assumed-network-hashrate: it is an
    estimate resting on that assumption, and is labeled so in the UI.
    """
    if network_hashrate_ehs <= 0:
        return 0.0
    my_hashes_per_s = tiles_per_s * factor
    net_hashes_per_s = network_hashrate_ehs * 1e18
    blocks_per_day = 86400 / BLOCK_TIME_S
    return my_hashes_per_s / net_hashes_per_s * blocks_per_day * BLOCK_REWARD_PRL


def prl_per_share_est(difficulty: float, network_hashrate_ehs: float) -> float:
    """Expected PRL credit for ONE accepted share at pool difficulty D,
    under proportional payout: reward × (hashes the share represents) ÷
    (hashes the network spends per block). Estimate — pools apply fees,
    payout windows, and luck on top."""
    if network_hashrate_ehs <= 0:
        return 0.0
    share_hashes = difficulty * HASHES_PER_DIFF1
    block_hashes = network_hashrate_ehs * 1e18 * BLOCK_TIME_S
    return BLOCK_REWARD_PRL * share_hashes / block_hashes


def verdict(tiles_per_s: float, factor: int, device_name: str,
            intensity: int, electricity_usd_per_kwh: float | None,
            assumed_prl_price_usd: float | None,
            assumed_network_hashrate: float | None) -> str:
    """The dashboard money line. Missing assumptions → a pointer at init,
    never a guessed number (map Fog house rule)."""
    if None in (electricity_usd_per_kwh, assumed_prl_price_usd,
                assumed_network_hashrate):
        return "run init to set your assumptions (electricity, PRL price, network)"
    prl_day = prl_per_day(tiles_per_s, factor, assumed_network_hashrate)
    earned = prl_day * assumed_prl_price_usd
    watts = gpu_watts_est(device_name, intensity)
    power = watts / 1000 * 24 * electricity_usd_per_kwh
    net = earned - power
    return (f"est. {'+' if net >= 0 else '−'}${abs(net):.2f}/day at your "
            f"assumptions (${earned:.2f} earned − ${power:.2f} power "
            f"@ est. {watts:.0f} W)")
