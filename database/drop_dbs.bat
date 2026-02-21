@echo off
setlocal
set "INSTANCE=marketplace-sql"
echo Deleting Cloud SQL instance %INSTANCE%...
gcloud sql instances delete "%INSTANCE%" --quiet
if errorlevel 1 (
  echo Delete failed.
  exit /b 1
)
echo Done.
