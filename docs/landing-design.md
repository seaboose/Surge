# Landing and preferences

The landing screen separates starting an investigation, returning to saved work,
and exploring the built-in demonstrations.

## Navigation

- **Open evidence** opens the existing file picker. Cancel preserves the workspace.
- **Start capture** offers supported owned-process and Survive telemetry sources.
- **Try Demo** opens the Survive and Code integrity demonstration chooser.
- Investigation views stay visible below the case heading. **Tools** exposes the
  case library and provides view shortcuts while on Home or a source chooser.
- **Home** returns to the landing screen without clearing evidence or stopping
  collection. Return and stop controls remain available for current work.
- Survive keeps its existing report and draft leave guards.

The bottom row shows one real saved case and provides **Resume** and
**All cases**. Its title also opens that case. “Recent” means the newest saved
case by its creation timestamp, not the most recently opened case. Library
changes refresh the row. Empty, loading and unavailable states remain distinct.

## Visual system

The SURGE wordmark uses bundled Inter at weight 200 with wide tracking. A small,
tightly spaced subtitle reads "Capture telemetry. Investigate behavior." in the
same family. Its width stays below the title's width; on narrow windows it wraps
between the two phrases. The title group sits above a reserved gap to the processor.
The 1920 by 1080 reference scene contains 32 deterministic cable routes, with varied
approaches, source colors and three depth levels. Each packet retains its path's
color and depth. Three paths pass in front of the lettering; the others pass
behind. Final inlet entries are straight. No letter is a processing stage.

The graphite processor contains three packets spaced equally along its engraved
S. A shared clock pauses and advances them without bunching. A small highlight
travels within the channel during advancement. Violet and teal routes connect
the compact actions. The desktop icon shares the same S silhouette and retains
a simpler, brighter mark at small sizes.

The reference scene scales uniformly. Compact and portrait windows adapt control
positions and connectors, while retaining readable labels and reachable recent
cases. Short windows can scroll. The canvas stops scheduling animation frames
when hidden, outside the visible area, or in reduced-motion mode; resize and
interaction events can still draw a static frame.

Packet motion and route colors are illustrative. They do not report collection,
security health, detection outcomes or source counts. Actual evidence keeps its
existing status labels and semantic colors. The title has a semantic heading
for assistive technology. Interface text uses bundled Inter;
smaller text has tighter spacing and a readable weight. The recent-case row sits
near the lower edge with reserved space rather than overlaying content.

## Compact workspaces

Capture, investigation, Survive, dialogs and settings share compact controls,
thin surface edges, bundled Inter and a small common header. Home retains its
existing scene. Workspace motion is limited to brief hover transitions; reduced
motion also disables those transitions.

Capture keeps the next action prominent while showing live collection and the
viewed evidence snapshot separately. Inspect does not stop collection. Stop opens
the final retained snapshot. Source details and demonstration context can be
expanded without hiding collection errors or snapshot provenance.

Results retain search, priority filtering, exports and the existing analysis.
Native observations add range and sample labels from the same source record.
The inspector highlights native range facts and byte differences, with complete
analysis and raw record details under disclosures. Closing it widens the list;
selecting a record reopens it. Generic numerical evidence keeps its chart.
Narrow windows stack the inspector beneath the observations and allow scrolling.

## Settings

The settings cog is available beside Tools, including within the Survive
workspace. Escape closes the settings panel and returns focus to its trigger.

**Reduce motion** keeps the interface still. The initial setting follows the
operating system's preference. An explicit choice overrides it, and **Use system
setting** restores automatic behavior. Static artwork retains the controls and
information hierarchy.

**Open latest case on startup** is off by default. When enabled, startup opens
the newest saved case through the normal case-opening path. It does not replace
already loaded evidence or a capture session. A user action takes precedence over
a delayed startup lookup. An empty library or a failed open returns to Home.

Preferences are stored locally per application profile. Invalid saved settings
fall back to defaults with a message. If persistence fails, changes apply to the
current session and the settings panel reports that they could not be saved.

## Verification scope

Focused checks cover navigation, current-work preservation, library updates,
preference persistence, startup fallback, reduced motion, keyboard access and
compact layouts. These changes do not expand supported capture sources,
detection rules, or the meaning of existing evidence results.

