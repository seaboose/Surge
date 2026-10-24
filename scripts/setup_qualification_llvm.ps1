param(
    [Parameter(Mandatory = $true)][string]$Destination,
    [Parameter(Mandatory = $true)][string]$EvidenceDirectory,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Portable tools only. Never install software, change PATH, or reuse an old attempt.
$attempt = Join-Path ([IO.Path]::GetFullPath($EvidenceDirectory)) ('llvm-bootstrap-' + [guid]::NewGuid().ToString('N').Substring(0, 12))
New-Item -ItemType Directory -Path $attempt | Out-Null
$helper = Join-Path $attempt 'bootstrap.py'
$sourceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$helperSource = @'
"""Pinned portable LLVM bootstrap; emitted by setup_qualification_llvm.ps1."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import time
import urllib.request

VERSION = "23.1.4"
PACKAGE = "clang+llvm-23.1.4-x86_64-pc-windows-msvc"
ASSET = PACKAGE + ".tar.xz"
ARCHIVE_SHA256 = "854bffcfc84528e0ee92490ff5c178920abd358a79c3e98f053e41e3e8e4c6d2"
ARCHIVE_BYTES = 901281460
ASSET_ID = 659079132
RELEASE_URL = "https://github.com/llvm/llvm-project/releases/tag/llvmorg-23.1.4"
DOWNLOAD_URL = "https://github.com/llvm/llvm-project/releases/download/llvmorg-23.1.4/clang%2Bllvm-23.1.4-x86_64-pc-windows-msvc.tar.xz"
METADATA_URL = "https://api.github.com/repos/llvm/llvm-project/releases/tags/llvmorg-23.1.4"
ZST_SHA256 = "1a3f2f998e230b5791cc4e2bfe11a1f7c07fe42c96ff44f227c9db0bedfaf091"
DOWNLOAD_SECONDS = 300
EXTRACTION_SECONDS = 240
MAX_DOWNLOAD_BYTES = 1024 * 1024 * 1024
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024 * 1024
MAX_EXTRACTED_BYTES = 512 * 1024 * 1024
MAX_MEMBERS = 10000
PRIOR_HASHES = {
    "bin/clang-cl.exe": "2fcd72a41bbc6bcf8e89c63555c4db7451da53bf47082fb91d6b1c1e990636ad",
    "bin/lld-link.exe": "92052a2d6dbd722fe31ef1991f1522f3c8200cc78917bf65920f3790148c4c36",
    "bin/llvm-cov.exe": "05669ad9efaf5b2c5752434ccc320f2a73f3de32cabc74058ee9a77ed70798e6",
    "bin/llvm-profdata.exe": "211949a166b52eea799bc2e2aac9a60be6ae2870036643309d54e6ead6bbf058",
    "lib/clang/23/lib/windows/clang_rt.asan_dynamic-x86_64.dll": "3c1fa35803045a589c2bb3cc7d1a6a9ea873bcf147800979cd8f165bb3354b58",
    "lib/clang/23/lib/windows/clang_rt.fuzzer-x86_64.lib": "ac4c867a9ce41c37df703b0e5bac4cf1bfc337bde8d0251bba9b9498d8f6a68c",
    "lib/clang/23/lib/windows/clang_rt.profile-x86_64.lib": "110532f3ee37f05692e3237a0b7e935a202eee525fe77d2ffdd2f96b8555f3fd",
}


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def refuse_source_destination(destination, source_root):
    if destination == source_root or source_root in destination.parents:
        raise RuntimeError("LLVM destination must be outside the source checkout")
    if destination.exists():
        raise RuntimeError("LLVM destination already exists; preserve it and use a fresh destination")


class NoMetadataRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        raise RuntimeError("Release metadata redirects are refused")


def read_metadata():
    # A hosted job may supply its read-only GitHub token to avoid the shared
    # anonymous API quota. Consume it here so archive/version subprocesses cannot
    # inherit it. Never attach it to downloads or follow metadata redirects.
    token = os.environ.pop("SURGE_GITHUB_TOKEN", None)
    headers = {"User-Agent": "Surge-bounded-qualification",
               "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(METADATA_URL, headers=headers)
    try:
        opener = urllib.request.build_opener(NoMetadataRedirect())
        with opener.open(request, timeout=20) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise RuntimeError("Release metadata exceeds 1 MiB")
        if token and token.encode() in raw:
            raise RuntimeError("Release metadata unexpectedly contains credential data")
        return raw
    except Exception as exc:
        # Transport exception strings can contain request details. Retain only
        # exception class and an HTTP status; never serialize headers or tokens.
        status = getattr(exc, "code", None)
        detail = " HTTP " + str(status) if isinstance(status, int) else ""
        raise RuntimeError("Official metadata request failed: " + type(exc).__name__ + detail) from None
    finally:
        request.remove_header("Authorization")
        headers.pop("Authorization", None)
        token = None


def download(url, path, expected_bytes, expected_sha256):
    started = time.monotonic()
    request = urllib.request.Request(url, headers={"User-Agent": "Surge-bounded-qualification"})
    digest = hashlib.sha256()
    written = 0
    with urllib.request.urlopen(request, timeout=20) as response:
        length = response.headers.get("Content-Length")
        if length is not None and int(length) != expected_bytes:
            raise RuntimeError("Download Content-Length differs from pinned release metadata")
        with path.open("xb") as output:
            while True:
                if time.monotonic() - started > DOWNLOAD_SECONDS:
                    raise RuntimeError("Download exceeded its 300-second bound")
                block = response.read(1024 * 1024)
                if not block:
                    break
                written += len(block)
                if written > min(expected_bytes, MAX_DOWNLOAD_BYTES):
                    raise RuntimeError("Download exceeded its pinned byte bound")
                output.write(block)
                digest.update(block)
    if time.monotonic() - started > DOWNLOAD_SECONDS:
        raise RuntimeError("Download exceeded its 300-second bound")
    if written != expected_bytes or digest.hexdigest() != expected_sha256:
        raise RuntimeError("Download length or SHA-256 differs from pinned release")
    return {"bytes": written, "sha256": digest.hexdigest(), "seconds": round(time.monotonic() - started, 3)}


def extract_selected(archive, destination):
    started = time.monotonic()
    members = declared = extracted = files = 0
    seen = set()
    # Stream through the verified archive; only tools and Clang resource files
    # needed by the existing pilot are extracted. No archive code is executed.
    with tarfile.open(archive, mode="r|xz") as source:
        for member in source:
            members += 1
            declared += member.size
            if members > MAX_MEMBERS or declared > MAX_ARCHIVE_BYTES:
                raise RuntimeError("Archive member or declared-byte bound exceeded")
            if time.monotonic() - started > EXTRACTION_SECONDS:
                raise RuntimeError("Extraction exceeded its 240-second bound")
            name = PurePosixPath(member.name)
            if "\\" in member.name or ":" in member.name or name.is_absolute() or ".." in name.parts:
                raise RuntimeError("Archive contains an unsafe path")
            if not name.parts or name.parts[0] != PACKAGE:
                raise RuntimeError("Archive contains an unexpected package root")
            relative = PurePosixPath(*name.parts[1:]).as_posix()
            selected = relative in PRIOR_HASHES or relative.startswith("lib/clang/23/")
            if not selected or member.isdir():
                continue
            if not member.isfile():
                raise RuntimeError("Selected archive member is not a regular file")
            if member.name in seen:
                raise RuntimeError("Archive contains a duplicate selected member")
            seen.add(member.name)
            extracted += member.size
            if extracted > MAX_EXTRACTED_BYTES:
                raise RuntimeError("Extracted-byte bound exceeded")
            target = destination.joinpath(*name.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.extractfile(member) as content, target.open("xb") as output:
                remaining = member.size
                while remaining:
                    if time.monotonic() - started > EXTRACTION_SECONDS:
                        raise RuntimeError("Extraction exceeded its 240-second bound")
                    block = content.read(min(1024 * 1024, remaining))
                    if not block:
                        raise RuntimeError("Truncated archive member")
                    output.write(block)
                    remaining -= len(block)
            files += 1
    return {"members_examined": members, "declared_bytes": declared, "extracted_bytes": extracted,
            "files": files, "seconds": round(time.monotonic() - started, 3)}


def verify_tools(root):
    files = {}
    for relative, expected in PRIOR_HASHES.items():
        path = root / relative
        actual = sha(path)
        files[relative] = {"bytes": path.stat().st_size, "sha256": actual,
                           "prior_verified_sha256": expected, "matches_prior": actual == expected}
        if actual != expected:
            raise RuntimeError("Extracted tool differs from prior verified toolchain: " + relative)
    required_resources = ["include/stddef.h", "lib/windows/clang_rt.asan_dynamic-x86_64.lib",
                          "lib/windows/clang_rt.asan_dynamic_runtime_thunk-x86_64.lib",
                          "lib/windows/clang_rt.asan_static_runtime_thunk-x86_64.lib"]
    for relative in required_resources:
        if not (root / "lib/clang/23" / relative).is_file():
            raise RuntimeError("Missing Clang resource: " + relative)
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    args = parser.parse_args()
    destination = args.destination.resolve()
    evidence = args.evidence.resolve()
    report = {"schema": "surge-qualification-llvm-v1", "status": "failed", "started_utc": utc(),
              "version": VERSION, "destination": str(destination), "archive": {
                  "name": ASSET, "url": DOWNLOAD_URL, "release_url": RELEASE_URL,
                  "asset_id": ASSET_ID, "bytes": ARCHIVE_BYTES, "sha256": ARCHIVE_SHA256,
                  "metadata_url": METADATA_URL, "local_zst_sha256_for_comparison": ZST_SHA256},
              "bounds": {"download_seconds": DOWNLOAD_SECONDS, "extraction_seconds": EXTRACTION_SECONDS,
                         "total_process_seconds": 600, "max_download_bytes": MAX_DOWNLOAD_BYTES,
                         "max_archive_bytes": MAX_ARCHIVE_BYTES, "max_extracted_bytes": MAX_EXTRACTED_BYTES,
                         "max_members": MAX_MEMBERS}, "phases": {},
              "limitations": ["Different archive compression from the local zstd package; required tools and runtimes are compared by hash.",
                              "SHA-256 and official release metadata verified; release signatures/attestations are not verified here.",
                              "Tool presence and version do not prove instrumentation; the qualification pilot must execute its controls."]}
    try:
        refuse_source_destination(destination, args.source_root.resolve())
        destination.mkdir(parents=True)
        archive = destination / ASSET
        raw = read_metadata()
        (evidence / "release-metadata.json").write_bytes(raw)
        metadata = json.loads(raw)
        matches = [item for item in metadata["assets"] if item["name"] == ASSET]
        if len(matches) != 1:
            raise RuntimeError("Official release asset not uniquely identified")
        asset = matches[0]
        if (metadata["tag_name"] != "llvmorg-" + VERSION or asset["id"] != ASSET_ID
                or asset["size"] != ARCHIVE_BYTES or asset["digest"] != "sha256:" + ARCHIVE_SHA256
                or asset["browser_download_url"] != DOWNLOAD_URL):
            raise RuntimeError("Official release metadata differs from pinned identity")
        report["archive"]["metadata_sha256"] = hashlib.sha256(raw).hexdigest()
        report["phases"]["metadata"] = "passed"
        write_json(evidence / "report.json", report)
        report["phases"]["download"] = download(DOWNLOAD_URL, archive, ARCHIVE_BYTES, ARCHIVE_SHA256)
        write_json(evidence / "report.json", report)
        report["phases"]["extraction"] = extract_selected(archive, destination)
        root = destination / PACKAGE
        report["files"] = verify_tools(root)
        versions = {}
        for tool in ("clang-cl.exe", "lld-link.exe", "llvm-cov.exe", "llvm-profdata.exe"):
            result = subprocess.run([str(root / "bin" / tool), "--version"], capture_output=True,
                                    text=True, timeout=5, check=True)
            if VERSION not in result.stdout or len(result.stdout) + len(result.stderr) > 65536:
                raise RuntimeError("Tool version missing or output exceeds bound: " + tool)
            versions[tool] = result.stdout.strip()
        report["versions"] = versions
        report["llvm_bin"] = str(root / "bin")
        report["status"] = "passed"
    except Exception as exc:
        report["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        report["finished_utc"] = utc()
        write_json(evidence / "report.json", report)
        print(json.dumps({"status": report["status"], "report": str(evidence / "report.json"),
                          "error": report.get("error")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
'@
Set-Content -LiteralPath $helper -Value $helperSource -Encoding utf8
$stdoutPath = Join-Path $attempt 'stdout.log'
$stderrPath = Join-Path $attempt 'stderr.log'
$exitCode = 1
try {
    $pythonCommand = Get-Command $Python -ErrorAction Stop
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $pythonCommand.Source
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    @('-B', $helper, '--destination', [IO.Path]::GetFullPath($Destination), '--evidence', $attempt, '--source-root', $sourceRoot) | ForEach-Object { $info.ArgumentList.Add($_) }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $info
    if (-not $process.Start()) { throw 'Could not start bounded LLVM bootstrap.' }
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(600000)) {
        $process.Kill($true)
        $process.WaitForExit()
        throw 'LLVM bootstrap exceeded its 600-second outer bound.'
    }
    $exitCode = $process.ExitCode
    Set-Content -LiteralPath $stdoutPath -Value $stdout.GetAwaiter().GetResult() -Encoding utf8
    Set-Content -LiteralPath $stderrPath -Value $stderr.GetAwaiter().GetResult() -Encoding utf8
    Get-Content -LiteralPath $stdoutPath
    if ($exitCode -eq 0) {
        $report = Get-Content -LiteralPath (Join-Path $attempt 'report.json') -Raw | ConvertFrom-Json
        if ($report.status -ne 'passed' -or -not (Test-Path -LiteralPath (Join-Path $report.llvm_bin 'clang-cl.exe'))) {
            throw 'Bootstrap did not produce a passed report and compiler.'
        }
        if ($env:GITHUB_OUTPUT) { Add-Content -LiteralPath $env:GITHUB_OUTPUT -Value ('llvm_bin=' + $report.llvm_bin) -Encoding utf8 }
        Write-Output ('LLVM bin: ' + $report.llvm_bin)
    }
} catch {
    $failure = @{ status = 'failed'; error = $_.Exception.Message; finished_utc = [DateTime]::UtcNow.ToString('o'); total_process_seconds = 600 }
    $failure | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $attempt 'wrapper-failure.json') -Encoding utf8
    if (Test-Path variable:stdout) { Set-Content -LiteralPath $stdoutPath -Value $stdout.GetAwaiter().GetResult() -Encoding utf8 }
    if (Test-Path variable:stderr) { Set-Content -LiteralPath $stderrPath -Value $stderr.GetAwaiter().GetResult() -Encoding utf8 }
    Write-Output ('LLVM bootstrap failed: ' + $_.Exception.Message)
    $exitCode = 1
}
Write-Output ('Bootstrap evidence: ' + $attempt)
exit $exitCode
