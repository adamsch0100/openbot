# PR #3: Sidebar Agent OS - Manual Verification Checklist

## Overview
Implements ROADMAP PR #3: Sidebar feels like named teammates in <3s — not a settings tree.

## Visual Changes Summary

### Avatars & Initials
- **Chief of Staff**: Shows "CS" initials in circular avatar
- **Each CEO**: Shows 2-letter initials from name (e.g., "NA" for Nadia, "OP" for openbot)
- **Workers**: Show initials when expanded under CEO

### Status Chips
- **Now chip**: Extracted from `Now:` line in CEO INDEX.md, shown below CEO name
- **Blocker chip**: When present (≠ "—"), shown with 🚫 emoji in danger color
- Text truncated to keep sidebar readable (50 chars for Now, 40 for Blocker)

### State Indicators
- **Busy/Working**: Avatar pulses with bronze glow during active job
- **Ping/Unread**: Bronze left border when CEO has pending approvals
- **Selected**: Bronze background, filled avatar when CEO is active

## Manual Verification Checklist

### 1. Avatar Display
- [ ] Chief of Staff shows "CS" avatar with gradient background
- [ ] Each CEO shows initials derived from name (first letter of first 2 words)
- [ ] Single-word CEOs show first 2 letters (e.g., "openbot" → "OP")
- [ ] Avatars are circular with bronze/mint gradient border
- [ ] Avatars remain visible when scrolling long CEO list

### 2. Now Chip Extraction
For each CEO, verify INDEX Now line appears in sidebar:

**Test with openbot CEO:**
- [ ] Open `org/projects/openbot/INDEX.md`
- [ ] Check `Now:` line content
- [ ] Verify same text appears below "openbot" in sidebar
- [ ] Verify long Now lines are truncated with "..."

**Test with Nadia CEO:**
- [ ] Open `org/projects/nadia/INDEX.md`
- [ ] Check `Now:` line content
- [ ] Verify same text appears below "Nadia" in sidebar

**Test with SAA Homes CEO:**
- [ ] Open `org/projects/saa-homes/INDEX.md`
- [ ] Check `Now:` line content
- [ ] Verify same text appears in sidebar

**Test with ListLogic CEO:**
- [ ] Open `org/projects/listlogic/INDEX.md`
- [ ] Check `Now:` line content
- [ ] Verify same text appears in sidebar

### 3. Blocker Chip Display
- [ ] Edit a CEO INDEX to set `Blocker: Test blocker message`
- [ ] Refresh board
- [ ] Verify 🚫 emoji appears before blocker text
- [ ] Verify blocker text appears in danger (red/coral) color
- [ ] Verify blocker is truncated if >40 chars
- [ ] Change blocker to `Blocker: —`
- [ ] Verify blocker chip disappears

### 4. Busy/Working State
- [ ] Send a message to a CEO (e.g., "What is going on?")
- [ ] While job is running, verify:
  - [ ] CEO avatar pulses with bronze glow
  - [ ] CEO name stays visible
  - [ ] Working state visible from any view
- [ ] After job completes, verify pulsing stops

### 5. Ping/Unread State
- [ ] Trigger a diff that needs Accept/Reject
- [ ] Verify CEO shows bronze left border (ping)
- [ ] Click the CEO
- [ ] Verify ping remains until approval is acted on

### 6. Fast Context Switching
- [ ] Click Chief of Staff
- [ ] Verify composer updates to "Talking to Chief of Staff" in <3s
- [ ] Click a CEO (e.g., openbot)
- [ ] Verify composer updates to "Talking to openbot" in <3s
- [ ] Click between multiple CEOs rapidly
- [ ] Verify no lag or visual glitches

### 7. Worker Display (Expanded Projects)
- [ ] Click twist arrow to expand a CEO
- [ ] Verify workers show avatars with initials
- [ ] Verify workers are indented under CEO
- [ ] Click a worker
- [ ] Verify context switches to that worker

### 8. Responsiveness
- [ ] Resize browser window to tablet size
- [ ] Verify avatars scale appropriately
- [ ] Verify initials remain readable
- [ ] Verify Now/Blocker chips wrap or truncate
- [ ] Test on mobile viewport (if applicable)

