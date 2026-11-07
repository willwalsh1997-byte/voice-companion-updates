# Releases-only repository (retired)

Retired on November 7, 2026. The project moved to the willwalsh1997-byte GitHub account, and
updates now come from Cloudflare R2 at updates.voicecompanionapp.com (see
`voice_companion/GITHUB AUTOMATED BUILDS.txt`). The source repository can be made private at any
time: publishing no longer needs a public repository. The rest of this page is history.

Installed copies of Voice Companion read updates from a public repository that holds only the
installers and the update file, and no source code. That lets the source repository become
private while updates keep reaching everyone.

## Where things are

- **Releases-only repository:** `willwalsh14-hub/voice-companion-releases`. It is public and holds no code.
- **Source repository:** `willwalsh14-hub/voice-companion-updates`. It can be made private once the releases repository works.
- **Update feed:** `voice_companion/update-settings.json`. `manifest_url` is the releases repository. `fallback_urls` is the source repository, used only while it is public.
- **Publishing:** `publish_release.py` publishes each release to every feed. The source repository uses the workflow's own token. The releases repository uses the `RELEASES_TOKEN` secret.

## One-time setup (Will)

1. Create the repository on GitHub. Choose **New repository**, name it `voice-companion-releases`, choose **Public**, and add a README so it is not empty. Do not add any code.
2. Create a token that can publish there. On GitHub, open **Settings**, **Developer settings**, **Personal access tokens**, **Fine-grained tokens**, then **Generate new token**.
   - Name: Voice Companion releases.
   - Expiration: the longest offered. Note the date: releases to this repository stop when it expires.
   - Repository access: **Only select repositories**, then `voice-companion-releases`.
   - Permissions: **Contents: Read and write**. Nothing else.
3. Copy the token. In the source repository, open **Settings**, **Secrets and variables**, **Actions**, then **New repository secret**. Name it `RELEASES_TOKEN`, and paste the token.
4. Tell Claude. The next release publishes to both repositories, and Claude checks the files arrived.

## Making the source repository private (Will)

Do this only after Claude confirms a release reached the releases repository, and after most copies have taken an update since then.

1. In the source repository, open **Settings**, then **General**.
2. At the bottom, under **Danger Zone**, choose **Change visibility**, then **Make private**.

Then:

- Build time on a private repository is billed. GitHub Free includes $12 a month, about 1,200 Windows minutes. A release uses about 100 Windows minutes, so that covers about 12 releases a month. At about 100 releases a month that is $90 to $100. A self-hosted runner on a spare Windows PC is free.
- Testers file bugs on the [Voice Companion issues page](https://github.com/willwalsh14-hub/voice-companion-releases/issues/new/choose) in the releases repository.
- The privacy policy contact is now willwalsh14@gmail.com, and a copy of the policy is in the releases repository.
- Before the switch, set the Chrome Web Store privacy policy link to the [privacy policy in the releases repository](https://github.com/willwalsh14-hub/voice-companion-releases/blob/main/PRIVACY-POLICY.md).
- Copies older than the release that moved the feed can no longer update, and need the installer once.
