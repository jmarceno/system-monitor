# Implementation Plan — `system-monitor` (Python / Qt desktop app for Wayland)

> **Status: implemented (M0–M6) and ported from Quickshell to PySide6.**
> The widget matches `mock/mockup.png` and runs as a systemd user service.
> Deviations from this plan are documented in §9.

Target environment (verified on this machine):

| Fact | Value |
|---|---|
| Desktop | Hyprland Wayland (was KDE Plasma Wayland/KWin); Omarchy 4.0.4 |
| Runtime | Python 3.12+ / PySide6 6.x (was Quickshell 0.3.1) |
| Kernel | 7.2.5-3-omarchy (was 6.12.104-1-MANJARO) |
| GPU | two NVIDIA RTX 3060 (`nvidia-smi` lists one row per GPU; gauge sums them) |
| zram | `/dev/zram0`, priority 100, world-readable `mm_stat`/`stat`/`io_stat` |
| Disk swap | `/swap/swapfile` (32 GB, priority 0; was `/home/swapfile` prio 10) |
| zswap | disabled (`/proc/meminfo` → `Zswapped: 0 kB`) |
| zram writeback | not configured (`backing_dev: none`) |

---

## 1. Problem statement

Existing system monitors (plasma-systemmonitor, btop, conky, KDE widgets) report a single
combined "swap used" number that mixes:

- **zram compaction** (anonymous pages compressed in RAM — cheap, desirable, *not* disk I/O), and
- **real disk swap** (pages written to `/home/swapfile` — slow, usually signals memory pressure).

This conflates healthy zram compaction with harmful disk swapping and leads to wrong
workload/optimization decisions. Additionally:

- RAM "used" shown by most tools doesn't distinguish reclaimable cache, so the number looks scarier than reality.
- No mainstream monitor lists **top VRAM consumers per process** (critical when local LLMs share the GPU with desktop apps).

## 2. Product scope

A **single desktop application** (not a bar, not a shell widget, not a shell replacement) that shows:

1. **RAM used / available** with an honest breakdown (used, available, cache/reclaimable, SwapCached).
2. **zram stats**: logical data stored, compressed size, compression ratio, actual RAM consumed, savings.
3. **Real disk swap stats**: per-device size/used, *net rate of change* per device (is anything actually being written to the NVMe?), plus system-wide swap-in/out throughput attributed to zram vs disk.
4. **Top VRAM consumer**: combined VRAM used + the single heaviest process by GPU memory.
5. **Mounted storage sidecar**: free/used/total space for the same mounted internal
   and removable filesystem devices users see in Dolphin.
6. **AI spend sidecar** (right of storage): Cursor plan meters (Cursor models /
   Other models %), OpenCode Go quota %, OpenRouter remaining credits, DeepSeek
   remaining credits (granted + topped-up split), OpenAI
   month-to-date cost when an admin key is configured. Meta stays `n/a` until
   it exposes an account-wide API. Do not sum mixed units (dollars vs quota %)
   into one total.

**Explicitly out of scope (for now):** CPU/network graphs, theming beyond a sane dark card look,
audio, battery, per-core stats, replacing any Plasma component.

**Safety contract (non-negotiable):**

- Run as an *ordinary user process alongside* the desktop. Never replace the compositor.
- **Read-only**: only read `/proc`, `/sys`, run read-only CLI queries (`nvidia-smi`
  query flags, `lsblk`, the AI-spend python helper). Never write to `/sys` (no `reset`,
  `compact`, `mem_limit`, no zram reconfiguration).
- **No root required.** If a data source is unreadable, degrade gracefully to "n/a" with a visible note — never block, never crash, never spawn sudo prompts.
- Bounded polling: total widget CPU budget ~<1% idle; all timers pausable; full kill switch = stop the service.

## 3. Architecture

```
sysmon/
├── __main__.py              # python -m sysmon  (window or --check)
├── config.py                # user-tunable constants (intervals, thresholds, toggles)
├── snapshot.py              # QObject aggregating all collectors
├── parse.py                 # side-effect-free /proc /sys lsblk nvidia-smi parsers
├── format.py                # bytes / rates / °C / USD
├── collectors/
│   ├── meminfo.py           # /proc/meminfo  → RAM + SwapCached + zswap fields
│   ├── zram.py              # /sys/block/zram0/{mm_stat,stat} + /proc/swaps zram row
│   ├── swap_disk.py         # /proc/swaps (disk rows) + /proc/vmstat rates + attribution
│   ├── vram.py              # nvidia-smi queries (+ fdinfo fallback path for AMD machines)
│   ├── storage.py           # lsblk -bP → mounted device/free-space snapshots
│   ├── storage_io.py        # /proc/diskstats → per-mounted-device I/O rates/history
│   ├── ai_spend.py          # python helper → Cursor / OpenCode / OpenRouter / DeepSeek / OpenAI / Meta
│   └── cpu.py               # /proc/stat + cpuinfo MHz + hwmon °C
├── ui/
│   ├── window.py            # frameless QWidget, drag handling, persistence
│   ├── cards.py
│   ├── gauges.py
│   └── sidecars.py
└── lib/
    └── ai_spend_collect.py  # read-only billing snapshot (HTTP + local creds)
```

