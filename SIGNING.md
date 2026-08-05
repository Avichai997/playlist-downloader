# Free Windows code signing (SignPath OSS)

Same optional setup as [dwfx2pdf](https://github.com/Avichai997/dwfx2pdf/blob/main/SIGNING.md).
Once configured, every tagged release can sign `PlaylistDownloader.exe` automatically.

## One-time setup

1. Apply at https://about.signpath.io/product/open-source for
   `https://github.com/Avichai997/playlist-downloader`
2. In SignPath, note Organization ID, project slug, and signing policy slug
3. Add GitHub Actions **variables** `SIGNPATH_ORGANIZATION_ID`, `SIGNPATH_PROJECT_SLUG`,
   `SIGNPATH_POLICY_SLUG` and **secret** `SIGNPATH_API_TOKEN`
4. Extend `.github/workflows/build.yml` with the SignPath step from dwfx2pdf's workflow
   (copy the `Code sign (SignPath OSS)` block)

Until then, Windows builds ship unsigned — use **More info → Run anyway** on first launch.
