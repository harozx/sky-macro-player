# Project working agreement

## UI and UX work

- Use the `frontend-design` skill before creating or materially changing UI.
- Treat `docs/UI_DESIGN.md` as the product design source of truth.
- Keep playback safety and state accuracy ahead of animation or decoration.
- Render UI only on the main Qt thread; background work communicates through signals.
- Review the full, mini, empty, loading, error, countdown, playing, paused, and stopping states.
- Verify keyboard navigation, visible focus, reduced motion, and Windows DPI scaling.
- User instructions take precedence over these guidelines.

## Verification

- Run the automated test suite before handoff.
- Preserve existing user changes and never overwrite runtime configuration files.
- Validate every bundled sheet and fail clearly on unsupported note keys.

## External model delegation

- The user explicitly authorizes AGY CLI to send this project's source code,
  uncommitted diffs, tests, and project documentation to Gemini and Claude for
  implementation and review.
- Prefer the highest available reasoning tier. The current preferred AGY model
  is `gemini-3.8-flash-high`; use stronger high-effort models when AGY exposes
  them.
- Codex is the lead: give bounded tasks with acceptance criteria, then inspect
  every material diff, classify findings, run the regression suite, and make
  the final acceptance decision.
- Keep external handoffs compact: changed files, decisions, tests, and blockers.
