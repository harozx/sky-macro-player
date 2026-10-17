# Macro Player UI design system

## Product focus

Macro Player is a compact Windows control desk for Sky and Heartopia players. Its
primary job is to let a player find a sheet and control playback safely without
pulling attention away from the game.

## Visual direction: Sky Instrument Console

The interface borrows from night skies, instrument panels, and musical motion.
It should feel calm and precise rather than like a neon game launcher. The one
signature element is the **Note Runway**: a thin playback timeline whose note
clusters move toward a fixed playhead. Other surfaces stay restrained.

### Core tokens

| Token | Value | Role |
| --- | --- | --- |
| Cloud Ink | `#101722` | Application canvas |
| Deep Slate | `#192536` | Primary surfaces |
| Lifted Slate | `#24344A` | Raised controls |
| Moon Mist | `#E7EFF7` | Primary text |
| Sky Blue | `#82CFFF` | Focus and selection |
| Sunset Apricot | `#FFB287` | Primary action and countdown |

Semantic colors may supplement the core palette for success, warning, and
danger, but should not be used as decoration.

### Typography

- Bahnschrift SemiCondensed: screen titles and song names.
- Segoe UI Variable or Segoe UI: body text and controls.
- Cascadia Mono: hotkeys, timestamps, counters, and diagnostic values.

### Layout

The full window uses a navigation rail, a flexible workspace, an optional queue
panel, and a playback dock that remains visible on every screen.

```text
+---------------- Search and filters -------------------------+
| Library    | Song list and current context   | Queue         |
| Shortcuts  | Empty/loading/error states      |               |
| Settings   |                                  |               |
+------------+----------------------------------+---------------+
| Song / queue position | Note Runway | Back Play Next Stop   |
+--------------------------------------------------------------+
```

The mini overlay keeps the current song, countdown/progress, pause/resume, next,
emergency stop, pin, and expand controls. It must remain usable at 100-200% DPI.

Settings and hotkey forms scroll vertically when height is constrained. At
narrow widths the queue may collapse, but the navigation rail always exposes a
control to reopen it.

### v3 additions

- **Dock tools** under the runway: speed (0.5×–1.5×), A / B / clear section
  loop, Preview, Keyboard. On narrow windows (< 900 px) the runway and its A–B
  controls are hidden together; speed and Preview stay.
- **Key strip**: an optional 3×5 grid of the in-game keys between the pages and
  the dock. Lit cells use Sunset Apricot fill plus bold text, so state is not
  carried by color alone.
- **Preview mode** prefixes every status with “Xem trước” and never sends
  operating-system input. It cannot be toggled during a session.
- **Song detail panel** below the list (hidden under 520 px height) shows
  length, notes, density/difficulty, play count and the 2Key/3Key choice.
- **Library header** hides its eyebrow and summary under 470 px height so the
  list keeps room at 200% scaling (960×540 logical on a 1080p screen). The
  window minimum is 760×520.
- **Dialogs** (import preview, first-run guide, command palette, window picker)
  reuse the same tokens; primary actions use Sunset Apricot.

## Interaction principles

- Play, pause, stop, and next remain one action away from every screen.
- Controls use plain Vietnamese verbs and report the same verb on completion.
- Errors name the affected file or setting and offer a concrete recovery action.
- Destructive list actions offer undo where practical.
- Hotkey capture detects reserved keys and conflicts before saving.
- State is never communicated by color alone.
- Motion responds to playback or a user action; reduced motion disables ambient
  timeline movement while preserving progress information.
- The complete window must remain readable; background opacity never makes text
  or focus indicators translucent beyond an accessible floor.

## Required states

Idle, empty library, no search results, loading, validating, selected, countdown,
playing, paused, stopping, skipped, completed, queue complete, rebinding, hotkey
conflict, missing file, unsupported sheet, focus-lock target missing, focus-paused,
refocused, and unexpected playback error.

## Focus lock (Sky by default, or a user-chosen game)

- Focus lock is opt-in and names its safety behavior beside the toggle.
- Playback begins only after the target Sky window is found and activated.
- Losing Sky focus creates a distinct `focus_paused` state; it never replaces a
  pause the user requested manually.
- Automatic resume occurs only after the same Sky window becomes foreground
  again and the user has enabled that option.
- Failure copy tells the player to open or click Sky; the app never attempts
  driver-level or background input injection.

## Quality bar

- Visible focus and logical tab order for every interactive control.
- Minimum 36 px target size; primary mini-player controls are at least 44 px.
- Text contrast target of 4.5:1 or better.
- Correct layout at 100%, 125%, 150%, and 200% Windows scaling.
- No Qt widget access from a worker thread.
- UI state is tied to a playback session ID so stale callbacks cannot render.
