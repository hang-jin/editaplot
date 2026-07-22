@echo off
setlocal

rem EditaPlot Windows launcher. This file needs no Python command on PATH.
set "EDITAPLOT_LAUNCHER_ROOT=%~dp0"
set "EDITAPLOT_BOOTSTRAP="
set "EDITAPLOT_PYTHON_PROBE=import platform,struct,sys;raise SystemExit(0 if platform.python_implementation()=='CPython' and struct.calcsize('P')*8==64 and sys.version_info[:2] in ((3,10),(3,11),(3,12)) else 1)"

if exist "%EDITAPLOT_LAUNCHER_ROOT%skill\editaplot\scripts\bootstrap_editaplot.py" set "EDITAPLOT_BOOTSTRAP=%EDITAPLOT_LAUNCHER_ROOT%skill\editaplot\scripts\bootstrap_editaplot.py"
if not defined EDITAPLOT_BOOTSTRAP if exist "%EDITAPLOT_LAUNCHER_ROOT%scripts\bootstrap_editaplot.py" set "EDITAPLOT_BOOTSTRAP=%EDITAPLOT_LAUNCHER_ROOT%scripts\bootstrap_editaplot.py"

if not defined EDITAPLOT_BOOTSTRAP (
  echo {"ok":false,"error":{"code":"bootstrap_missing","message":"EditaPlot bootstrap_editaplot.py was not found."}} 1>&2
  exit /b 3
)

rem 1. Explicit override.
if not defined EDITAPLOT_PYTHON goto launcher_312
"%EDITAPLOT_PYTHON%" -c "%EDITAPLOT_PYTHON_PROBE%" >nul 2>nul
if errorlevel 1 goto launcher_312
"%EDITAPLOT_PYTHON%" "%EDITAPLOT_BOOTSTRAP%" %*
exit /b %errorlevel%

:managed_runtime
rem 6. Last-resort fallback. The Python bootstrap rechecks the managed fingerprint.
if exist "%EDITAPLOT_LAUNCHER_ROOT%runtime\.editaplot-venv\Scripts\python.exe" goto run_repo_managed
if exist "%EDITAPLOT_LAUNCHER_ROOT%.editaplot-venv\Scripts\python.exe" goto run_root_managed
goto no_python

:run_repo_managed
"%EDITAPLOT_LAUNCHER_ROOT%runtime\.editaplot-venv\Scripts\python.exe" -c "%EDITAPLOT_PYTHON_PROBE%" >nul 2>nul
if errorlevel 1 goto run_root_managed_if_present
"%EDITAPLOT_LAUNCHER_ROOT%runtime\.editaplot-venv\Scripts\python.exe" "%EDITAPLOT_BOOTSTRAP%" %*
exit /b %errorlevel%

:run_root_managed_if_present
if exist "%EDITAPLOT_LAUNCHER_ROOT%.editaplot-venv\Scripts\python.exe" goto run_root_managed
goto no_python

:run_root_managed
"%EDITAPLOT_LAUNCHER_ROOT%.editaplot-venv\Scripts\python.exe" -c "%EDITAPLOT_PYTHON_PROBE%" >nul 2>nul
if errorlevel 1 goto no_python
"%EDITAPLOT_LAUNCHER_ROOT%.editaplot-venv\Scripts\python.exe" "%EDITAPLOT_BOOTSTRAP%" %*
exit /b %errorlevel%

:launcher_312
rem 2. Windows Python Launcher, highest verified minor first.
where py.exe >nul 2>nul
if errorlevel 1 goto path_python
py -3.12 -c "%EDITAPLOT_PYTHON_PROBE%" >nul 2>nul
if errorlevel 1 goto launcher_311
py -3.12 "%EDITAPLOT_BOOTSTRAP%" %*
exit /b %errorlevel%

:launcher_311
py -3.11 -c "%EDITAPLOT_PYTHON_PROBE%" >nul 2>nul
if errorlevel 1 goto launcher_310
py -3.11 "%EDITAPLOT_BOOTSTRAP%" %*
exit /b %errorlevel%

:launcher_310
py -3.10 -c "%EDITAPLOT_PYTHON_PROBE%" >nul 2>nul
if errorlevel 1 goto path_python
py -3.10 "%EDITAPLOT_BOOTSTRAP%" %*
exit /b %errorlevel%

:path_python
rem 3. PATH. The bootstrap rejects Store aliases and unsupported versions.
where python.exe >nul 2>nul
if errorlevel 1 goto path_python3
python.exe -c "%EDITAPLOT_PYTHON_PROBE%" >nul 2>nul
if errorlevel 1 goto path_python3
python.exe "%EDITAPLOT_BOOTSTRAP%" %*
exit /b %errorlevel%

:path_python3
where python3.exe >nul 2>nul
if errorlevel 1 goto registry_python
python3.exe -c "%EDITAPLOT_PYTHON_PROBE%" >nul 2>nul
if errorlevel 1 goto registry_python
python3.exe "%EDITAPLOT_BOOTSTRAP%" %*
exit /b %errorlevel%