### 9. Accessibility
- [ ] Verify avatars have `aria-hidden="true"` (not read by screen readers)
- [ ] Verify CEO names are readable by screen readers
- [ ] Verify working state is announced in title attribute
- [ ] Test keyboard navigation (Tab through CEOs)
- [ ] Verify Enter/Space activates CEO selection

### 10. Edge Cases
- [ ] CEO with no Now line (should show empty or nothing)
- [ ] CEO with Now: "—" (should not display)
- [ ] CEO with Now: "source of truth" (should not display)
- [ ] CEO with empty name (should show "??")
- [ ] CEO with very long name (should show first 2 initials)
- [ ] Multiple CEOs busy at once (all should pulse)
- [ ] CEO with special characters in name (should handle gracefully)

### 11. Integration with Existing Features
- [ ] Add new CEO via "+ Add CEO" button
- [ ] Verify new CEO gets avatar immediately
- [ ] Right-click CEO to open context menu
- [ ] Verify menu still works with new layout
- [ ] Delete a CEO
- [ ] Verify sidebar updates without errors

### 12. Performance
- [ ] Open board with 4+ CEOs
- [ ] Verify sidebar renders in <1s
- [ ] Send message to CEO
- [ ] Verify avatar animation doesn't cause lag
- [ ] Rapidly switch between CEOs 10 times
- [ ] Verify no memory leaks or slowdown

## Screenshot Notes

### Key Screenshots to Capture

1. **Sidebar Overview**
   - Full sidebar with Chief of Staff + all CEOs visible
   - Highlight avatars with initials
   - Show at least 2 CEOs with Now chips visible
   - Label: "sidebar-overview.png"

2. **CEO with Blocker**
   - Edit a CEO INDEX to add a blocker
   - Capture sidebar showing 🚫 blocker chip in danger color
   - Label: "ceo-with-blocker.png"

3. **Busy/Working State**
   - Capture during an active job
   - Show pulsing avatar (may need screen recording)
   - Label: "ceo-working-state.png" or "ceo-working-state.gif"

4. **Ping/Unread State**
   - Trigger pending approval (diff or login wall)
   - Show bronze left border on CEO
   - Label: "ceo-ping-state.png"

5. **Expanded CEO with Workers**
   - Open a CEO with workers
   - Show worker avatars and indentation
   - Label: "expanded-ceo-workers.png"

6. **Selected CEO**
   - Click a CEO to select it
   - Show bronze background and filled avatar
   - Label: "selected-ceo.png"

7. **Multiple States**
   - If possible, capture sidebar with:
     - One CEO selected (bronze background)
     - One CEO busy (pulsing)
     - One CEO with blocker (danger color)
     - One CEO idle
   - Label: "multiple-states.png"

## Testing Environment

- **Browser**: Chrome/Firefox/Safari (specify which tested)
- **OS**: Windows/macOS/Linux (specify which tested)
- **Board URL**: http://127.0.0.1:8787 or Railway URL
- **Date Tested**: [Fill in]
- **Tester**: OpenBot CEO

## Known Limitations

1. **Avatar Images**: Currently only shows initials, no custom images yet
2. **Color Customization**: Avatar gradient is fixed bronze/mint theme
3. **Long Names**: Names >20 chars may overflow on narrow screens
4. **Animation Performance**: Pulsing may use more CPU on low-end devices

## Success Criteria (From ROADMAP)

- [x] Sidebar shows Chief of Staff + all CEOs with avatars or initials
- [x] Each CEO row shows live Now and/or Blocker chips from INDEX
- [x] Busy/working state visible when job is in flight
- [x] Fast CoS ↔ CEO switch without deep Settings spelunking
- [x] Enhanced existing sidebar/org UI in web/app.js + CSS
- [x] Kept BRAND/NOTICE, no secrets

## Notes for Reviewer

- This PR focuses on **visual feel** as much as functionality
- Sidebar should feel like a "team panel" not a file tree
- Fast switching (<3s) is critical for operator flow
- Avatars/chips make status visible at a glance without opening panels

## Next Steps After Merge

- Consider adding custom avatar upload (post-MVP)
- Consider color-coding busy/idle/blocked states beyond current indicators
- May need to optimize rendering for 10+ CEOs (pagination or virtualization)
- Integration with ROADMAP PR #1 (Builder Delight Loop) will show Now updates in real-time
