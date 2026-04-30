# Quant Hunter Installer Build

## Quick Start

Build the portable application directory:

```powershell
.\build_exe.bat
```

Build an installable EXE package:

```powershell
.\build_exe.bat --installer
```

You can also use:

```powershell
.\build_installer.bat
```

## Output Files

Installer builds are written to `releases\`.

Recommended files:

- `releases\quant_hunter_setup_latest.exe`
- `releases\quant_hunter_portable_latest.zip`
- `releases\quant_hunter_bundle_latest.zip`

Timestamped history files are kept in the same folder for traceability.

## Build Chain

1. `build_exe.bat --app-only` runs PyInstaller and produces `dist\quant_hunter\`.
2. `tools\build_release_package.ps1` packages the portable ZIP and bundle ZIP.
3. If `Inno Setup 6` is installed, the script prefers it and creates a standard Windows installer with uninstall support.
4. If Inno Setup is not available, the script tries `IExpress`.
5. If `IExpress` does not produce the installer, it falls back to a PyInstaller-based installer stub.

## Notes

- `quant_hunter_setup_latest.exe` is the main file to send to end users.
- 7-Zip self-extracting EXE generation is optional. If the SFX module is missing, the main installer still succeeds.
- Recommended compiler path: `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`
