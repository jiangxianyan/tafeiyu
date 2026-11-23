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
- excludes transient watchdog/login state and stale `.bot_runtime` launch files;
- excludes voice weights, reference audio, personal sticker files and images;
- excludes the old WeChat runtime and debug screenshots;
- names source-only output `tafeiyu-source-part*.zip`;
- names complete runtime output `tafeiyu-offline-part*.zip`;
- splits ZIP output before 1.8 GB per part;
- writes `SHA256SUMS.json` for release verification;
- keeps the complete corresponding source inside the package.

GitHub Actions uploads source-only archives as `tafeiyu-source-part*.zip`.
These are not installable desktop bundles. Upload the complete
`dist\tafeiyu-offline-part*.zip` files and `SHA256SUMS.json` manually for a
full runtime release. Large runtime bundles are produced locally because they
exceed normal repository storage limits.

Third-party runtime licenses and notices must remain in the package. Voice
model weights and character reference audio are never included.

The Python installer is optional when the release is distributed to users who
already have Python 3.12. The package manifest records whether the installer is
included; the README must state that requirement when it is omitted.
