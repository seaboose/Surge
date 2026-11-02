"""Bounded read-only downloads of two official Riot pages and their ability clips.

Reference material only. Nothing downloaded is executed or added to gameplay.
Existing evidence is never overwritten. Run only when network research is allowed.
"""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "profiles/evidence/ability-video-2026-10-26"
ALLOW = {"www.leagueoflegends.com", "leagueoflegends.com", "lol.dyn.riotcdn.net"}


def download(url, maximum):
    if urlparse(url).scheme != "https" or urlparse(url).hostname not in ALLOW:
        raise ValueError("Unapproved public reference origin")
    with urlopen(Request(url, headers={"User-Agent": "Survive-Calibration/1.0"}), timeout=30) as response:
        if urlparse(response.url).hostname not in ALLOW:
            raise ValueError("Unexpected redirect origin")
        content = response.read(maximum + 1)
    if len(content) > maximum:
        raise ValueError("Reference exceeds bounded download size")
    return content


def main():
    OUTPUT.mkdir(exist_ok=False)
    receipts = []
    for champion, number, key in (("lucian", "0236", "E"), ("lux", "0099", "Q")):
        page_url = f"https://www.leagueoflegends.com/en-us/champions/{champion}/"
        page = download(page_url, 2 * 1024 * 1024)
        (OUTPUT / (champion + "-page.html")).write_bytes(page)
        text = page.decode("utf-8").replace("\\/", "/")
        pattern = r'https://lol\.dyn\.riotcdn\.net/[^"\s<>\\]*ability_' + number + '_' + key + r'1\.mp4'
        matches = sorted(set(re.findall(pattern, text)))
        if len(matches) != 1:
            raise ValueError("Official page did not establish one expected ability clip: " + champion)
        content = download(matches[0], 20 * 1024 * 1024)
        filename = champion + "-" + key.lower() + ".mp4"
        (OUTPUT / filename).write_bytes(content)
        receipts.append({"champion": champion, "ability": key, "page_url": page_url,
                         "page_sha256": hashlib.sha256(page).hexdigest(), "video_url": matches[0],
                         "file": filename, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
                         "measurement_status": "not-measured"})
    with (OUTPUT / "downloads.json").open("x", encoding="utf-8") as stream:
        json.dump(receipts, stream, indent=2)
        stream.write("\n")
    print(json.dumps(receipts))


if __name__ == "__main__":
    main()
