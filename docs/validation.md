# Validation and limits

## Recorded checks

- On **1 November 2026**, the original 0.4.3 Windows package completed gameplay,
  recording, analysis, report export, reopening, and native/import checks in one
  fresh Windows 11 VMware guest without development toolchains.
- On **2 November 2026**, the cleaned package completed gameplay-to-report,
  relocation, and reopening on the development host. Its executables and game
  assets were byte-identical to the guest-tested runtime.
- The reviewed source passed four Windows CI jobs: package build, packaged
  acceptance, first use, and the broader test suite. A new source commit must
  earn its own CI result; this is a record of the checked predecessor.

The 0.4.4 publication keeps that runtime and updates packaging, guides, and the
source repository. Repackaging is not a new clean-machine test. The release's
validation receipt and checksums identify the exact files and scope.

[Guest evidence manifest](../evidence/clean-machine-20261101/publication-manifest.json) ·
[Guest environment](../evidence/clean-machine-20261101/guest-report.public.json)

The original guest-tested archive SHA-256 was:

```text
dc135a0348a3ee85b9360b0e7151230df419d79436b0f79658134b1a9048c005
```

## What remains unproven

Surge checks its own game and native sample. Legal automation can satisfy all
movement rules, so no finding does not prove human input. Synthetic fixtures and
controlled violations do not establish real-cheat accuracy, a human baseline,
or a human false-positive rate. Unfamiliar-user testing remains pending.

The native sample measures limited ranges at a target interval. Changes outside
coverage or between observations may be missed. Hashes check retained evidence
consistency; unsigned local data does not authenticate an untrusted client.

One VM and one development host do not cover all Windows hardware. The build is
unsigned. These checks are not a security audit or a completed broad fuzzing campaign.
See [security boundaries](../SECURITY.md) and the [study protocol](survive-study.md).

## Repeat the checks

Start with [development setup](development.md), then use the
[qualification guide](qualification.md), [package checks](windows-package-check.md),
and [clean-machine procedure](clean-machine-qualification.md). Keep failures and
record the exact source and package hashes. Do not turn a past pass into a claim
about untested changes.
