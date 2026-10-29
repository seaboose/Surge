"""Check frozen source and both reviewed profiles; runtime evidence is separate."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
profile = json.loads((ROOT / "profiles/survive-lucian-practice-v1.json").read_text(encoding="utf-8"))
reference = json.loads((ROOT / "profiles/survive-lucian-reference-v1.json").read_text(encoding="utf-8"))
source = (ROOT / "Source/SurgeMovementLab/SurviveProfile.h").read_text(encoding="utf-8")
values = {name: float(value) for name, value in re.findall(
    r"inline constexpr (?:float|double|int32) (\w+) = ([0-9.]+)(?:f)?;", source)}
expected = {
    "WalkSpeed": profile["movement"]["walk_speed_cm_s"],
    "PathRadius": profile["movement"]["path_radius_cm"],
    "HitRadius": profile["movement"]["hit_radius_cm"],
    "VisualRadius": profile["movement"]["visual_radius_cm"],
    "DashMinRange": profile["dash"]["min_range_cm"],
    "DashMaxRange": profile["dash"]["max_range_cm"],
    "DashSpeed": profile["dash"]["speed_cm_s"],
    "DashPracticeCooldown": profile["dash"]["cooldown_s"],
    "DashReferenceCooldown": profile["dash"]["reference_cooldown_s"],
    "BlinkRange": profile["blink"]["max_range_cm"],
    "BlinkPracticeCooldown": profile["blink"]["cooldown_s"],
    "BlinkReferenceCooldown": profile["blink"]["reference_cooldown_s"],
    "ProjectileSpeed": profile["projectile"]["speed_cm_s"],
    "ProjectileRadius": profile["projectile"]["radius_cm"],
    "ProjectileWarning": profile["projectile"]["cast_delay_s"],
    "ProjectileRange": profile["projectile"]["range_cm"],
    "CircleRadius": profile["circle"]["radius_cm"],
    "CircleWarning": profile["circle"]["delay_s"],
    "RoundSeconds": profile["capture"]["duration_s"],
    "DefaultSeed": profile["capture"]["seed"],
    "AimedFraction": profile["capture"]["aimed_fraction"],
    "ProjectileFraction": profile["capture"]["projectile_fraction"],
    "SpawnInterval": profile["capture"]["spawn_interval_s"],
}
assert f'TEXT("{profile["id"]}")' in source, "profile ID mismatch"
for name, value in expected.items():
    assert values.get(name) == value, f"{name}: source {values.get(name)} != profile {value}"
terrain = re.search(r"inline constexpr bool ProjectileBlockedByTerrain = (true|false);", source)
assert terrain and (terrain.group(1) == "true") == profile["projectile"]["blocked_by_terrain"], "terrain collision mismatch"
assert reference["id"] == "survive-lucian-reference-v1", "reference profile ID mismatch"
character_source = (ROOT / "Source/SurgeMovementLab/LabCharacter.cpp").read_text(encoding="utf-8")
assert f'TEXT("{reference["id"]}")' in character_source, "reference capture ID mismatch"
for group in ("movement", "projectile", "circle", "capture"):
    assert reference[group] == profile[group], f"reference shared {group} settings drifted"
for kind in ("dash", "blink"):
    for field, value in profile[kind].items():
        expected_value = profile[kind]["reference_cooldown_s"] if field == "cooldown_s" else value
        assert reference[kind].get(field) == expected_value, f"reference {kind}.{field} drifted"
print(f"Source/profile agreement: {len(expected)} numeric settings, terrain flag, both profile IDs and practice/reference consistency passed. This check compares constants; runtime evidence is recorded separately.")
