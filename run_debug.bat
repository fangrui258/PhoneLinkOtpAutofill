@echo off
setlocal
cd /d "%~dp0"

set "CONDA_CMD=%CONDA_EXE%"
if not defined CONDA_CMD if exist "%USERPROFILE%\anaconda3\Scripts\conda.exe" set "CONDA_CMD=%USERPROFILE%\anaconda3\Scripts\conda.exe"
if not defined CONDA_CMD if exist "%USERPROFILE%\miniconda3\Scripts\conda.exe" set "CONDA_CMD=%USERPROFILE%\miniconda3\Scripts\conda.exe"
if not defined CONDA_CMD if exist "D:\software\Anaconda\Scripts\conda.exe" set "CONDA_CMD=D:\software\Anaconda\Scripts\conda.exe"
if not defined CONDA_CMD set "CONDA_CMD=conda"

call "%CONDA_CMD%" run -n game python -m pip install -r requirements.txt
if errorlevel 1 goto :error
call "%CONDA_CMD%" run -n game python PhoneLinkOtpAutofill.py
if errorlevel 1 goto :error
goto :end

:error
echo.
echo Failed to run with Conda environment "game".

:end
pause
