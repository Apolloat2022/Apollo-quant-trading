@echo off
setlocal EnableDelayedExpansion

echo ================================================================
echo  Python PATH Setup — Quant Trading Platform
echo ================================================================
echo.

set "PYTHON_DIR=C:\Users\pande\AppData\Local\Programs\Python\Python311"
set "PYTHON_SCRIPTS=%PYTHON_DIR%\Scripts"

:: Verify the Python exe exists before doing anything
if not exist "%PYTHON_DIR%\python.exe" (
    echo ERROR: python.exe not found at:
    echo   %PYTHON_DIR%
    echo.
    echo Please update PYTHON_DIR in this script to match your install.
    pause
    exit /b 1
)

echo Python found at:
echo   %PYTHON_DIR%
echo.

:: Check if already in user PATH to avoid duplicates
echo %PATH% | find /I "%PYTHON_DIR%" >nul 2>&1
if %errorlevel%==0 (
    echo Python dir already in current session PATH.
) else (
    echo Adding to current session PATH...
    set "PATH=%PYTHON_DIR%;%PYTHON_SCRIPTS%;%PATH%"
)

:: Persist to user-level PATH via setx (no admin required)
:: setx reads the registry value, not the current session, so we
:: must retrieve the existing user PATH first to avoid overwriting it.
for /f "tokens=2*" %%A in (
    'reg query "HKCU\Environment" /v PATH 2^>nul'
) do set "CURRENT_USER_PATH=%%B"

:: Only add if not already present in the registry value
echo !CURRENT_USER_PATH! | find /I "%PYTHON_DIR%" >nul 2>&1
if %errorlevel%==0 (
    echo Python dir already in user PATH ^(registry^) — no change needed.
) else (
    echo Persisting to Windows user PATH...
    setx PATH "%PYTHON_DIR%;%PYTHON_SCRIPTS%;!CURRENT_USER_PATH!"
    if %errorlevel%==0 (
        echo   Done. New PATH entries added:
        echo     %PYTHON_DIR%
        echo     %PYTHON_SCRIPTS%
    ) else (
        echo   WARNING: setx failed. You may need to add these manually.
    )
)

echo.
echo ----------------------------------------------------------------
echo Verifying Python...
"%PYTHON_DIR%\python.exe" --version
echo pip location:
"%PYTHON_SCRIPTS%\pip.exe" --version 2>nul || echo   pip not found in Scripts
echo ----------------------------------------------------------------
echo.
echo NOTE: Open a NEW terminal window for the PATH change to take effect.
echo       This session already has it active for the remainder of this window.
echo.
pause
