# SeedScope

SeedScope is a desktop dashboard for monitoring and migrating qBittorrent torrents between hosts.

## Highlights

- Multi-client qBittorrent monitoring (dashboard, activity, insights)
- Guided torrent transfer workflow between hosts
- Progress tracking during copy and recheck
- Client management UI (add/edit/remove hosts)

## Requirements

- Windows 10/11
- Python 3.11+ recommended
- qBittorrent Web UI enabled on each host

## Run From Source

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.main
```

## Data And Logs

- Database: `%USERPROFILE%\.seedscope\seedscope.db`
- Logs: `%USERPROFILE%\.seedscope\logs\seedscope.log`

## Build EXE And Installer (PyInstaller + Inno Setup)

1. Install Inno Setup 6.
2. Ensure your project icon exists at `app/assets/icon.png` or `app/icon.png` (optional but recommended).
3. Run:

```powershell
.\scripts\build_installer.ps1 -Version 0.1.0
```

Outputs:

- App folder: `dist\SeedScope\`
- Installer: `dist\installer\SeedScope-Setup-<version>.exe`

## Repository

- GitHub: `https://github.com/Kevnaut/SeedScope`
