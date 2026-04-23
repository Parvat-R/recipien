@echo off
REM Run all Jupyter notebooks in the notebooks directory
jupyter nbconvert --execute --to notebook --inplace "%~dp0notebooks\00 setup.ipynb"
jupyter nbconvert --execute --to notebook --inplace "%~dp0notebooks\01 ingredients.ipynb"


if %ERRORLEVEL% neq 0 (
    echo ERROR: Notebook execution failed.
    exit /b %ERRORLEVEL%
)

echo Done!