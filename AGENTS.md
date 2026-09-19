# AGENTS.md

Guidelines for AI agents and contributors working in this repository.

## Project Scope & Objectives

`system-monitor` is a **Quickshell (QML) desktop widget for Wayland**
(Hyprland on this host; KDE Plasma compatible)
showing the memory/GPU picture existing monitors get wrong, plus an AI-spend sidecar:

1. **RAM used / available** (honest, cache-separated usage)
2. **zram stats** (logical stored → compressed → RAM held → ratio → savings)
3. **Real disk swap stats** (per-device, with net-rate-of-change — "is anything actually
   being written to disk, or is zram just compacting in RAM?")
4. **Top VRAM consumer** (combined total + the heaviest GPU-memory process)
5. **AI spend sidecar** (Cursor / OpenCode / OpenRouter / DeepSeek / OpenAI / Codex / Meta — never merge
   prepaid balance, plan quota %, and period spend into one fake total)

The **flagship feature is swap attribution**: distinguishing healthy in-RAM zram
compaction from real disk swap. Never merge these into one number.

Full implementation plan, data-source formulas, and milestones: **`PLAN.md`** — read it
before implementing anything. UI/UX decisions live there; don't redesign them silently.

## Non-Negotiable Safety Rules

1. **Run alongside Plasma, never as a shell replacement.** Launch via
   `quickshell -p ./shell` (manual) or a systemd *user* service. Never touch
   `plasmashell`, KWin config, or compositor settings.
2. **Strictly read-only system access.** Only read `/proc/*`, `/sys/*` and run
   read-only CLI queries from the allowlist: `nvidia-smi --query-*`, `lsblk -bP
   -o PATH,LABEL,FSTYPE,FSAVAIL,FSSIZE,FSUSED,MOUNTPOINTS,RM,TYPE,TRAN,PKNAME,KNAME`,
   `pgrep`, and `python3 -u shell/lib/ai-spend-collect.py` (the spend helper itself
   may read Cursor's local `state.vscdb` / OpenCode `auth.json` and issue GET/POST
   to the documented billing endpoints — never write those databases, never log
   tokens).
   **Never write to `/sys`** — no `reset`, `compact`, `mem_limit`, no zram
   reconfiguration. The zram `sysfs` attrs are config, not data.
3. **No root, no sudo, no privileged helpers.** Missing permissions ⇒ render "n/a"
   with a note; never block, retry-storm, or prompt.
4. **Never block the QML render loop.** All I/O async (`FileView` async reload,
   `Process` non-blocking). Parse failures yield `n/a`, not exceptions.
5. **Bounded polling.** Defaults: meminfo 1 s, swap/zram 2 s, `nvidia-smi` 5 s,
   AI spend 5 min (15 min while collapsed). Timers pause when the widget is hidden.
   All intervals configurable in `shell/Config.qml`.
6. **Kill switch must always work**: `systemctl --user stop qs-system-monitor`
   fully removes the widget with zero residue.

## Architecture Rules

- Directory layout is fixed by `PLAN.md` §3: `shell/{shell.qml,Config.qml,service/,widget/}`.
- **Collectors are `Singleton` QML files** in `service/` — each owns its data source
  and parsing. UI (`widget/`) never reads `/proc` or `/sys` directly; it renders
  snapshot state only.
- Parsing lives next to its source (`Zram.qml` owns `mm_stat` layout knowledge).
- Parsers must **tolerate layout drift**: variable field counts, missing files,
  missing devices. Unknown fields ignored; missing data → `n/a`.
- Position/prefs persistence via `PersistentProperties` (survives quickshell reloads).
- The current machine is NVIDIA (two RTX 3060s): `nvidia-smi` is the VRAM
  primary path and lists one row per GPU. The ring gauge is combined used/total;
  the NVIDIA VRAM card draws one bar per GPU. AMD fdinfo fallback stays in the
  design but is secondary. Validate pids against `/proc/<pid>/comm` every tick to
  guard PID-reuse races.
- Storage volumes come from the read-only `lsblk -bP` query. Filter to mounted
  filesystems, group them into internal/removable sections, and never add a
  mount path or device name to `Config.qml`.
- AI spend keys never live in `Config.qml` or the repo. Optional file:
  `$XDG_CONFIG_HOME/qs-system-monitor/ai-spend.json` (see
  `packaging/ai-spend.example.json`). Cursor/OpenCode/OpenRouter/Codex also fall back to
  credentials already on the machine.

## Known Environment Facts (verified 2026-08 Manjaro; re-verified 2026-09-19 Omarchy)

- Quickshell 0.3.1 (was 0.3.0); Hyprland Wayland (was KDE Plasma Wayland/KWin).
  Omarchy 4.0.4, kernel 7.2.5-3-omarchy.
- `/dev/zram0` priority 100 + `/swap/swapfile` priority 0, 32 GB each
  (was `/home/swapfile` priority 10 on Manjaro; both swap areas present).
- zswap **disabled**; zram has no writeback backing device (`backing_dev: none`).
- `/proc/vmstat` `pswpin/pswpout` count **all** swap I/O including zram — disk-only
  rate must subtract zram deltas (see `PLAN.md` §4.3 for the exact formula).
- If these facts change (zswap enabled, writeback configured, GPU vendor swap),
  re-check `PLAN.md` §4 formulas before trusting attribution math.

## Development Workflow

1. Branch from `master`: `feat/<name>`, `fix/<name>`, `docs/<name>`.
2. Conventional commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`).
3. Run the widget live while developing: `quickshell -p ./shell` (live-reloads on save).
4. Verify numbers against ground truth before trusting a collector:
   - RAM: `free -h`, `cat /proc/meminfo`
   - zram: `zramctl`, `cat /sys/block/zram0/mm_stat`
   - swap: `swapon --show`, `cat /proc/swaps`, `grep pswpin /proc/vmstat`
   - VRAM: `nvidia-smi`
   - AI spend: `python3 shell/lib/ai-spend-collect.py` (prints JSON; never log it if debugging keys)
5. Automated/parser checks: `node scripts/parse-test.mjs` (validates `shell/lib/Parse.js`
   against live `/proc`/`/sys` plus `ai-spend-collect.py --self-test` — run after
   touching any parser).
6. Headless collector check (prints live values, no window):
   `quickshell -p shell/collector-check.qml`.
7. Commit only verified-working states; test the systemd service after any change
   to launch code (`systemctl --user restart qs-system-monitor`).

## QML / Quickshell Conventions

- Follow Quickshell 0.3.x API (installed docs: `quickshell.outfoxxed.me/docs/v0.3.0`).
- Quickshell 0.3.0 gotchas (see `PLAN.md` §9.3 for details): `FileView.text` is a
  **function** (`text()`), singletons instantiate **lazily** on first reference, imports
  must not escape the config root, `PersistentProperties` persists only properties
  declared inside it.
- No hardcoded user paths or thresholds — all knobs in `shell/Config.qml`.
- Idempotent collectors: a quickshell live-reload must not duplicate timers or
  double-count state.
- Prefer clarity over cleverness; small focused components; document non-obvious math
  (especially §4.3 attribution) with comments citing the source files.

## Committing

- Check `git status` / `git diff` before every commit.
- Never commit secrets, credentials, `.env` files, or generated state.
- Update `README.md`/`AGENTS.md`/`PLAN.md` when scope, formulas, or workflow change.

## Getting Help

See `README.md` for run instructions and `PLAN.md` for the implementation roadmap.
