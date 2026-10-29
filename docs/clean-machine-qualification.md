# Clean Windows qualification

The product runs with bundled Electron/Python and a cooked Survive game. A
restricted PATH on the development host proves runtime selection, but does not
prove operation on a freshly provisioned Windows installation.

Initial discovery on 28 October 2026 found Windows 11 Home with a Linux Docker/WSL2
backend and no existing Windows test guest. No Windows Sandbox executable, Hyper-V
management module, VMware, VirtualBox or QEMU executable was initially available.
Microsoft states that [Windows Sandbox is not
supported on Windows Home](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/),
and [Windows containers do not support desktop GUI applications](https://learn.microsoft.com/en-us/virtualization/windowscontainers/quick-start/lift-shift-to-containers).
Consequently the existing host checks could not honestly count as clean-Windows
acceptance.

The user then authorized a new local test VM. A minimal, verified Oracle
VirtualBox 7.2.22 host installation completed without a host restart. The official
Windows 11 Enterprise Evaluation x64 image matched Microsoft's published SHA-256,
and matching Guest Additions matched Oracle's published checksum. The VM uses
6 GiB RAM, four virtual CPUs, a 64 GiB dynamic disk, EFI, TPM 2.0 and Secure Boot.
Host virtualization/security protections remain enabled; no host firewall rule,
security exception or reboot was introduced. See [Oracle installation details](https://docs.oracle.com/en/virtualization/virtualbox/7.2/user/installation.html)
and [Microsoft's image-verification instructions](https://support.microsoft.com/en-us/servicing/os/windows/docs/2026/09/verify-the-authenticity-of-a-windows-11-enterprise-evaluation-iso-file).

The reviewed unattended template removes Oracle's stock Windows-requirement
bypass commands. Guest setup installs the signed Guest Additions without adding
extra root certificates, a test execution service or firewall exceptions. Private
generated guest credentials remain outside the source/product archives. Setup
and runtime acceptance are distinct: the latter must run on the guest's ordinary
interactive desktop with non-elevated application, worker and game tokens.

Provisioning alone is not acceptance. Exact guest installation and qualification
results belong in retained external receipts for the tested ZIP; this document
does not claim that a prepared or still-installing guest has passed.

## Offline qualification kit

Create a separate developer validation kit for the exact final product:

```text
python scripts/check_clean_machine.py prepare --archive <product.zip> --manifest <package-manifest.json> --output-root <new-kit-parent>
```

Preparation verifies the package's bytes, copies the existing acceptance harnesses
and pinned Playwright packages (including their licences), and hashes all tooling.
It does not download software, install anything, or add test files to Product.

Copy the generated folder to a freshly provisioned Windows x64 VM with adequate
graphics support. Supply `guest-provenance.json`:

```json
{
  "provisioning": "fresh-vm",
  "image": "Windows 11 x64 image and build description",
  "created_utc": "2026-10-28T00:00:00Z"
}
```

Use the actual creation timestamp and image. Run `Start-Qualification.ps1
-Provenance <absolute-file-path>` from an ordinary PowerShell session. Keep the
output path short; the default creates a fresh folder under Public Documents/SQ.
Allow 12 GiB free disk and roughly 10 minutes. Do not bypass Windows security
prompts or change script/security policy; use an approved runner if local policy
blocks the script.

The bootstrap verifies the ZIP and uses its bundled Python. Electron's bundled
Node runtime supervises Playwright; actual application processes receive a
separate restricted environment and remain packaged, isolated renderers. No
external Python, Node, Unreal, compiler or package-manager installation is needed.

The guest records OS/GPU/VM identity and checks PATH, installed developer-product
registrations, known Unreal directories and registered builds. A desktop-host
model or observed developer installation blocks the clean claim. Windows Store
Python aliases are recorded separately from installed interpreters. Freshness is
an operator declaration; the check is not cryptographic attestation or a complete
filesystem inventory.

Both existing acceptance journeys then run with fresh profiles:

1. Real standalone legal, speed-control and partial practice rounds; exact capture,
   replay/citations, report export, relocation and reopening.
2. Original Surge import/native demonstration, replacement, missing-component
   recovery, saved-case preservation and immutable payload checks.

During all three game rounds, the supervisor samples the owned game's loaded
modules and network endpoints twice. Package/Windows-only modules and no owned
TCP/UDP endpoints are required at those observations. This is a sampled dependency
and network check, not a comprehensive security audit.

Keep the full output folder, `clean-machine-report.json`, original ZIP and manifest.
`clean_machine_qualified: true` requires a qualifying guest preflight and both
journeys to pass. `-HostedSelfCheck` exercises this tooling on an existing host but
always reports `clean_machine_qualified: false`, even when every journey passes.
Prepared kits and hosted checks must never be advertised as clean-machine acceptance.

This does not replace native graphics/driver coverage, signing/reputation checks,
unfamiliar-user acceptance, human dataset collection or an independent security
review. It makes the remaining clean-machine check repeatable and evidence-bound.
