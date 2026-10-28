# Opt-in engine input probe

Development builds launched with `-SurviveInputProbe` bind **F8** to a short input
contract probe and **F9** to a focus observation. Neither starts automatically.
Both require a local authority controller, its active unit, a focused real game
viewport, and released RMB/S/Q. Press F8 or F9 again to cancel a running probe.
Allow ordinary window input with `-unattended -UnattendedInput` when using the
bounded rendered runner. Place the cursor over a reachable floor position first.

F8 queues this sequence through Unreal's `APlayerController::InputKey` and normal
`UPlayerInput`/`InputComponent` dispatch:

| Approximate elapsed time | Engine input event |
| --- | --- |
| 0 s | RMB press; hold |
| 1.1 / 1.2 s | S press/release; RMB remains queued down |
| 2.3 / 2.45 s | RMB release, then a fresh RMB press |
| 3.55 / 3.65 s | Q press/release; RMB remains queued down |
| 4.75 s | Final RMB release |
| 4.95 s | End observation |

Each spacing begins at the actual queued event. Hitches delay stages; they never
create catch-up events. An eight-second deadline aborts F8. Inputs dispatch on a
later frame, so queue timestamps differ from handler/command timestamps.

F9 queues one RMB press, observes for about 20 seconds, then queues its release.
The operator may switch focus using the permitted window-control tool. Natural
Unreal focus flushing remains active: the probe never reasserts a key or movement
latch after focus loss. It changes no cursor position, destination, speed or limit.

The movement gate requires both a focused viewport and an active Slate
application. The first rendered check showed that `Viewport::HasFocus()` could
remain true while another desktop app was active; Unreal's key flush still
released RMB. A scoped Slate application-activation delegate now clears the held
movement latch immediately on actual deactivation, even if background ticking
pauses. Reactivation never restores it. This also applies during normal gameplay;
the existing last destination may continue walking, but held cursor updates stop.

`Unreal.log` records probe ID/session, stage/elapsed time, queued key edges,
`InputKey`'s handled return, viewport focus, observed `IsInputKeyDown` values and
`bMoveHeld`. Transitions and 0.25-second observations contain no pass verdict.
The effective `focus` field combines app activation and viewport focus. Separate
`slate_active` and `viewport_focus` fields retain both observations. While a probe
is active, activation callbacks also log the actual `active_event` argument and
the held latch before/after handling; they do not depend on a later player tick.
Review actual command/ability events and movement in the session's JSONL beside
this external log. The probe adds no truth labels or probe fields to raw telemetry.

These are engine-simulated input events (`FInputKeyEventArgs::CreateSimulated`),
not physical mouse holds or human-player evidence. No OS input injection, window
automation, cursor movement, other app interaction or global setting is used by
the probe. Keep external window actions separate in the operator record.

Cleanup releases only probe-owned keys on cancellation, restart, unit replacement,
round termination or controller EndPlay. F8 also cancels on focus loss. The normal
movement guard and Unreal's shutdown/focus handling remain responsible for the
live movement latch. The activation delegate uses a weak UObject binding, is
registered once for each local controller, and is removed at controller EndPlay.
Probe fields, bindings and injection code are excluded from
Shipping builds. Build and runtime verification must be recorded separately.

API reviewed locally in UE5.8: `Engine/Public/InputKeyEventArgs.h` and
`Engine/Private/InputKeyEventArgs.cpp` (`CreateSimulated`),
`Engine/Classes/GameFramework/PlayerController.h` (`InputKey`), and
`Engine/Private/UserInterface/PlayerInput.cpp` (queued events/bound-key dispatch).
Application activation APIs were reviewed in
`Slate/Public/Framework/Application/SlateApplication.h` (`IsActive`,
`OnApplicationActivationStateChanged`) and its implementation. This gate observes
the game's own application; it does not inspect or control another desktop app.
