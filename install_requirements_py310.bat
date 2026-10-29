@echo off
setlocal
chcp 65001 >nul
echo ============================================================
echo CBCT TMJ Analysis - Python 3.10 backend dependency installer
echo ============================================================
python -c "import sys,struct; print('Python:',sys.executable); print('Version:',sys.version); print('Bits:',struct.calcsize('P')*8); assert sys.version_info[:2] == (3,10), 'Activate a Python 3.10 conda environment first'; assert struct.calcsize('P')*8 == 64, '64-bit Python is required'"
if errorlevel 1 goto :error
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :error
python -m pip install -r "%~dp0requirements_backend_py310.txt"
if errorlevel 1 goto :error
python -m pip check
if errorlevel 1 goto :error
python "%~dp0verify_backend.py"
if errorlevel 1 goto :error
echo.
echo Installation and import checks completed successfully.
pause
exit /b 0
:error
echo.
echo Installation/check failed. Review the error messages above.
pause
exit /b 1
