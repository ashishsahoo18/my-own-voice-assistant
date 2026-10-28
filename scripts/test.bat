@echo off
setlocal
echo ===================================================
echo   OLIVER 2.0 - Automated Test Suite Runner
echo ===================================================

set PYTHONPATH=.
python -m unittest discover -s tests -p "test_*.py"
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Tests failed with exit code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)

echo [SUCCESS] All OLIVER 2.0 tests passed cleanly.
endlocal
