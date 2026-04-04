# NASA App Closeout Archive

Archived: 2026-04-04
Scope: standalone NASA / ISS app delivery closeout

Summary:
- NASA app startup, loading, crew pagination, offline country lookup, and page rendering fixes were completed and accepted.
- The app now runs correctly on the Pi per operator confirmation.

Delivered outcomes:
- crew page uses only bottom dots for pagination
- loading page text box remains removed
- stale badges and hard error pages are gated behind a 10-minute API failure grace window
- `Currently over:` shows the local country name on land and `Ocean` over water
- raw geoBoundaries country files are kept local under `nasa-app/assets/countries/` and are not tracked in git because the shapefile is too large for GitHub
- active page indicator dot uses `#44a5ff`

Operational notes:
- Pi deployments must copy the local country boundary files into `nasa-app/assets/countries/`
- `nasa-app/api_failure_state.json` may retain failure state between runs and can be reset for a clean startup state

Known residuals at closeout:
- one unrelated pre-existing test mismatch remained around `test_text_box_constants_match_new_guide`
- repository theme assets had unrelated working-tree changes outside the NASA slice at closeout time

Archived so the active control plane can stay minimal for the next task.
