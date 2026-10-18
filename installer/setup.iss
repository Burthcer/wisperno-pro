; Wisperno Pro Windows installer (Inno Setup 6). A SEPARATE app from the
; original Wisperno: different AppId, name, install folder, exe and mutex, so
; installing it never upgrades, replaces or uninstalls an installed Wisperno.
; The identity values below must match src/branding.py (tests/test_branding.py). Compiled via scripts/build_installer.py,
; which passes /DMyAppVersion=<version> read from src/__version__.py - never hardcode
; a version here, it would drift out of sync with the actual build.
#ifndef MyAppVersion
  #define MyAppVersion "1.6.0"
#endif
#define MyAppName "Wisperno Pro"
#define MyAppPublisher "Wisperno Pro"
#define MyAppExeName "WispernoPro.exe"
; Overridden by build_installer.py to a staged directory containing only the
; ACTIVE model preset (not every preset ever downloaded to this dev machine's
; models\ cache) - see build_installer.py's docstring for why staging exists.
#ifndef SourceDir
  #define SourceDir "..\Final App\v" + MyAppVersion
#endif

[Setup]
; Fixed GUID - the one thing that must never change between versions, it's
; how Windows/Inno recognize "this is the same app" for in-place upgrades.
; No prior real installation exists with the earlier placeholder GUID this
; installer shipped with before its first real user, so swapping to this one
; is safe - it must never change again after this.
; Wisperno Pro's own GUID (the original Wisperno is 8F2B1C94-...). Never
; reuse the original's: Windows would treat Pro as an upgrade of it.
AppId={{C6D1A7E3-5B24-4F8E-A1D9-73E2B0F4C518}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Per-user install dir (not Program Files) - a background hotkey app has no
; business asking for admin elevation on every install/update.
PrivilegesRequired=lowest
OutputDir=..\Final App
OutputBaseFilename=WispernoPro-Setup-v{#MyAppVersion}
; No compression, deliberately - same reasoning as scripts/package_portable.py's
; ZIP_STORED choice: this bundle is almost entirely already-compressed binary
; data (GGUF weights, CTranslate2 tensors, CUDA DLLs), where LZMA2 buys back a
; percent or two of size at the cost of a genuinely long compression pass over
; several GB (observed: still compressing after 10+ minutes on just the torch
; DLLs, before ever reaching the model weights).
Compression=none
; Windows/Inno hard-cap a single Setup.exe at ~4.2GB - and this app's own CUDA/
; PyTorch/llama.cpp runtime (_internal\, ~5GB) alone already exceeds that,
; before models are even added. Disk spanning is Inno's sanctioned mechanism
; for exactly this: one WispernoPro-Setup-v{#MyAppVersion}.exe launcher plus
; numbered .bin volumes, all of which must ship together in the same folder -
; not literally one file, but one install experience (double-click the .exe,
; the volumes are picked up automatically from beside it).
DiskSpanning=yes
; 1.9 GB slices so every part fits GitHub's 2 GB release-asset limit.
DiskSliceSize=1900000000
SetupIconFile=..\assets\icons\wisperno.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
; Tells Windows Explorer to refresh its icon cache when setup finishes, so the desktop and Start menu
; shortcuts show the new logo straight away instead of the old (or a blank) one until the next sign-in.
ChangesAssociations=yes
; Matches src/single_instance.py's actual MUTEX_NAME exactly - Setup detects
; a running instance and prompts to close it before continuing the upgrade.
AppMutex=Local\WispernoPro_SingleInstance_Mutex_4417
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[InstallDelete]
; Builds before v1.3.0 bundled all of PyTorch (about 3.6 GB) in _internal\torch; the app no longer uses it. An in-place
; upgrade overwrites files but never removes ones a newer version stopped shipping, so without these lines every
; upgraded PC would keep 3.6 GB of dead weight. Only these two folders are removed - never settings, history or models.
Type: filesandordirs; Name: "{app}\_internal\torch"
Type: filesandordirs; Name: "{app}\_internal\torchaudio"

[Files]
; App binaries + PyInstaller runtime deps - always refreshed on upgrade.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "config\*,models\*,logs\*"; Flags: ignoreversion recursesubdirs createallsubdirs

; Model weights - always refreshed on upgrade, same as the app binaries
; (grouped with them, not with user state: a partial/corrupt models\ folder
; from an earlier failed install must never survive silently into a later
; "upgrade" via a skip-if-present flag).
Source: "{#SourceDir}\models\*"; DestDir: "{app}\models"; Flags: ignoreversion recursesubdirs createallsubdirs

; User state - never clobbered on upgrade. wisperno.db itself lives entirely
; outside {app} (%APPDATA%\WispernoPro\wisperno.db - see src/config.py's
; get_db_path()) - %APPDATA%\WispernoPro\wisperno.db for Pro - so the installer never touches it at all; only
; config.yaml/dictionary.json live inside {app} and need the explicit guard.
Source: "{#SourceDir}\config\config.yaml"; DestDir: "{app}\config"; Flags: onlyifdoesntexist
Source: "{#SourceDir}\config\dictionary.json"; DestDir: "{app}\config"; Flags: onlyifdoesntexist

[Dirs]
Name: "{app}\logs"

[Icons]
; WorkingDir explicit on both - Inno's own default when omitted is not
; guaranteed to be {app} on every Windows version/shell config, and every
; relative-path assumption anywhere in the dependency chain (torch/faster-
; whisper/llama-cpp-python, not just this app's own code) is safer with it
; pinned down explicitly rather than left to chance.
Name: "{autoprograms}\{#MyAppName}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Description: "Launch Wisperno Pro now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"

[Messages]
WelcomeLabel1=Welcome to the [name] Setup Wizard
WelcomeLabel2=This will install [name/ver] on your computer. It installs alongside the original Wisperno and does not change or replace it.%n%nWisperno Pro - Local Ultra-Fast Dictation & Voice Intelligence.%n100%% Private, Offline Speech-to-Text Powered by Whisper & Local SLMs. No audio or text ever leaves this machine.%n%nThis installation requires approximately 8.5 GB of free disk space for the application and its offline neural network models (speech recognition + local language model).%n%nIt is recommended that you close all other applications before continuing.
; This app isn't code-signed, so Windows Defender/SmartScreen scans the newly-
; extracted exe + its DLLs the first time it's ever run - measured at ~26s of
; apparent "nothing happening" before the very first log line, vs. 2s on every
; run after (the file's already-scanned verdict is cached). Telling the user
; up front (right where "Launch Wisperno now" is offered) turns that from
; "did it freeze?" into an expected, one-time wait.
FinishedLabel=Setup has finished installing [name] on your computer.%n%nThe application may take up to 30 seconds to fully start the very first time it runs - Windows scans new, unsigned programs on their first launch. This only happens once; every launch after is fast.%n%nThe application may be launched by selecting the installed icons.
