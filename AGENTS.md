# Vision — instructions for coding agents

## Mandatory project and host boundaries

Owner decision, 2026-11-24:

- Work on Vision locally **only on the Vision VENTUNO Q host**, using an isolated development worktree on its NVMe. Verify the selected device and storage before local coding, cloning, dependency installation, builds, or tests.
- GitHub is the canonical code repository; GitHub/Codex cloud development, pull requests, and CI remain permitted.
- **Never use AI Platform as a Vision development, build, or test host.** Do not clone this repository or launch a Vision Codex session there. It is a separate AI project. If VENTUNO is unavailable, report the blocker; do not silently fall back to AI Platform.
- Do not modify or restart operational services or access actuators for ordinary development. Respect separate hardware acceptance procedures.
- Keep work isolated and start new feature branches from current `origin/main`. Never push directly to main; merge only after the approved review/test process.
- **WebGUI is only a client of the entire Vision system.** Do not duplicate Core, Workflow, hardware access, or readiness decisions in the frontend.
- Never publish private calibration, real inspection data, logs, credentials, or unapproved branding assets. Keep project files and development caches on the intended NVMe, not eMMC.

See [development rules](docs/process/DEVELOPMENT.md), [repository hygiene](docs/process/REPOSITORY_HYGIENE_V1.md), and [ADR-VISION-WEBGUI-001](docs/decisions/ADR_VISION_WEBGUI_CLIENT_ONLY_2026-11-24.md).
