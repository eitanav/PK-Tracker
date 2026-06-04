# Public Release Checklist

This repository is ready to be made public once the final repository settings are confirmed.

## Already completed

- `LICENSE` exists and uses Apache License 2.0.
- `NOTICE` exists and includes project attribution and safety scope language.
- `DISCLAIMER.md` exists and clarifies that the software is not medical advice, not a medical device, and must not be used for alcohol/driving or prescription-medication decisions.
- `README.md` includes a License section that points to `LICENSE` and `DISCLAIMER.md`.
- The project documentation already explains that all values are estimates from population-average models.

## Recommended before clicking Public

- Confirm that Windows release assets exist under this repository, not an older repository name.
- In `README.md` and `README.he.md`, update any hard-coded release links that still point to `eitanav/coffe-thing` so they point to `eitanav/PK-Tracker`, or replace them with relative links to `../../releases/latest` until the release assets are final.
- Consider renaming the default branch to `main`; the current default branch name appears automation-generated and is not ideal for a public repository.
- Run a final secret scan locally before publishing:

```bash
git grep -n -i "api_key\|secret\|token\|password\|client_secret\|private key\|AIza"
```

- Verify that no local database, personal logs, or generated build artifacts were accidentally committed.

## Visibility change path

GitHub repository page → Settings → General → Danger Zone → Change repository visibility → Public.

