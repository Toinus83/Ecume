$ErrorActionPreference = "Continue"

$Ports = @(8000, 5173, 5174)
$Stopped = 0

foreach ($Port in $Ports) {
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($connection in $connections) {
        $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
        if ($process) {
            Write-Host "Arret du processus $($process.ProcessName) sur le port $Port"
            Stop-Process -Id $process.Id -Force
            $Stopped += 1
        }
    }
}

if ($Stopped -eq 0) {
    Write-Host "Aucun serveur ECUME detecte sur les ports habituels."
} else {
    Write-Host "$Stopped processus arrete(s)."
}
