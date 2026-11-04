# My-EPG GitHub Actions package

Publishes a compressed XMLTV file at `https://55corndog1337.github.io/My-EPG/epg.xml.gz` after GitHub Pages deployment.

## Installation

1. Upload `build_epg.py`, `matches.csv`, and `.github/workflows/update-epg.yml` to the root of `55Corndog1337/My-EPG` (preserve `.github/workflows/` directory structure). Do not upload the playlist itself.
2. Repository **Settings → Secrets and variables → Actions → New repository secret**: name `PLAYLIST_URL`, value your complete M3U URL.
3. Repository **Settings → Pages → Build and deployment → Source**: select **GitHub Actions**.
4. **Actions → Update EPG → Run workflow**. Wait for the build/deploy job to complete. It then runs about every 12 hours (scheduled runs may be delayed).
5. Add `https://55corndog1337.github.io/My-EPG/epg.xml.gz` to the IPTV player as its XMLTV URL.

## Important limits

- `matches.csv` comes from the previously generated matching audit; matches have **not** been independently verified against the latest remote playlist or feeds.
- The generator uses the original nonblank `tvg-id` values from the playlist so the guide matches those channels. Playlist channels with **blank `tvg-id` values cannot receive guide data without changing the playlist IDs**. Some duplicate IDs may also require playlist corrections. This package does not modify or publish your M3U.
- The guide will be **public** through GitHub Pages. Do not upload credentials or private playlist files to the public repository. The playlist URL is stored in a GitHub Actions secret, but the generated programme information is public.
- A scheduled build fails rather than replacing the published guide with a partial/empty file if a source download fails.
- Actions runs and Pages bandwidth/storage are subject to GitHub plan and usage policies.
