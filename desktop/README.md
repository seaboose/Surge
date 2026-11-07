# Desktop source

Run `Setup-Surge.ps1` from the repository root, then `Start-Surge.cmd`.
Within `desktop`, `pnpm build` builds the renderer and `pnpm start` opens it.
`pnpm dev` enables source maps and the interface inspector for development.

`src/main.jsx` starts React. `case-workspace/App.jsx`, `SurviveWorkspace.jsx`,
and `SurviveInvestigations.jsx` coordinate the workflows. The main process owns
native dialogs and the Python worker. The sandboxed renderer cannot choose
arbitrary filesystem paths or commands. See the [source guide](../docs/code-map.md).

Electron and esbuild are source-build dependencies. The packaged application
contains the required runtime and compiled renderer, without build tools,
development inspectors, source maps, or tests. Tests and their dependencies are
available in the matching validation kit.
