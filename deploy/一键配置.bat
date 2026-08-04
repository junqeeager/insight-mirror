@echo off
echo ====================================
echo   个人画像系统 - 一键端口转发配置
echo ====================================
echo.
echo 正在以管理员权限运行...
echo.

:: 获取脚本所在目录
set "SCRIPT_DIR=%~dp0"

:: 以管理员权限运行 PowerShell 脚本
powershell -ExecutionPolicy Bypass -Command "Start-Process PowerShell -ArgumentList '-ExecutionPolicy Bypass -File \"%SCRIPT_DIR%setup-portforward.ps1\"' -Verb RunAs"

echo.
echo 如果弹出 UAC 提示，请点击"是"
echo.
pause
