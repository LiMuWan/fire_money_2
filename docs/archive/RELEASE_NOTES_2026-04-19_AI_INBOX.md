# Release Notes
## 2026-04-19

### Highlights

- Added `gpt-5.4` powered single-symbol AI review into the desktop product.
- Added streaming AI review output on the recommendation page.
- Added a unified message center that merges:
  - AI review events
  - message source refresh events
  - recommendation pool refresh events
  - trade submission / execution feedback

### AI Review

- Configurable in the configuration workspace:
  - Base URL
  - API Key
  - model
  - reasoning effort
  - timeout
  - max output tokens
- Supports:
  - manual trigger
  - auto-trigger after news refresh / pool refresh
  - local result caching
  - DPAPI protection for the API key on Windows

### Unified Message Center

- Added recommendation-page inbox / dashboard with:
  - category filter
  - sort mode
  - unread / handled states
  - mark read / mark handled
  - mark all read
  - clear handled
  - open related page
  - focus symbol
- Added visible counters:
  - recommendation tab badge
  - message center badge
  - metric cards for unread / open / AI / news / trade

### Demo

- New demo script:
  - [demo_ai_inbox_flow.py](C:/Users/18335/Documents/New%20project/tools/demo_ai_inbox_flow.py)
- New demo suite wrapper:
  - [run_ai_inbox_demo_suite.ps1](C:/Users/18335/Documents/New%20project/tools/run_ai_inbox_demo_suite.ps1)
- New release material collector:
  - [prepare_ai_inbox_release_materials.ps1](C:/Users/18335/Documents/New%20project/tools/prepare_ai_inbox_release_materials.ps1)
- New all-in-one bundle packager:
  - [package_ai_inbox_release.ps1](C:/Users/18335/Documents/New%20project/tools/package_ai_inbox_release.ps1)

Run:

```powershell
python .\tools\demo_ai_inbox_flow.py
.\tools\run_ai_inbox_demo_suite.ps1
.\tools\prepare_ai_inbox_release_materials.ps1
.\tools\package_ai_inbox_release.ps1 -SkipBuild
```

### Verification

- Related unit tests passed.
- Full `unittest discover` passed.
- Offscreen startup smoke passed.

### Notes

- This capability remains research-assistive.
- It does not replace the final manual trading decision.
