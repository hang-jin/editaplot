# Read the installed Skill's JSON pointer without needing a global Python.
# Keep paths and forwarded arguments as Unicode data, never as shell source.
$ErrorActionPreference = 'Stop'
$managedPython = $null
try {
    $engineRoot = $env:EDITAPLOT_ENGINE_HOME
    if ([string]::IsNullOrWhiteSpace($engineRoot)) {
        $configPath = Join-Path $env:EDITAPLOT_LAUNCHER_ROOT '.editaplot-local.json'
        if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { exit 64 }
        $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($config.engine_home -isnot [string]) { exit 64 }
        $engineRoot = $config.engine_home
    }
    if ([string]::IsNullOrWhiteSpace($engineRoot)) { exit 64 }
    $managedPython = Join-Path $engineRoot '.editaplot-venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $managedPython -PathType Leaf)) { exit 64 }
    if (-not (Test-Path -LiteralPath $env:EDITAPLOT_BOOTSTRAP -PathType Leaf)) { exit 64 }
    $probe = "import platform,struct,sys;raise SystemExit(0 if platform.python_implementation()=='CPython' and struct.calcsize('P')*8==64 and sys.version_info[:2] in ((3,10),(3,11),(3,12)) else 1)"
    & $managedPython -I -c $probe > $null 2> $null
    if ($LASTEXITCODE -ne 0) { exit 64 }
} catch {
    # Continue normal discovery for a missing, stale, or invalid local pointer.
    exit 64
}

# The Python bootstrap still checks the dependency lock and managed fingerprint.
$env:PYTHONIOENCODING = 'utf-8'
& $managedPython $env:EDITAPLOT_BOOTSTRAP @args
exit $LASTEXITCODE
