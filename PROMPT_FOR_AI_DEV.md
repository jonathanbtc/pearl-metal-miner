# Prompt for an AI dev agent

Want an AI coding agent (Claude Code, Cursor, Copilot Workspace, …) to set
this miner up for you? Copy everything inside the block below and paste it as
your first message. It works best if you start the agent inside an empty
folder (or inside a clone of this repo — the prompt handles both).

Replace `YOUR_PRL_ADDRESS` at the top with your own `prl1p…` address, or
leave it as-is and the agent will create a local wallet for you with the
repo's included wallet tool.

```text
I want you to set up and run pearl-metal-miner
(https://github.com/jonathanbtc/pearl-metal-miner) on this Mac, end to end.

My payout address: YOUR_PRL_ADDRESS
(If that still says YOUR_PRL_ADDRESS, I don't have one yet — create the
local wallet in step 5 instead, tell me you did, and remind me at the end
that wallet.json holds the only key to anything mined and must be backed
up.)

Known facts, so you don't have to rediscover them:

- This only works on Apple Silicon (M1 or newer) — check `uname -m` says
  `arm64` first and stop if it doesn't.
- Mining PRL on a Mac loses far more in electricity than it earns. I know.
  I'm running it for the demonstration, not income.
- The project's own README is the authoritative guide; prefer it over
  guesses. The short version of the steps is below.

Do this, in order, telling me briefly what you did at each step:

1. Prerequisites. Verify, and install only what's missing:
   - Xcode Command Line Tools (`xcode-select -p`; install with
     `xcode-select --install` — this one needs me to click a dialog).
   - Python 3.12+ (`python3 --version`; e.g. `brew install python@3.12`).
   - Rust (`cargo --version`; install via https://rustup.rs).

2. Clone the repo if we're not already inside it:
   `git clone https://github.com/jonathanbtc/pearl-metal-miner.git && cd pearl-metal-miner`

3. Build:
   `./packaging/setup.sh` (creates .venv, clones the pinned upstream, builds
   the py-pearl-mining extension — takes a few minutes), then
   `./packaging/build_macos.sh` (compiles the Metal host library, seconds).

4. THE GATE — run the self-test:
   `.venv/bin/python -m pearl_metal_miner.miner --self-test`
   It must print SELF-TEST PASS (about 50 exact-integer checks of the wallet
   codec and every GPU stage against the reference implementation). If it
   fails: STOP. Do not
   mine, do not work around it. Show me the full output and the exact
   failing stage — a failed self-test means shares would be silently
   rejected and electricity wasted.

5. Wallet. If I gave you a real prl1p… address above, use it. Otherwise run
   `.venv/bin/python -m pearl_metal_miner.wallet new` once, and tell me
   clearly that wallet.json now holds the private key — the only claim on
   anything mined — and must be kept secret and backed up.

6. Start mining, politely, so I can keep using the machine:
   `.venv/bin/python -m pearl_metal_miner.miner --pool luckypool \
      --address <the address> --worker <this Mac's short name> \
      --intensity 60 --auto-intensity`
   Run it in a way that keeps running after you're done (e.g. tell me the
   command to run in my own terminal, or use a persistent session), and the
   Mac must stay plugged in and awake for it to mine.

7. Confirm it's actually working before declaring success:
   - the log shows a job arriving and a tiles/s rate within ~30 s;
   - explain to me what the log lines mean and that the FIRST accepted
     share can legitimately take from tens of minutes to hours — a quiet
     log is not a failure;
   - tell me how to stop it (Ctrl-C) and how to check the pool dashboard
     for my address.

Rules: never proceed past a failed self-test; don't change the job-shape
flags (--m/--n/--k/--rank/--rows/--cols) — the defaults are the fast path;
if the pool connection fails, try `--pool kryptex` before debugging deeper;
and if anything looks off, show me real output instead of summarising it
away.
```

That's the whole prompt. The agent ends with the miner running, the
self-test passed on your own machine, and your dashboard address to watch.