Design principles:

- **Every collector is a `QObject`** exposing read-only properties (`mem`, `zram`, `swap`, `vram`). UI never touches `/proc` directly — only the snapshot state.
- Parsing lives in `sysmon/parse.py`; derived attribution math lives in `SwapDiskCollector`.
- UI is dumb: renders the snapshot state, no I/O.
- Config is a single dataclass so intervals/limits can be tuned in one place.

## 4. Data sources & formulas (the hard part — done carefully)

### 4.1 RAM (`collectors/meminfo.py`)

Source: `/proc/meminfo` (kB fields). Poll every **1 s** via `QTimer`.
(**not** inotify — procfs doesn't fire inotify reliably).

Derived properties:

- `used` = `MemTotal - MemAvailable` (KDE-convention "true usage")
- `available` = `MemAvailable`
- `cacheReclaimable` = `Cached + SReclaimable - Shmem`
- `swapCached` = `SwapCached` (pages that left RAM but still have a swap copy — relevant to swap-in cost)
- `zswapUsed` = `Zswap`, `zswapCompressed` = `Zswapped` (0 here, but read them so the widget stays correct if zswap is ever enabled)

### 4.2 zram (`collectors/zram.py`)

Sources:

- `/sys/block/zram0/mm_stat` — fields (verified present on this kernel):
  `orig_data_size, compr_data_size, mem_used_total, mem_limit, mem_used_max, same_pages, huge_pages, huge_pages_failed, huge_pages_alloc` (tolerate both 6-field old and 9-field new layouts).
- `/proc/swaps` row where filename starts with `/dev/zram` — authoritative *swap-side* usage (`Used` kB).
- `/sys/block/zram0/stat` (diskstat layout) and `io_stat` — for I/O-rate deltas.

Derived:

- `logicalStored` = mm_stat[0]
- `compressed` = mm_stat[1]
- `ramHeld` = mm_stat[2] (`mem_used_total` — actual RAM consumed holding zram)
- `compressionRatio` = logicalStored / compressed
- `ramSaved` = logicalStored − ramHeld
- `hugePages` counts (regression signal when ratio degrades)

### 4.3 Disk swap + attribution (`collectors/swap_disk.py`) — the core fix

Sources:

- `/proc/swaps`: **split rows into `zram` devices vs `disk` devices** (filename prefix `/dev/zram`).
  Each area: size, used, priority.
- `/proc/vmstat`: `pswpin`, `pswpout` (cumulative, pages; **includes zram traffic**), `zswpin/zswpout` (zswap, 0 here).
- zram I/O: `/sys/block/zram0/stat` write/read sectors (4 KiB zram sectors) deltas.

Rate attribution per sampling window (default 2 s):

```
swapOutTotalPagesΔ  = pswpout_now - pswpout_prev
zramWritePagesΔ     = (zram stat write_sectorsΔ) / 8   // 8 sectors per 4 KiB page
diskSwapOutPagesΔ   = max(0, swapOutTotalPagesΔ - zramWritePagesΔ)
```

Plus a **net-balance view per device** (authoritative, immune to attribution edge cases):

```
zramUsedΔ  = /proc/swaps zram row UsedΔ      → positive: compaction happening
diskUsedΔ  = /proc/swaps disk rows UsedΔ     → positive: REAL disk swap happening
```

UI verdict states (this is what the user actually needs):

- `zram-only`: zram Used rising, disk Used flat → "compacting in RAM ✔"
- `disk-pressure`: disk Used rising or `diskSwapOut` rate > 0 → "REAL disk swap ✖ kB/s"
- `draining`: values shrinking → "swap being read back"
- `idle`: nothing changing

### 4.4 VRAM consumers (`collectors/vram.py`)

Primary (NVIDIA, this machine): `Process.exec` of two read-only queries every **5 s**:

- `nvidia-smi --query-gpu=memory.used,memory.total,temperature.gpu,index,name --format=csv,noheader,nounits`
  → one CSV line per GPU. The ring gauge and card header use the **sum** of
  `memory.used` / `memory.total` across all lines; the VRAM card draws **one bar
  per GPU**. The ring stacks one die temp per GPU (same order as the bars);
  they are never merged into a single hottest reading.
- `nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv,noheader,nounits`
  → for each pid: read `/proc/<pid>/comm` to get the short friendly name; **validate pid is alive and comm matches the reported basename** (guards against PID reuse races; drop stale entries instead of mislabeling).

Fallback paths (keep for AMD/other machines / future portability):

- Generic: scan `/proc/*/fdinfo/*` for `drm-` fields (`vram`, `gtt`, `dma-buf`) — works with amdgpu fdinfo.
- Graceful degrade when `nvidia-smi` missing: hide card, log once.

### 4.5 Mounted storage (`collectors/storage.py`)

Source: the allowlisted read-only query:

```
lsblk -bP -o PATH,LABEL,FSTYPE,FSAVAIL,FSSIZE,FSUSED,MOUNTPOINTS,RM,TYPE,TRAN,PKNAME,KNAME
```

The parser keeps mounted non-swap filesystems, uses `LABEL` with a mountpoint
fallback for the display name, and reports byte-accurate `FSAVAIL`, `FSSIZE` and
`FSUSED`. Devices are marked removable when `RM=1` or the transport is USB/MMC/
FireWire; the latter covers USB enclosures that expose `RM=0`. Duplicate RAID-tree
rows are deduplicated by device path, and `/boot`/EFI implementation partitions
are omitted from the Dolphin-style user storage list. Missing `lsblk` or an
unreadable query produces an unavailable sidecar rather than a retry storm.

### 4.6 Per-device storage I/O (`collectors/storage_io.py`)

Source: `/proc/diskstats`, polled every **2 s**. The collector matches each
mounted volume's `KNAME` from `lsblk` to its own cumulative read/write sector
counters, converts 512-byte sectors to kB/s over the sampling interval, and
keeps a bounded 40-point total-throughput history for the sidecar sparkline.
Parent disks are not summed with their partitions, so each displayed filesystem
shows the activity of the device that actually backs its mountpoint. A new or
temporarily unavailable device starts with zero rates and fills its history after
the next complete sample pair.

Nuance shown in UI: per-process sum ≠ GPU total (driver-reserved + graphics overhead) — show total separately, never fake a "sum" as total.

## 5. UI & interaction

### 5.1 Window model

- Ordinary resizable `QWidget` with the compositor's title bar, so it tiles and focuses like any other desktop application.
- One client area. Sections share edges in a grid (`spacing` 0). There are no floating cards, side panels, or a collapsed pill.
- Geometry is clamped to the current screen's available area. Lists scroll inside their cell so a short window cannot push a section off screen or collapse it to nothing.

### 5.2 Placement persistence

- `~/.local/state/system-monitor/window-state.json` stores `posX`, `posY`, `width`, `height`, and screen name. Older `collapsed` / `pinned` keys are ignored.
- `packaging/hyprland-windowrule.conf` no longer forces float, pin, or noborder. Those rules made the Qt port keep behaving like the old Quickshell widget.

### 5.3 Layout

One grid that fills the window:

```
┌ CPU ┬ GPU VRAM ┬ RAM ┬ Swap (disk only, 0 when zram is the only device) ┐
├ Memory ┴──────────┼ zram (orig / compr / mem / compaction rate) ─────────┤
├ Disk swap ────────┼ VRAM (one bar per GPU, top process) ─────────────────┤
├ Storage (scroll) ─┼ AI spend (scroll) ───────────────────────────────────┤
└───────────────────┴──────────────────────────────────────────────────────┘
```

The top row is four equal gauges (CPU, GPU VRAM, RAM, disk swap) at content
height. Below that, two columns size independently: memory and disk swap stay
as tall as their content, and storage takes the remaining height. zram and
VRAM do the same on the right, with AI spend taking the rest. Storage and AI
spend scroll inside their cells. Storage contains separate `Internal drives` and `Removable
drives` sections and is driven entirely by the latest `lsblk` snapshot; no device
names or mount paths are stored in configuration.

AI spend lists one card per provider. Remaining credits, plan quota %, and period
spend stay separate numbers. Keys are never in `sysmon/config.py` — see
`packaging/ai-spend.example.json`.

- The swap gauge and the disk-swap section count **disk swap only**. zram is never
  included. With no disk swap device the gauge stays at 0. zram compaction rate
  stays on the zram section.
- Each storage entry adds its own read/write rates and a compact I/O sparkline below
  the mountpoint.

## 6. Precautions ("do not break things")

1. **No shell takeover**: launch as `python -m sysmon` in a systemd *user* service; compositor untouched. Kill switch: `systemctl --user stop system-monitor`.
2. **Read-only I/O only.** A grep-guarded review rule in AGENTS.md: spawned commands must be from an allowlist (`nvidia-smi --query-*`, the exact `lsblk -bP` storage query). No writes outside our own state file. The spend helper must not write Cursor/`opencode` credential stores.
3. **Never block the Qt event loop.** `/proc` reads are tiny; `nvidia-smi`/`lsblk` use `QProcess`; AI spend uses a worker `QThread`. Parse failures produce `n/a`, not exceptions.
4. **Poll budget**: 1 s meminfo (tiny file), 2 s swap/zram and per-device diskstats,
   5 s `nvidia-smi`, 5 s `lsblk` snapshots, and 5 min AI-spend. Timers stop when
   the window is not visible.
5. **Permission degradation**: if `mm_stat` unreadable (some setups restrict it), still show `/proc/swaps` zram Used with an "advanced stats unavailable" note. Never retry-storm.
6. **Process races**: VRAM pid list re-validated against `/proc/<pid>/comm` every tick; dead pids dropped.
7. **Layout edge cases**: mm_stat field-count variations; missing zram device (`/sys/block/zram*` glob empty → zram card renders "no zram configured"); multiple swap files (list each).
8. **Restart safety**: collectors parent their `QTimer`s; a process restart must not leave a stray window (kill switch stops the user unit).
9. **Memory of the monitor itself**: keep snapshots tiny; per-device I/O histories
   are capped at 40 points and are discarded when a device disappears.

## 7. Milestones

### M0 — Skeleton boots (no data)
- `sysmon/ui/window.py` floating card renders; drag strip moves it; position persists across restart.
- systemd user unit installs; widget appears after login; `systemctl --user stop` kills it cleanly.
- **Accept:** drag to any position → restart → position retained; `journalctl --user -u system-monitor` clean.

### M1 — RAM + zram cards
- MemInfo + Zram collectors with the formulas above; cards render live values that match `free -h` and `zramctl` outputs within rounding.
- **Accept:** `used` ≈ KDE convention; compression ratio matches `zramctl`'s ALGO/RATIO; unit tests via a tiny `qs` console check script (documented in AGENTS.md).

### M2 — Disk swap + attribution (the flagship feature)
- SwapDisk collector with per-device Used deltas + vmstat/zram attribution; verdict states drive card color.
- **Accept:** while running only a browser + editor, card shows `zram-only / idle`; stress test (`stress-ng --vm`) or an intentional `chrt` memory hog shows `disk-pressure` only when the NVMe is truly being written (verify against `/proc/diskstats` manually once).

### M3 — VRAM card
- nvidia-smi queries + pid validation + the single heaviest process; graceful hide on missing binary.
- **Accept:** launching/stopping a CUDA process updates the list within one tick; desktop apps (kwin, brave gpu-proc) appear with friendly names.

### M4 — Polish
- Collapse/pill modes, `sysmon/config.py` knobs (intervals, thresholds, top-N), docs, screenshot, final README/AGENTS alignment.

### M5 — Dynamic storage sidecar
- `StorageCollector` discovers mounted filesystem devices with the allowlisted `lsblk`
  query, reports free/used/total bytes, and separates internal from removable media.
- `StorageSidecar` is an always-open column to the right of the main card, same height.
- **Accept:** current mounted devices appear without configuration edits, USB media
  is grouped under `Removable drives`, and a fresh query reflects mount/unmount changes.

### M6 — AI spend sidecar
- `AiSpendCollector` runs `sysmon/lib/ai_spend_collect.py` every 5 min on a worker
  thread and publishes a provider snapshot. `AiSpendSidecar` is the always-open column
  to the right of storage. Cursor uses the local session (undocumented dashboard RPC); OpenRouter
  uses the official credits API; DeepSeek uses the official `GET /user/balance`
  (remaining credits with granted + topped-up split, USD preferred); OpenCode Go
  uses `/zen/go/v1/usage`; OpenAI uses
  the official organization costs API when an admin key is present; Codex uses
  `GET chatgpt.com/backend-api/wham/usage` via `~/.codex/auth.json`; Meta renders
  `n/a`.
- **Accept:** Cursor / OpenCode Go / OpenRouter / DeepSeek / Codex show live figures from local
  logins; OpenAI shows month-to-date when `openaiAdminKey` is in the secrets file;
  no tokens appear in logs or `sysmon/config.py`.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Qt / Wayland positioning | Normal toplevel. The compositor owns the frame. Saved geometry is clamped to the screen. |
| `nvidia-smi` spawn cost every 5 s | Single combined query; increase interval in Config; only re-spawn when the previous `QProcess` has exited. |
| vmstat attribution edge cases (e.g., future zram writeback) | `backing_dev` is read and, if non-`none`, attribution switches to `bd_stat` deltas; net-balance per-device view stays authoritative. |
| Driver/kernel updates change file layouts | Parsers tolerate field-count drift; unknown fields ignored; missing → n/a. |
| PySide6 / Qt Wayland drift | Pin docs to installed version; smoke-run `--check` on every update. |

## 9. Implementation notes & deviations (post-implementation record)

### 9.1 Window model: normal desktop window

The original Quickshell build was a layer-shell widget. The first PySide6 port
kept that shape: a frameless, pinned, non-focusing card with separate side
panels. That is gone. The process is a normal resizable window. The compositor
draws the title bar and decides tiling. Position and size persist in
`window-state.json`.

### 9.2 Scope additions from the mockup

The mockup added three things that were "out of scope" in §2. They are implemented:

- **Top summary** with larger ring gauges arranged as CPU/GPU then RAM/Swap —
  `CpuCollector`, `VramCollector`, `MemInfoCollector` and `SwapDiskCollector`;
  per-device disk **I/O** is in the storage section via
  `StorageIoCollector` (`/proc/diskstats` matched by `lsblk` `KNAME`);
- **Window chrome** is the compositor's. There is no in-app pin, drag strip, or pill.

### 9.3 Python / Qt notes

- `nvidia-smi` and `lsblk` run through `QProcess` so the UI thread never waits on them.
- AI spend runs `collect()` on a `QThread`; credentials never enter the UI layer.
- Window state is a JSON file under `$XDG_STATE_HOME/system-monitor/` (debounced 400 ms).
- Headless verification: `.venv/bin/python -m sysmon --check`.

### 9.4 Verification performed (2026-08-31, Quickshell era; re-run after the PySide6 port)

- `scripts/parse-test.py` — assertions against live `/proc`, `/sys` and synthetic
  nvidia-smi output.
- `python -m sysmon --check` — live values match `free -h`, `/proc/swaps`, `mm_stat` ratio
  (≈ `zramctl`), and a live GPU process appears with a friendly name.

### 9.5 Single grid

Storage and AI spend are cells in the same grid as memory, zram, disk swap, and
VRAM. They are not separate panels and they are not stacked under a fixed-width
card. Extra rows scroll inside the cell. Older `storageExpanded` /
`aiSpendExpanded` keys in `window-state.json` are ignored.

### 9.7 Disk swap is not zram

`/proc/meminfo` `SwapTotal` and `/proc/swaps` include zram. The swap gauge,
`SwapDiskCollector.used_pct`, and the disk-swap section do not. They use only
rows whose filename is not `/dev/zram*`. On a machine whose only swap device is
zram, disk size, disk used, and the gauge stay at 0. zram orig/compr/mem and
the compaction rate stay on the zram section. If a disk swap file is added
later, it shows up on its own and does not get added into the zram numbers.

### 9.6 AI spend sidecar (M6)

- Collector: `sysmon/lib/ai_spend_collect.py` imported in-process on a worker thread.
  The UI only receives the JSON snapshot; it never sees tokens.
- Cursor **Pro meters** are `autoPercentUsed` (Cursor models) and `apiPercentUsed`
  (Other models). Do not treat `includedSpend`/`totalSpend` cents or `displayMessage`
  as billed usage — they disagree with the Plan & Usage page. OpenRouter
  `remaining = total_credits - total_usage`. DeepSeek `GET /user/balance`
  reports per-currency `total_balance` (decimal strings) with `granted_balance` /
  `topped_up_balance` split; USD is preferred when several currencies are present
  and there is no quota total to percent against.
  OpenCode Go percents are **used** (matching the dashboard). OpenAI sums `results[].amount.value`
  for the current UTC month. Codex 5-hour / weekly percents come from
  `chatgpt.com/backend-api/wham/usage` (ChatGPT OAuth in `~/.codex/auth.json`).
  Cloudflare returns 1010 unless the helper sends a User-Agent.
- Cursor and Codex access-token refresh (on 401) is in-memory only — we never write
  `state.vscdb` or `~/.codex/auth.json`.
- Optional secrets file: `$XDG_CONFIG_HOME/qs-system-monitor/ai-spend.json` for the
  OpenAI organization admin key. OpenRouter/OpenCode fall back to
  `~/.local/share/opencode/auth.json`; Cursor and Codex fall back to their signed-in
  app databases.
