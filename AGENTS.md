# Workspace preferences

- Keep visible windows for this work on the user's left portrait monitor unless
  the user requests another display. At the time of the request it was Windows
  `DISPLAY3`, with bounds x=-1080, y=0, width=1080, height=1920 and a 1872-pixel
  work area. Recheck the display layout when starting a new session.
- `verification/window-placement.json` stores the local visible-launch preference.
  Pass that JSON as `SURGE_PRESENTATION` for launches outside `Start-Surge.ps1`.
  For automated Electron checks use the same point with `hidden: true`.
- Run GUI checks that need a wider viewport hidden, so they do not occupy another
  monitor. Coordinate GUI checks sequentially. Do not move unrelated applications
  or change the Windows display configuration.
- Preserve unrelated logo explorations under `output/`; these are generated
  drafts and are excluded from source and product packages.
