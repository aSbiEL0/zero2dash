# Currency Salvage Manifest

Created on `codex/restore-bad-merge` on 2026-03-09 to preserve currency-related repo state before restoring the active implementation from `origin/codex/gbp-pln-currency`.

## Source Refs

| Snapshot | Ref | Commit |
| --- | --- | --- |
| `main/` | `origin/main` | `ee9a01a1215e3513591db0d7b63320d16afd0f13` |
| `feature-branch/` | `origin/codex/gbp-pln-currency` | `d8c9374303195f10becb91fbeafa171e2aca1bd2` |

## File Presence By Ref

| File | `origin/main` | `origin/codex/gbp-pln-currency` |
| --- | --- | --- |
| `scripts/currency-rate.py` | yes | yes |
| `scripts/currency.py` | yes | yes |
| `images/currency-bkg.png` | yes | yes |
| `cache/currency_state.json` | yes | no |
| `systemd/currency-update.service` | yes | yes |
| `systemd/currency-update.timer` | yes | yes |

## Notes

- `images/current-currency.png` is a generated runtime artefact and is not restored into the active branch tree.
- Historical evidence shows `images/current-currency.png` existed earlier in history and was later deleted, so it is treated as forensic output rather than source.
- `cache/currency_state.json` is preserved only inside this salvage snapshot because it is transient runtime state.