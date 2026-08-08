# Implementation Plan

## Feature

Run one canonical Trackmania Bingo game for the three participating viewers, with first-start-wins setup and process-wide shared state that keeps all live viewers synchronized on Streamlit Cloud.

## Steps

- [x] 1. Define the single canonical game model and shared-storage boundary in `bingo_service.py` (one pending setup state, one active/stopped game, immutable board/timing configuration, records, leaderboard snapshot metadata, and runtime timer state). Specify atomic first-start-wins, stop, and reset operations; do not add room IDs or role-based admin state. Validate the model and concurrency rules with focused service tests using an in-memory fake store.
- [x] 2. Make the canonical store process-wide in `bingo_service.py` (alongside the existing shared timer and polling coordinator) and document the deployment boundary: all viewers in the same running Streamlit app process share state, while process restarts clear the game. Do not add external storage, storage secrets, or persistence dependencies. Validate that independent viewer calls observe the same store instance and that a fresh store starts empty.
- [x] 3. Move setup configuration out of browser-local state in `streamlit_bingo_page.py`: make shuffle and pending campaign/timing settings update the shared pending game state, allow any participating viewer to configure it, and make the first successful start atomically establish the game for everyone. Add focused tests for two independent session-state mappings observing the same pending configuration and for concurrent first-start attempts.
- [x] 4. Migrate start, stop, and reset from `start_session_in_state`, `stop_session_in_state`, and `reset_session` to single-game operations. Freeze the selected board seed/layout, tracks, start time, and timing settings at start; make reset explicitly return to pending setup; ensure a new viewer never creates a private game. Validate lifecycle transitions, late joins, refreshes, reconnects, and attempts to start while a game is already active.
- [ ] 5. Make leaderboard polling and Bingo transitions canonical: have one game-scoped poll/update path persist the processed API snapshot, record de-duplication, ownership, winner, and status, while viewers only read the resulting game snapshot. Preserve shared request pacing, cache reuse, bounded retries, and server-side time calculations. Add service tests proving that separate viewers converge on identical records and board state and that repeated viewer reruns do not duplicate updates or API requests.
- [ ] 6. Define the clean-restart flow for the single game. Treat an empty process-wide store after a Streamlit restart as setup mode; when any player starts a new game, load the selected campaign tracks and poll the current leaderboard through the normal API path, using the newly selected configuration and board seed. Do not attempt to recover the previous board, start time, records, or timers. Validate that a restart can begin a fresh game from current API data and cannot resurrect stale in-memory state.
- [ ] 7. Update the Streamlit rendering and controls to read the canonical game on every rerun, including the shared board preview, active board, deadlines, records, player timers, status, and stop/reset results. Cover late-entry, reconnect, and cross-viewer convergence behavior with focused `test_streamlit_bingo_page.py` cases, and revise existing session-state tests to assert shared-game delegation rather than private-session mutation.
- [ ] 8. Document Streamlit Cloud setup, the process-wide state boundary, single-game lifecycle, first-start-wins behavior, and the clean-restart/new-game behavior in `README.md` and `DEVELOPER.md`. Make clear that no external game-state storage is required and that a restart intentionally starts from fresh configuration and current API data. Add the user-visible change to `development-docs/CHANGELOG.md` only after implementation is complete.

## Completion Checks

- `uv run --active python -m pytest`
- `uv run --active python -m compileall .`
- `uv run --active pre-commit run --all-files`
- Verify the focused service and Streamlit tests cover two independent viewers, late joining, refresh/reconnect, canonical polling, first-start-wins lifecycle actions, process-wide store isolation, and clean-restart/new-game behavior.
- Add a concise user-visible changelog entry when the feature is complete.
- Create one clean local commit through the `create-commit` skill; do not push from that workflow.

