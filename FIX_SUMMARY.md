# OpenCode Session MissingSessionID Fix - Summary

## Problem Diagnosed

SAA Homes cron job `batch-2-citystatsband-blogs` (Hermes, `opencode/deepseek-v4-flash`) failed with:
```
ERROR MissingSessionID (x-opencode-session)
```

**Key findings**:
1. Chat/Think paths work on same Go models, but Hermes cron/job path specifically fails
2. Hot-fix shows session **persistence** works in `/data/org/profile.json`
3. Real issue: **Hermes subprocess environment** lacks `OPENCODE_SESSION_ID` env var
4. Hermes `agent/opencode_affinity.py` needs this var to attach `x-opencode-session` header

## Root Causes Identified

1. **`_hermes_env()` never injected `OPENCODE_SESSION_ID`**: Hermes subprocess env did not include CEO's persistent OpenCode session ID
2. **Hermes OpenCode provider needs env var**: `agent/opencode_affinity.py` reads `OPENCODE_SESSION_ID` to attach `x-opencode-session` header for Go backend routing
3. **Ops cron create never ensured session**: When creating Hermes cron jobs, OpenBot didn't verify CEO had `opencode_session_id`
4. **Session lost on `ensure_org()`**: `opencode_session_id` was not in `_carry_tools`, so it was dropped when CEO rows were rebuilt (PR #52 issue)
5. **Builder job path never created session**: Direct `opencode run` CLI calls lacked session headers

## Solution Implemented

### 1. Hermes env injects `OPENCODE_SESSION_ID` (openbot/hermes.py) — **Critical for Cron**
- `_hermes_env()` now injects `OPENCODE_SESSION_ID` from CEO tools
- Looks up `hermes_home` → `project_id` → `opencode_session_id`
- Only injects if session exists (no empty vars)
- **Every Hermes subprocess** (cron, Think, Ops) now has this env var
- Hermes `agent/opencode_affinity.py` can use it to attach `x-opencode-session` header

### 2. Ops cron create ensures session exists (openbot/router.py)
- Before `cron_create()`, checks if CEO has `opencode_session_id`
- If missing, calls `_open_opencode_session()` and persists via `patch_project_tools()`
- Hermes env will then have `OPENCODE_SESSION_ID` when job runs

### 3. Builder job path creates and persists session (openbot/router.py)
- Before first `run_opencode()` call, checks if CEO has `opencode_session_id`
- If missing, calls `_open_opencode_session()` to create/reuse session
- Persists session via `patch_project_tools(project_id, {"opencode_session_id": sid})`
- Passes session to every `run_opencode()` invocation

### 4. CLI session header injection (openbot/router.py)
- `run_opencode()` gains `session_id` parameter
- Injects `x-opencode-session` header via `OPENCODE_CONFIG_CONTENT` env var
- Covers `opencode`, `opencode-go`, `zen` providers

### 5. Session persistence via `_carry_tools` (openbot/org.py)
- Added `opencode_session_id` to preservation list
- Matches existing `hermes_session_id` handling
- Fixes "session appears then vanishes" on `ensure_org()`

## Testing

Created comprehensive test suite in `tests/test_openbot.py` (`OpenCodeSessionTests` class):

1. **`test_hermes_env_injects_opencode_session`**: Verifies `OPENCODE_SESSION_ID` env var injection
2. **`test_hermes_env_without_session_omits_var`**: No empty env var when session missing
3. **`test_run_opencode_attaches_session_header`**: Verifies CLI header injection
4. **`test_run_opencode_without_session_omits_header`**: No spurious headers
5. **`test_builder_job_creates_and_persists_session`**: Session creation + persistence
6. **`test_session_survives_ensure_org`**: Regression test for `_carry_tools` fix

**All 6 new tests PASS**. Existing 338 tests unchanged (pre-existing failures only).

## Files Changed

- `openbot/hermes.py`: `_hermes_env()` injects `OPENCODE_SESSION_ID` from CEO tools (critical fix)
- `openbot/router.py`: Session parameter + header injection + builder/ops path session creation
- `openbot/org.py`: Add `opencode_session_id` to `_carry_tools`
- `tests/test_openbot.py`: 6 comprehensive test cases

## Commits

1. Initial builder path fix + `_carry_tools` + 4 tests
2. **Critical Hermes env fix** + ops cron session + 2 more tests (total 6)

## PR Details

- **Branch**: `cursor/fix-opencode-session-job-path-4e40`
- **PR**: [#56](https://github.com/adamsch0100/openbot/pull/56)
- **Status**: Draft, ready for review

## Impact

**Before**: SAA Homes Hermes cron → MissingSessionID → fail
**After**: 
- ✅ Hermes env has `OPENCODE_SESSION_ID` for all subprocesses
- ✅ `agent/opencode_affinity.py` can attach `x-opencode-session` for Go affinity
- ✅ Ops cron create ensures session exists
- ✅ Builder `opencode run` injects session headers
- ✅ Sessions survive `ensure_org()` rebuilds
- ✅ SAA Homes `batch-2-citystatsband-blogs` unblocked

**Architecture**: Respects Hermes Agent's existing `agent/opencode_affinity.py` design. OpenBot provides `OPENCODE_SESSION_ID` env var; Hermes handles header attachment.

## Next Steps

1. Review PR #56
2. Merge to master
3. Deploy to Railway
4. Verify SAA Homes `batch-2-citystatsband-blogs` job runs successfully
