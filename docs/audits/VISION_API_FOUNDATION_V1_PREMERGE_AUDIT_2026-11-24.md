# API-01 premerge audit — 2026-11-24

## Reviewed baseline

PR #57, head `1f91ff3d9c19fc4d05a634a8adab8b0e62f844eb`, [CI run](https://github.com/autoklinika/Vision/actions/runs/45503049555), 12/12 PR workflows completed successfully. First failed run had invalid Vite configuration; repaired in `1f91ff3`.

| Baseline check | Observed result |
| --- | --- |
| Backend CI (Core, Runtime, Planner, ECU, Thermal, etc.) | 11/11 workflows passed |
| API unittest | 7 passed |
| TypeScript, ESLint, Vitest | Passed; 17 Vitest tests |
| Brand importer synthetic tests | 5 passed |
| DEV browser regression | 18 passed, 5 config-specific skips |
| Build browser regression | 14 passed, 9 config-specific skips |
| Actual Python HTTP through Vite DEV | 1 passed |
| Actual Python HTTP through build preview | 1 passed |
| npm audit | 0 reported vulnerabilities |

## Source review

- No edits to Core, Runtime, Planner, hardware adapters or existing backend workflows. The public API is an isolated loopback-only, read-only adapter. No filesystem routes, device access, write or motion commands.
- The closed API-01 schema cannot declare READY, supply a device component report or invent a measurement timestamp. Valid API replies explicitly say Core UNKNOWN and CORE_REPORT_NOT_CONNECTED. Invalid mode never fetches; demo stays separate; error/refresh replaces the previous report. The UI displays the last report rather than claiming continuous live connectivity.
- Original brand bytes are excluded; private original tests remain out of public CI. No real auth, session or protected data routes.
- Actual loopback integration tests cover a real HTTP reply, simulated transport loss by Playwright interception, and recovery of actual replies. They do not test physical network disconnection or restarting a deployed service.

## Findings and remediation

| ID | Finding | Remediation |
| --- | --- | --- |
| A01-R01 | Rejection before acquiring the body reader could leave the fetch active after the timer was cleared. | Abort in finally; cancel untouched response bodies, retaining the 4096-byte bound and timeout through streaming. Added three tests for early rejection, oversize without Content-Length, and stalled body after headers. |
| A01-R02 | `git diff --check` alone checks only uncommitted changes on a clean runner. | On PR compare actual base SHA to checkout HEAD; fetch history. For pushes check the head commit. Verify no tracked local-brand assets. |
| A01-L01 | Python HTTPServer uses an inactivity timeout, not an aggregate deadline; serial LAB transport is not hardened for production. | Document boundary and retain loopback-only scope. Production transport, authorization and TLS require separate review before any protected route or remote exposure. |

The fixes and tests are in this PR; **the corrected head requires a new successful CI run**. Baseline results above must not be treated as results for the amended code. ARM64 VENTUNO acceptance of this new API-01 code and private-original suite are separate. No hardware, system settings or AI Platform changes were performed during this GitHub audit.

**Disposition: draft; no merge or production deployment based on this report alone.**
