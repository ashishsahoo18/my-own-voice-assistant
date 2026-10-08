# OLIVER 2.0 - PowerShell Test Runner
$ErrorActionPreference = "Stop"
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  OLIVER 2.0 - Automated Test Suite Runner (PowerShell)" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

$env:PYTHONPATH = "."
python -m unittest discover -s tests -p "test_*.py"

if ($LASTEXITCODE -eq 0) {
    Write-Host "[SUCCESS] All OLIVER 2.0 tests passed cleanly." -ForegroundColor Green
} else {
    Write-Host "[FAIL] Test suite failed with exit code $LASTEXITCODE." -ForegroundColor Red
    exit $LASTEXITCODE
}
