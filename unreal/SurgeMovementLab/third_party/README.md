# Reuse in Survive

Only the ideal linear dodge-window calculation from `evaluate()` in
[dcass5212/lol-dodge-calc index.html](https://github.com/dcass5212/lol-dodge-calc/blob/af8c5d40ff8eda343cc0e80af27f4304cf9343d5/index.html)
is adapted in `../telemetry/dodge_window.py`. Upstream commit:
`af8c5d40ff8eda343cc0e80af27f4304cf9343d5`; reviewed October 25, 2026.
The complete MIT notice is retained alongside this file. No upstream scripts,
dependencies, game assets or repository setup commands were executed.

The helper is for initial difficulty calibration. It is not a general collision
solver and is not used as detection evidence or a claim of League equivalence.

Qrytics/dodgeLoL was a behavior reference (cursor clamping, cooldown feedback,
mixed threats); no code/assets were copied because no reuse license was found.
The Unreal game and concept preview implement those ideas independently.
