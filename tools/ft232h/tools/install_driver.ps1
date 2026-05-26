# FT232H driver auto-install helper.
#
# Flow: detect FT232H -> download Zadig -> launch GUI -> verify driver swap.

# Always show a window pause + log file even if we crash early.
$ErrorActionPreference = "Stop"
$logFile = Join-Path $env:TEMP "ft232h_install_driver.log"
try { Start-Transcript -Path $logFile -Force | Out-Null } catch {}

function Pause-End($code)
{
    Write-Host ""
    Write-Host "Log file: $logFile" -ForegroundColor DarkGray
    try { Stop-Transcript | Out-Null } catch {}
    [void](Read-Host "Press Enter to close")
    exit $code
}

try
{
    # ---- 0. Self-elevate to admin if needed ----
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))
    {
        Write-Host "Need admin privileges, relaunching..." -ForegroundColor Yellow
        $self = $MyInvocation.MyCommand.Path
        Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$self`""
        exit
    }

    $root = Split-Path -Parent $MyInvocation.MyCommand.Definition
    $projRoot = Split-Path -Parent $root
    $cacheDir = Join-Path $root "_cache"
    $zadigExe = Join-Path $cacheDir "zadig.exe"

    Write-Host "FT232H driver installer" -ForegroundColor Cyan
    Write-Host "  script root : $root"
    Write-Host "  project root: $projRoot"
    Write-Host "  zadig cache : $zadigExe"
    Write-Host ""

    function Get-Ft232hDevices
    {
        Get-PnpDevice -ErrorAction SilentlyContinue |
            Where-Object { $_.InstanceId -match "VID_0403&PID_6014" }
    }

    function Show-Devices($devices, $title)
    {
        Write-Host ""
        Write-Host "==== $title ====" -ForegroundColor Cyan
        if (-not $devices)
        {
            Write-Host "  (no FT232H found)"
            return
        }
        foreach ($d in $devices)
        {
            $color = "White"
            if ($d.Service -eq "WinUSB") { $color = "Green" }
            elseif ($d.Service -in @("libusbK", "libusb0", "FTDIBUS")) { $color = "Yellow" }
            Write-Host ("  {0,-24} driver={1,-10} status={2}" -f $d.FriendlyName, $d.Service, $d.Status) -ForegroundColor $color
            Write-Host ("    InstanceId: {0}" -f $d.InstanceId) -ForegroundColor DarkGray
        }
    }

    # ---- 1. Initial detection ----
    $before = Get-Ft232hDevices
    Show-Devices $before "Before"

    if (-not $before)
    {
        Write-Host ""
        Write-Host "FT232H not found (VID=0403 PID=6014)." -ForegroundColor Red
        Write-Host "Plug in the FT232H board via USB and rerun this script."
        Pause-End 1
    }

    $already = $before | Where-Object { $_.Service -eq "WinUSB" }
    if ($already -and ($already.Count -eq $before.Count))
    {
        Write-Host ""
        Write-Host "All FT232H devices already on libusb driver. Nothing to do." -ForegroundColor Green
        Pause-End 0
    }

    # ---- 2. Download Zadig ----
    if (-not (Test-Path $cacheDir))
    {
        New-Item -ItemType Directory -Path $cacheDir | Out-Null
    }

    if (-not (Test-Path $zadigExe))
    {
        Write-Host ""
        Write-Host "Downloading latest Zadig from GitHub..." -ForegroundColor Cyan
        try
        {
            [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
            $headers = @{ "User-Agent" = "FT232H-Tester-Installer" }
            $api = Invoke-RestMethod -Uri "https://api.github.com/repos/pbatard/libwdi/releases/latest" -Headers $headers -UseBasicParsing
            $asset = $api.assets | Where-Object { $_.name -match "^zadig-.*\.exe$" } | Select-Object -First 1
            if (-not $asset) { throw "No zadig-*.exe asset in latest release" }
            Write-Host ("  -> {0} ({1:N0} bytes)" -f $asset.name, $asset.size)
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zadigExe -Headers $headers -UseBasicParsing
            Write-Host "Downloaded: $zadigExe" -ForegroundColor Green
        }
        catch
        {
            Write-Host "Download failed: $_" -ForegroundColor Red
            Write-Host "Manual: download zadig.exe from https://zadig.akeo.ie/ to:"
            Write-Host "    $zadigExe"
            Pause-End 1
        }
    }
    else
    {
        Write-Host ""
        Write-Host "Using cached Zadig: $zadigExe"
    }

    # ---- 3. Launch Zadig ----
    Write-Host ""
    Write-Host "========== Zadig steps ==========" -ForegroundColor Yellow
    Write-Host "  1. Options -> List All Devices  (check)"
    Write-Host "  2. Options -> Ignore Hubs or Composite Parents  (check)"
    Write-Host "  3. Dropdown: pick 'USB Serial Converter' or 'FT232H' (USB ID 0403 6014)"
    Write-Host "  4. Target driver: WinUSB  (recommended; libusb-1.0.dll does not support libusbK on Win11)"
    Write-Host "  5. Click  Replace Driver  button, wait for SUCCESS"
    Write-Host "  6. Close Zadig window; this script will recheck automatically"
    Write-Host "==================================" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Launching Zadig..." -ForegroundColor Cyan

    Start-Process -FilePath $zadigExe -Wait

    # ---- 4. Re-detect ----
    Write-Host ""
    Write-Host "Re-detecting driver..."
    Start-Sleep -Seconds 2
    $after = Get-Ft232hDevices
    Show-Devices $after "After"

    $okList = $after | Where-Object { $_.Service -eq "WinUSB" }
    if ($okList -and $okList.Count -gt 0)
    {
        Write-Host ""
        Write-Host "SUCCESS: FT232H switched to libusb driver." -ForegroundColor Green

        $venvPy = Join-Path $projRoot ".venv\Scripts\python.exe"
        if (Test-Path $venvPy)
        {
            Write-Host ""
            Write-Host "Probing with pyftdi..." -ForegroundColor Cyan
            $code = "from pyftdi.ftdi import Ftdi`nlst = list(Ftdi.list_devices('ftdi://ftdi:232h/?'))`nprint(f'pyftdi sees {len(lst)} FT232H')`nfor desc, _ in lst: print('  -', desc.sn or '(no-sn)', desc.description)"
            & $venvPy -c $code
        }
        else
        {
            Write-Host ""
            Write-Host "(.venv not built yet; skip pyftdi probe. Run .\run.ps1 to launch the GUI later.)" -ForegroundColor DarkGray
        }
        Pause-End 0
    }
    else
    {
        Write-Host ""
        Write-Host "Driver does NOT look swapped. Still on the original driver." -ForegroundColor Red
        Write-Host "Rerun this script, or open $zadigExe manually and retry."
        Pause-End 2
    }
}
catch
{
    Write-Host ""
    Write-Host "FATAL: $_" -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkRed
    Pause-End 99
}