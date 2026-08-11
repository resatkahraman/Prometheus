# DESKTOP-PKG-001 - Windows Development Packaging

Status: COMPLETE

## Objective

Provide a normal installable and launchable Windows Prometheus application so daily use does not require PowerShell, npm, cargo or `tauri dev`.

## Packaging contract

- NSIS is the only bundle target; MSI and custom portable launchers are out of scope.
- Installation mode is `currentUser`, avoiding unnecessary elevation.
- Product identity remains Prometheus, version `0.1.0`, identifier `com.resatkahraman.prometheus`.
- Installer languages are exactly Turkish and English, with the normal installer language selector enabled.
- Start Menu integration uses the normal Prometheus entry without a publisher subfolder.
- The canonical generated `icons/icon.ico` brands both installer and uninstaller.
- WebView2 uses Tauri's default prerequisite handling; no runtime is bundled or skipped.
- The development installer is unsigned; Windows may show an Unknown Publisher or SmartScreen warning.
- No custom NSIS template or installer hooks are used.

## User validation

Build with:

```text
npm.cmd run tauri build -- --bundles nsis
```

Expected output class:

```text
desktop/src-tauri/target/release/bundle/nsis/*-setup.exe
```

User validation completed successfully. `npm.cmd ci` passed with 73 packages installed and 0 vulnerabilities. `npm.cmd run tauri build -- --bundles nsis` passed with exit code 0. The release application and NSIS installer passed; generated installer: `Prometheus_0.1.0_x64-setup.exe`. Turkish/English installer selection, current-user installation, Start Menu entry, desktop shortcut, normal Windows launch, terminal-free launch, close and relaunch from the installed application all passed. Uninstallation remains covered by the normal NSIS flow.

The package does not expand application authority: webview filesystem, shell, process and network restrictions and the bounded `desktop_bootstrap` command remain unchanged.

The package is unsigned; code signing is not configured yet, and production signing/updater work remains future release work. Do not imply production signing or auto-update support.

## Next

`DESKTOP-002 - Secure Core Transport and Live Command Surface`.
