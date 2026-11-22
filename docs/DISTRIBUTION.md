# Offline distribution

The repository and normal GitHub workflow builds the source bundle. A complete
offline package is assembled on a Windows build machine because AstrBot,
NapCat/QQ, Python and GPT-SoVITS are large third-party runtimes.

Build the source-only bundle:

```powershell
python scripts/build_offline_package.py --output dist
```

Build the complete offline package:

```powershell
python scripts/build_offline_package.py `
  --output dist `
  --astrbot-tool "$env:APPDATA\uv\tools\astrbot" `
  --napcat-shell "C:\tafei\napcat\NapCat.52230.Shell" `
  --voice-engine "C:\tafei\voice\GPT-SoVITS-run" `
  --python-installer "C:\downloads\python-3.12.10-amd64.exe"
```

The builder:

- excludes `.secrets`, API configuration, chat databases, logs and user memories;
- excludes voice weights, reference audio, personal sticker files and images;
- excludes the old WeChat runtime and debug screenshots;
- splits ZIP output before 1.8 GB per part;
- writes `SHA256SUMS.json` for release verification;
- keeps the complete corresponding source inside the package.

Upload the `dist\tafeiyu-offline-part*.zip` files and `SHA256SUMS.json` as
GitHub Release assets. GitHub Actions handles source releases and verification;
large runtime bundles are produced locally because they exceed normal repository
storage limits.

Third-party runtime licenses and notices must remain in the package. Voice
model weights and character reference audio are never included.
