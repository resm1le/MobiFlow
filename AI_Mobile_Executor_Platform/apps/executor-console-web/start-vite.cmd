@echo off
setlocal
set "APP_DIR=%~dp0"

if "%VITE_CONTROL_API_BASE_URL%"=="" set "VITE_CONTROL_API_BASE_URL=http://127.0.0.1:8080"
if "%VITE_CONTROL_API_BEARER_TOKEN%"=="" set "VITE_CONTROL_API_BEARER_TOKEN="

if not exist "%APP_DIR%node_modules\vite\bin\vite.js" (
  echo Run npm install in apps\executor-console-web first.
  exit /b 1
)

node "%APP_DIR%node_modules\vite\bin\vite.js" --host 127.0.0.1 --port 5173 > "%APP_DIR%vite.out.log" 2> "%APP_DIR%vite.err.log"
