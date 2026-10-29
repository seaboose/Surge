# Open the Windows package

The Windows x64 package includes Surge, its runtime and the separate owned sample
used by **Try Demo**. It needs no Python, Node.js, compiler or setup command.

1. Extract the complete `Surge-<candidate>-windows-x64.zip` to a new local folder.
   Keep all extracted files together; do not run the application from inside the ZIP.
2. Open `Surge.exe`. Use **Try Demo** for a first investigation, **Import evidence**
   for your own supported files, or **Case library** to reopen saved work.
3. In Try Demo, choose **Start collection**, then **Stop collection** when you have
   observations. The sample runs separately by design to demonstrate collection,
   analysis and replay. The included sample has an approval for its exact build;
   complete unchanged observations should show **No finding**. That result applies
   only to the measured ranges and observations, not the whole computer.
4. Choose **Save case** to keep the investigation. Close and reopen Surge, then
   find it in **Case library**. A reopened case contains recorded evidence; it does
   not start a live check.

The `demos/native` folder contains published saved examples. Use **Case library →
Open case file** to inspect one without adding it, or **Import case** to keep a
library copy. These examples retain their original provenance, separate from the
sample build bundled with this package.

## Keep your cases

Your library is stored in your Windows application-data folder under
`surge-desktop`, outside the extracted package. Use **Export case** to make portable
copies of important cases in a separate folder. Deleting a library entry preserves
original evidence and external exports.

To replace a package, close Surge, extract the new ZIP to a different folder and
open its `Surge.exe`. Keep the previous package and your exports until you have
reopened your cases successfully. Do not combine runtime files from two packages.
Folder replacement checks do not establish compatibility with every future version.

## If Surge cannot open

Keep the startup message and the diagnostic location it provides. Extract the
complete ZIP again into a new folder and try that copy. Installing a developer
runtime does not repair a missing bundled runtime. Startup diagnostics contain
component/status information, not imported evidence or raw worker messages.

The candidate is unsigned. A package hash identifies the tested bytes; it does
not establish publisher identity or SmartScreen reputation. Record any Windows
warning or blocked launch as a test result. This guide does not ask you to disable
Windows protection or use administrator privileges.

## Candidate status

Read the accompanying generated qualification report for the exact source, package
SHA-256, completed checks, failed attempts and untested environments. Automated
checks do not establish unfamiliar-user acceptance, which remains **pending**.
The original broader fuzzing campaign remains **unfinished**. No installer,
automatic updater, whole-process assurance or client attestation is included.
