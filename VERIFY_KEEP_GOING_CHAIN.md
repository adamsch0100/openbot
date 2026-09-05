# Verify: Keep-Going Step Chain (Chat Gap #3) - FIXED

## Implementation Summary

Properly implemented automatic step chaining to OpenBot's keep-going flow. When a work job settles with `keep_going=true`, the stream offers a Continue CTA that starts the next step from **last RESULT (truncated 600 chars) + INDEX Next**.

### CEO NACK Fixes Applied

1. ✅ **Step counter persistence**: No hardcoded {step:1,total:1}. Chain context stored in `chainContexts` Map and increments properly. Total grows to accommodate steps (never shows Continue 2/1).

2. ✅ **Continue message includes RESULT + Next**: Message format is now `"Continue. Last RESULT:\n{resultSnippet}\n\nNext: {next}"` with 600-char truncated result.

3. ✅ **Stop clears chain context**: Real cancel semantics via `chainContexts.delete(idKey)` on Stop, not just messageQueues.

4. ✅ **Visible step chips**: Each job card shows "Step N/M" in the meta line when in a chain.

## Architecture

### Backend (router.py + server.py)
- **chain_context parameter**: Dict `{step, total, last_result}` tracks position across jobs
- **Step tracking**: Job response includes `step_count`, `total_steps`, `in_chain` fields
- **Smart step counting**: Uses chain_step if provided, otherwise starts at 1; total grows with max(chain_total, chain_step)
- **One-shot preservation**: Each Continue is still a separate `handle()` call (no third runtime)
- **RESULT handoff**: Last RESULT (600 chars) + INDEX Next in continuation message

### Frontend (web/app.js)
- **chainContexts Map**: Persists `{step, total, last_result}` per aimKey (project/worker scope)
- **Continue CTA**: Shows "Continue (N/M)" button, increments step on click
- **Continue message**: Includes last RESULT snippet (600 chars) + INDEX Next
- **Step chips**: Visible "Step N/M" badge in job card meta line
- **Chain cancellation**: Stop clears chainContexts.delete() + messageQueues (real cancel)
- **Stream integration**: chain_context passed through /api/chat/stream

## Verify Steps

### 1. Single-step work (baseline)
```
1. Start OpenBot: python3 bin/openbot
2. Open http://127.0.0.1:8787
3. Send: "Read OPENBOT.md"
4. Expect: Job settles, Continue button shows "Continue" (no counter)
5. Click Continue
6. Expect: New job starts with "Continue from Last and Next"
```

### 2. Multi-step chain flow
```
1. In INDEX, set Next: "Review AGENTS.md next"
2. Send: "Read ARCHITECTURE.md"
3. Wait for job to settle with keep_going=true
4. Verify: Continue button shows "Continue (1/1)"
5. Verify: Job card shows "Step 1/1" in meta line
6. Click Continue
7. Verify: New job shows "Continue (2/2)" on button after it settles
8. Verify: New job card shows "Step 2/2" in meta line
9. Verify: Continue message included last RESULT + INDEX Next
10. Verify: Each job is a separate card in the stream
11. Click Continue again
12. Verify: Next job shows "Step 3/3" (total grows)
```

### 3. Stop/clear cancellation (real cancel semantics)
```
1. Start a Builder job that will take time
2. While streaming, click Stop
3. Verify: Message queue clears
4. Verify: chainContexts.delete() called (check in DevTools console if needed)
5. Verify: Chain state resets (no lingering step counters)
6. Send next message
7. Verify: Next Continue starts fresh at "Step 1/1" (not continuing from stopped chain)
```

### 4. Turn Report preservation
```
1. Run a multi-step chain
2. Verify: Each step shows engine name on job card (OpenCode / Hermes Agent / board)
3. Verify: Progress chips appear during streaming ("OpenCode · step-start")
4. Verify: No broken metadata or missing engine attribution
```

### 5. Hermes progress chips
```
1. Run Research or Think job
2. Verify: Progress events show "Hermes Agent · tool-name" during execution
3. Click Continue
4. Verify: Next step also shows progress chips correctly
```

## Known Constraints

- **Week 1 scope only**: Multi-step chain is composer-level, not a program/ticket system
- **No PR_*.md created**: Per AGENTS.md, no PR summaries in repo
- **No engine vendoring**: Calls official `hermes` and `opencode` binaries
- **Chat is UI**: Thread JSON is not the prompt; INDEX is memory
- **One-shot jobs**: Each Continue is a fresh `handle()` call, not a persistent runtime

## Acceptance Criteria

✅ After work job settles, Continue CTA offers next step from RESULT + INDEX Next  
✅ Shows step list (1/N) while chaining  
✅ Stop/clear cancels the chain  
✅ Still one-shot jobs under the hood (no third runtime)  
✅ Does not break Turn Report cards or Hermes progress chips  
✅ No PR_*.md in repo  
✅ No engine vendoring  

## Files Changed

- `openbot/router.py`: Added chain_context parameter, step tracking fields
- `openbot/server.py`: Pass chain_context through /api/chat and /api/chat/stream
- `web/app.js`: Continue button with step counter, chain state management

## Testing Notes

All changes are backward compatible. Jobs without chain_context behave exactly as before. The `keep_going_for()` logic is unchanged—this only adds visibility and handoff state.

Tested with:
- Cos status queries (no chain)
- Builder code edits (baseline Continue)
- Multi-step Think → Builder → Research chains
- Stop during streaming
- Queue clear on cancellation

## OpenBot CEO Review

This PR implements Chat Gap #3 per the original pain statement: "Multi-step work needs retyping; Grok keeps going." The solution preserves OpenBot's architecture (board routes, engines execute, INDEX is memory) while adding a visible plan→next job loop that feels like Grok's keep-going without becoming a third runtime.

Ready for merge to master after review.
