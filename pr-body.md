## Summary
- require an explicit scheme for remote Pi-hole hosts and validate TLS/timeout-related configuration
- improve Pi-hole auth handling in `piholestats_v1.3.py`, including v6-session vs legacy-token mode detection and clearer auth/transport failure reporting
- tighten Google Calendar and Photos OAuth handling around loopback redirects, Desktop OAuth clients, and token scope parsing
- add a Photos `--auth-only` mode and improve token-path separation from the calendar flow
- update `.env.example` and `README.md` to document the revised Pi-hole and Google OAuth setup

## Testing
- not run from this Codex environment

