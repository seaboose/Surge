# Run Surge on Windows

Extract the complete Windows ZIP into a new local folder and open **Surge.exe**.
Keep all extracted files together. No Python, Node, compiler, or Unreal Editor
installation is needed to run the complete package.

- **Open evidence** imports supported records.
- **Start capture → Owned process** captures the included process.
- **Try Demo** contains Code integrity and Survive.
- **Tools → Case library** opens saved or portable cases.
- **Home** returns without clearing evidence or stopping collection.

During collection, **Inspect snapshot** opens a fixed copy while capture
continues. **Stop collection** opens the final retained snapshot. Use **Save
case** for the inspected investigation or **Export captured records** for the
current capture window. These can represent different moments.

The `demos/native` folder contains saved examples with their original provenance.
Use **Case library → Open case file** to inspect one or **Import case** to add it
to the library. No finding applies only to measured observations and ranges.

Cases, recordings, and reports are stored in the local user profile outside the
application folder. Export important cases before replacing a package. Close
Surge and its game, extract the replacement to a new folder, and reopen saved
work before discarding the old package. Do not combine files from two versions.

If startup fails, preserve the message and its diagnostic location. Extract a
complete copy again. Installing a developer runtime cannot replace missing
bundled files. Packages are unsigned unless the release explicitly states
otherwise; hashes establish byte identity, not publisher trust.

See the [Survive walkthrough](standalone-demo.md) and [security scope](../SECURITY.md).
