# Learn Surge with the interface inspector

The developer edition uses Chromium's built-in DevTools, docked beside the actual
application. This gives you the live HTML, CSS, layout measurements and original
JavaScript/JSX sources. There is no second implementation or additional server.
The standalone product has no Developer menu, source maps or enabled DevTools.

From the source kit's `desktop` folder, after the normal development setup:

```text
pnpm dev
```

This builds readable development code with source maps and opens **Surge —
Development**. Existing source launches also have the Developer menu; `pnpm dev`
adds the useful source maps. `pnpm build` restores the compact production renderer.

1. **Find an element.** Right-click a tab, label or button and choose **Inspect
   element**. Or press **F12**, then use DevTools' element picker (**Ctrl+Shift+C**)
   to point at the interface. The highlighted HTML node is the element you see.
2. **Understand its size.** In **Elements**, use **Styles**, **Computed** and the
   box-model display to inspect the active CSS, inherited rules, padding, margins,
   grid/flex settings and dimensions. Crossed-out declarations were overridden.
3. **Try a change.** Edit a CSS value or toggle a declaration in Styles. The app
   changes immediately. These experiments are temporary and reset on reload.
   Save a lasting change in the mapped source file, then rebuild and reopen.
4. **Find the code.** Click a stylesheet's filename/line beside its rule. In
   **Sources**, use the file picker (**Ctrl+P**) for `SurviveWorkspace.jsx`,
   `SurviveFlow.jsx` or `main.jsx`. Source maps include the original source text.
   A rendered HTML node is not the same thing as a React component; use its class,
   accessible label or text to locate the matching JSX.
5. **Trace a click.** Use **Sources → Event Listener Breakpoints → Mouse → click**,
   then click a control. Inspect the call stack and resume/step until the mapped
   handler is visible. The renderer's `window.surge.request` call crosses into the
   validated IPC boundary; Python processing is outside browser DevTools. Follow
   the corresponding method in `desktop_worker.py` using `docs/code-map.md`.

**Developer → How to inspect and edit CSS** provides the short instructions inside
the app. F12 or Ctrl+Shift+I toggles the docked inspector while Surge has focus.
The inspector can also be closed using its own close button. Docking reduces
available page width, so the app may switch to its narrow layout; this is useful
for learning responsive design. Test the final layout with the inspector closed.

The developer inspector is a local editing tool. It does not grant the renderer
new filesystem or process APIs. CSS experiments do not change recorded evidence,
game rules or saved reports. Do not enable persistent DevTools file-workspace
editing unless you intend to edit those source files; normal CSS experiments
require no filesystem permission. Rebuild and run the relevant diagnostics before
keeping a change.

During automated checks, Electron launches another isolated application with
separate test data. A `--surge-test` source launch is explicitly titled **Surge —
Test session**. The older Python/Tk workbench is a separate legacy interface used
by compatibility tests; it is not included in the standalone runtime product.

This workspace also keeps an optional local display preference in
`verification/window-placement.json`, which `Start-Surge.ps1` passes through
`SURGE_PRESENTATION`. The setting selects a display point or rectangle; `hidden`
keeps automated wide-viewport checks invisible. The main process fits visible
Surge and Survive windows to that display. This controls presentation only and
does not enter renderer IPC, evidence or detector configuration. The local file
is excluded from release packages; unset launches retain their normal defaults.

Implementation references: [Electron inspector methods](https://www.electronjs.org/docs/latest/api/web-contents#contentsopendevtoolsoptions)
and [esbuild source maps](https://esbuild.github.io/api/#sourcemap).
