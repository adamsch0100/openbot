# OpenCode Session MissingSessionID Fix - Summary

## Problem Diagnosed

SAA Homes cron job `batch-2-citystatsband-blogs` (Hermes, `opencode/deepseek-v4-flash`) failed with:
```
ERROR MissingSessionID (x-opencode-session)
```

**Key finding**: Chat/Think paths work on same Go models, but job/cron path specifically fails.

## Root Causes Identified

1. **`run_opencode()` never attaches session**: The CLI subprocess path (`opencode run`) does not inject the `x-opencode-session` header required by OpenCode Go models for backend routing
2. **Builder job path never creates session**: Unlike Chat/Think (which use `opencode web` HTTP API with session management), builder jobs never call `_open_opencode_session()` or persist `opencode_session_id`
3. **Session lost on `ensure_org()`**: `opencode_session_id` was not in `_carry_tools`, so it was dropped when CEO rows were rebuilt
4. **OpenCode Go requirement**: Models like `deepseek-v4-flash` require `x-opencode-session` for stable routing to backends

## Solution Implemented

### 1. Modified `run_opencode()` to inject session header (openbot/router.py)
- Added `session_id` parameter
- Build config overlay via `OPENCODE_CONFIG_CONTENT` env var
- Inject `x-opencode-session` header for `opencode`, `opencode-go`, `zen` providers
- Based on OpenCode CLI source showing it accepts provider config via env var

### 2. Builder job path now creates and persists session (openbot/router.py)
- Before first `run_opencode()` call, check if CEO has `opencode_session_id`
- If missing, call `_open_opencode_session()` to create/reuse session
- Persist session via `patch_project_tools(project_id, {"opencode_session_id": sid})`
- Pass session to every `run_opencode()` invocation

### 3. Added `opencode_session_id` to `_carry_tools` (openbot/org.py)
- Preserves `opencode_session_id` when `ensure_org()` rebuilds CEO rows
- Matches existing `hermes_session_id` handling
- Fixes the "session appears then vanishes" issue

## Testing

Created comprehensive test suite in `tests/test_openbot.py`:

1. **`test_run_opencode_attaches_session_header`**: Verifies header injection
2. **`test_run_opencode_without_session_omits_header`**: No spurious headers
3. **`test_builder_job_creates_and_persists_session`**: Session creation + persistence
4. **`test_session_survives_ensure_org`**: Regression test for `_carry_tools` fix

**All 4 new tests PASS**. Existing 338 tests unchanged (pre-existing failures only).

## Files Changed

- `openbot/router.py`: Session parameter + header injection + builder path session creation
- `openbot/org.py`: Add `opencode_session_id` to `_carry_tools`
- `tests/test_openbot.py`: 4 comprehensive test cases

## PR Details

- **Branch**: `cursor/fix-opencode-session-job-path-4e40`
- **PR**: [#56](https://github.com/adamsch0100/openbot/pull/56)
- **Status**: Draft, ready for review

## Impact

**Before**: SAA Homes cron jobs → MissingSessionID → fail
**After**: ✅ Sessions created, persisted, attached → jobs work

**Minimal surgical fix**: No Chat/Think changes, no Hermes changes, no model chain modifications.

## Next Steps

1. Review PR #56
2. Merge to master
3. Deploy to Railway
4. Verify SAA Homes `batch-2-citystatsband-blogs` job runs successfully
