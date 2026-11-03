# Security policy

## Supported versions

Only the latest commit on `main` is supported. There are no releases or older branches to patch.

## Reporting a vulnerability

Please report it privately, not in a public issue, pull request or discussion: open the repository's **Security** tab and choose **Report a vulnerability**. That opens a private report that only the maintainer and you can see. Say what you found, where, and how to reproduce it. Do not include anyone's real data or a working key in the report.

You will get an answer there. Please give the maintainer a reasonable time to fix a problem before you disclose it.

## What is and is not at risk

- **The hosted demo is static.** [kamil-shirinov.github.io/Archivist](https://kamil-shirinov.github.io/Archivist/) is plain files published by GitHub Pages from `main`: it has no keys, no server code, no upload box and no model call, and what it shows are recorded runs of synthetic or public-domain pages.
- **No secret is in the repository.** `.env` is ignored and never committed ([`.env.example`](.env.example) lists names only). If you find a key, a token or personal data in the code or its history, report it the same way and do not use it.
- **The local live-reading app** (`archivist.live`) listens on loopback only, offers development pages only, and spends only from the keys and caps its owner sets ([docs/live-reading.md](docs/live-reading.md)).