:registry_python
rem 4. Official CPython registry entries, including custom install directories.
call :find_registry_python 3.12
if defined EDITAPLOT_REGISTRY_PYTHON goto run_registry_python
call :find_registry_python 3.11
if defined EDITAPLOT_REGISTRY_PYTHON goto run_registry_python
call :find_registry_python 3.10
if defined EDITAPLOT_REGISTRY_PYTHON goto run_registry_python
goto local_312

:run_registry_python
"%EDITAPLOT_REGISTRY_PYTHON%" -c "%EDITAPLOT_PYTHON_PROBE%" >nul 2>nul
if errorlevel 1 goto local_312
"%EDITAPLOT_REGISTRY_PYTHON%" "%EDITAPLOT_BOOTSTRAP%" %*
exit /b %errorlevel%

:find_registry_python
set "EDITAPLOT_REGISTRY_PYTHON="
for %%H in (HKCU HKLM) do (
  for %%R in (64 32) do (
    for /f "tokens=2,*" %%A in ('reg.exe query "%%H\Software\Python\PythonCore\%~1\InstallPath" /ve /reg:%%R 2^>nul ^| findstr.exe /R /C:"REG_SZ" /C:"REG_EXPAND_SZ"') do (
      if exist "%%Bpython.exe" set "EDITAPLOT_REGISTRY_PYTHON=%%Bpython.exe"
      if exist "%%B\python.exe" set "EDITAPLOT_REGISTRY_PYTHON=%%B\python.exe"
    )
  )
)
exit /b 0

:local_312
rem 5. Standard per-user/system Python locations when PATH is unavailable.
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" goto run_local_312
if exist "%ProgramFiles%\Python312\python.exe" goto run_program_312
goto local_311

:run_local_312
"%LocalAppData%\Programs\Python\Python312\python.exe" -c "%EDITAPLOT_PYTHON_PROBE%" >nul 2>nul
if errorlevel 1 goto run_program_312_if_present
"%LocalAppData%\Programs\Python\Python312\python.exe" "%EDITAPLOT_BOOTSTRAP%" %*
exit /b %errorlevel%

:run_program_312_if_present
if exist "%ProgramFiles%\Python312\python.exe" goto run_program_312
goto local_311

:run_program_312
"%ProgramFiles%\Python312\python.exe" -c "%EDITAPLOT_PYTHON_PROBE%" >nul 2>nul
if errorlevel 1 goto local_311
"%ProgramFiles%\Python312\python.exe" "%EDITAPLOT_BOOTSTRAP%" %*
exit /b %errorlevel%

:local_311
if exist "%LocalAppData%\Programs\Python\Python311\python.exe" goto run_local_311
if exist "%ProgramFiles%\Python311\python.exe" goto run_program_311
goto local_310

:run_local_311
"%LocalAppData%\Programs\Python\Python311\python.exe" -c "%EDITAPLOT_PYTHON_PROBE%" >nul 2>nul
if errorlevel 1 goto run_program_311_if_present
"%LocalAppData%\Programs\Python\Python311\python.exe" "%EDITAPLOT_BOOTSTRAP%" %*
exit /b %errorlevel%

:run_program_311_if_present
if exist "%ProgramFiles%\Python311\python.exe" goto run_program_311
goto local_310

:run_program_311
"%ProgramFiles%\Python311\python.exe" -c "%EDITAPLOT_PYTHON_PROBE%" >nul 2>nul
if errorlevel 1 goto local_310
"%ProgramFiles%\Python311\python.exe" "%EDITAPLOT_BOOTSTRAP%" %*
exit /b %errorlevel%

:local_310
if exist "%LocalAppData%\Programs\Python\Python310\python.exe" goto run_local_310
if exist "%ProgramFiles%\Python310\python.exe" goto run_program_310
goto managed_runtime

:run_local_310
"%LocalAppData%\Programs\Python\Python310\python.exe" -c "%EDITAPLOT_PYTHON_PROBE%" >nul 2>nul
if errorlevel 1 goto run_program_310_if_present
"%LocalAppData%\Programs\Python\Python310\python.exe" "%EDITAPLOT_BOOTSTRAP%" %*
exit /b %errorlevel%

:run_program_310_if_present
if exist "%ProgramFiles%\Python310\python.exe" goto run_program_310
goto managed_runtime

:run_program_310
"%ProgramFiles%\Python310\python.exe" -c "%EDITAPLOT_PYTHON_PROBE%" >nul 2>nul
if errorlevel 1 goto managed_runtime
"%ProgramFiles%\Python310\python.exe" "%EDITAPLOT_BOOTSTRAP%" %*
exit /b %errorlevel%

:no_python
echo {"ok":false,"error":{"code":"python_command_unavailable","message":"Install 64-bit CPython 3.10-3.12 or set EDITAPLOT_PYTHON. No global packages or Origin changes were attempted."}} 1>&2
exit /b 3
