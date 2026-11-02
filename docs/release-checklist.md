# Release checklist

Use one versioned release for each reviewed publication. Continue development in
small branches; leave the published assets unchanged until the next release.

1. Start from a clean checkout. Keep only source, required tests, fixtures, licences,
   and concise documentation. Update `scripts/source-files.txt` for file changes.
2. Review the staged diff. Exclude local paths, credentials, tool configuration,
   session logs, personal recordings, backup archives, and generated dependencies.
3. Run relevant tests and `scripts/check_release.py`; require Windows CI to pass.
   Preserve failures privately and report any skipped or incomplete checks.
4. Build or explicitly identify reused runtime binaries. Verify required notices
   and record source, package, and per-file hashes. Never present repackaging as a rebuild.
5. Test the extracted gameplay-to-report flow and reopening. A new clean-machine
   claim requires a new guest test of that exact package.
6. Check the download, screenshot tour, code guide, and report links. Read the README
   as a first-time user; keep detailed procedures in `docs/`.
7. Publish the release with today's actual date, checksums, and short notes. Keep one
   current public release and preserve superseded artifacts in a verified private archive.

## Release note template

```text
Surge <version> — <YYYY-MM-DD>

Download the Windows ZIP, extract it, and open Surge.exe.

Changes: <brief behavior or packaging changes>.
Verified: <exact checks and source/package identifiers>.
Limits: <remaining gaps; distinguish host and clean-machine results>.
```

Use ordinary descriptive branch and commit names. Do not copy workstation details
or editing-session material into project documentation. Preserve required upstream
attribution for software actually distributed.
