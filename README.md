# System Monitor (Quickshell · KDE Plasma)

A free-floating desktop widget for KDE Plasma (Wayland) built with
[Quickshell](https://quickshell.outfoxxed.me/) that shows the memory truth other
monitors hide.

## Why this exists

Every mainstream monitor conflates **zram compaction** (anonymous pages compressed
in RAM — cheap and healthy) with **real disk swap** (pages written to disk — slow
and a memory-pressure warning). A single combined "swap used" bar makes healthy
zram activity look like disk thrashing and leads to wrong workload and
optimization decisions.

This widget splits them, honestly:

- **RAM used / available** — real usage, with cache/reclaimable separated so the number isn't inflated.
- **zram stats** — logical data stored → compressed size → compression ratio → actual RAM held → RAM saved.
- **Real disk swap stats** — per-device size/used and the *net rate of change*: if the disk swap file isn't growing, **nothing is being written to disk**, period.
- **Top VRAM consumers** — total GPU memory plus the top processes by VRAM, with friendly process names (crucial when local LLMs share the GPU with desktop apps).

## Design goals

1. **Truthful attribution** — never reports "swapping to disk" unless disk swap is actually changing.
2. **Non-invasive** — runs alongside `plasmashell` as a plain user process; never replaces any Plasma component; read-only access to `/proc` and `/sys`; no root.
3. **Practical & readable** — one line per metric, color-coded verdicts (✔ in-RAM compaction, ✖ real disk swap).
4. **Placeable** — draggable anywhere on any monitor; position persists across restarts.

## Current state

**Implemented and running** (M0–M4 of [PLAN.md](./PLAN.md)). The UI matches
[mock/mockup.png](./mock/mockup.png): header with minimize/pin/close controls, a top strip
with CPU/RAM/Swap/VRAM gauges and a disk-I/O sparkline, the Memory card, the highlighted
**Swap Attribution** card, the zram card (with zswap/writeback chips), the NVIDIA VRAM top-
consumers card, and the safety-posture footer chips.

Behavior:

- **Drag the header** to place it anywhere; position persists across restarts.
- Unpinned it lives **below** your windows (desktop furniture); **📌 pin** raises it above
  everything. **−** collapses to a small pill; **✕** quits the instance.

## Running it

```bash
# One-time install + enable + start (systemd user service)
./scripts/install.sh --start

# Kill switch
systemctl --user stop qs-system-monitor

# Run manually from the project root (dev mode, live-reloads on save)
quickshell -p ./shell
```

Requirements: Quickshell ≥ 0.3.0, KDE Plasma on Wayland, Linux ≥ 6.x with zram
(optional — card degrades gracefully without it). NVIDIA needs `nvidia-smi` for
the VRAM card (AMD fallback via fdinfo is planned in the code path).

## Safety posture

- **Read-only**: reads `/proc/meminfo`, `/proc/swaps`, `/proc/vmstat`,
  `/sys/block/zram0/*`, and runs read-only `nvidia-smi --query-*` commands. Never
  writes to `/sys`, never touches zram configuration.
- **No root**, no privileged helpers, no sudo prompts.
- **Kill switch** is a single systemd stop; Plasma is untouched by design.

## Documentation

| File | Purpose |
|---|---|
| [PLAN.md](./PLAN.md) | Implementation plan, data-source formulas, milestones, risks, implementation record |
| [AGENTS.md](./AGENTS.md) | Scope, architecture rules and conventions for agents/contributors |
| [mock/mockup.png](./mock/mockup.png) | UI mockup the implementation follows |

## License

TBD
