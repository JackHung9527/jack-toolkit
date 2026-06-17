@echo off
REM Fix: an Ethernet adapter with no internet steals the default route from Wi-Fi.
REM This lowers the chosen adapter's priority by raising its interface metric,
REM which also disables "automatic metric" so it survives reconnects.

REM --- self-elevate to Administrator ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator rights...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo ===========================================================
echo  Current network interfaces (lower Metric = higher priority)
echo ===========================================================
powershell -NoProfile -Command "Get-NetIPInterface -AddressFamily IPv4 | Sort-Object InterfaceMetric | Format-Table ifIndex, InterfaceAlias, InterfaceMetric, @{N='AutoMetric';E={$_.AutomaticMetric}}, ConnectionState -AutoSize"

echo.
echo Look at the table above. Find your ETHERNET adapter (the one
echo plugged into the router with NO internet) and note its ifIndex.
echo.
set /p IDX="Enter the ifIndex of the Ethernet adapter to de-prioritise: "

echo.
echo Setting interface %IDX% metric to 9000 (IPv4 + IPv6)...
powershell -NoProfile -Command "Set-NetIPInterface -InterfaceIndex %IDX% -AddressFamily IPv4 -InterfaceMetric 9000"
powershell -NoProfile -Command "Set-NetIPInterface -InterfaceIndex %IDX% -AddressFamily IPv6 -InterfaceMetric 9000 -ErrorAction SilentlyContinue"

echo.
echo ===========================================================
echo  Updated interfaces:
echo ===========================================================
powershell -NoProfile -Command "Get-NetIPInterface -AddressFamily IPv4 | Sort-Object InterfaceMetric | Format-Table ifIndex, InterfaceAlias, InterfaceMetric, ConnectionState -AutoSize"

echo.
echo Done. Wi-Fi should now be used for internet. Test by opening a website.
echo (To undo: re-run and set the metric back, or run
echo  "Set-NetIPInterface -InterfaceIndex %IDX% -AutomaticMetric Enabled" in an admin PowerShell.)
echo.
pause
