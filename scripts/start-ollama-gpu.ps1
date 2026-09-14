param(
    [ValidateRange(1024, 65535)][int]$Port = 11434,
    [string]$Model = '',
    [ValidateRange(0, 16)][int]$GpuIndex = 0,
    [switch]$Restart
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$OllamaExe = (Get-Command ollama -ErrorAction Stop).Source
$OllamaDirectory = Split-Path -Parent $OllamaExe
$VulkanDirectory = Join-Path $OllamaDirectory 'lib\ollama\vulkan'
if (-not (Test-Path -LiteralPath $VulkanDirectory)) {
    throw 'Le moteur Vulkan est absent de cette installation Ollama.'
}

$Listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($Listeners.Count -gt 0) {
    if (-not $Restart) {
        throw "Le port $Port est occupe. Pour redemarrer Ollama en mode GPU : ajouter -Restart."
    }
    $Processes = @(Get-CimInstance Win32_Process)
    $ServerIds = @($Listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($ServerId in $ServerIds) {
        $Server = $Processes | Where-Object { $_.ProcessId -eq $ServerId }
        if ($Server.Name -ne 'ollama.exe' -or $Server.ExecutablePath -ne $OllamaExe) {
            throw "Le processus $ServerId n'est pas le serveur Ollama attendu ; arret refuse."
        }
        $Parent = $Processes | Where-Object { $_.ProcessId -eq $Server.ParentProcessId }
        $StopId = $ServerId
        if ($Parent.Name -eq 'ollama app.exe' -and $Parent.ExecutablePath -eq (Join-Path $OllamaDirectory 'ollama app.exe')) {
            $StopId = $Parent.ProcessId
        }
        & "$env:SystemRoot\System32\taskkill.exe" /PID $StopId /T /F
        if ($LASTEXITCODE -ne 0) { throw 'Arret refuse par Windows. Ferme Ollama depuis son icone puis relance ce script.' }
    }
    $Deadline = (Get-Date).AddSeconds(10)
    while ([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners().Port -contains $Port) {
        if ((Get-Date) -gt $Deadline) { throw "Le port $Port reste occupe." }
        Start-Sleep -Milliseconds 250
    }
}

$Logs = New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot 'data\runtime')
$Settings = @{
    CUDA_VISIBLE_DEVICES = '-1'
    OLLAMA_VULKAN = '1'
    GGML_VK_VISIBLE_DEVICES = [string]$GpuIndex
    OLLAMA_LLM_LIBRARY = $null
    OLLAMA_HOST = "127.0.0.1:$Port"
}
$Previous = @{}
try {
    foreach ($Name in $Settings.Keys) {
        $Previous[$Name] = [Environment]::GetEnvironmentVariable($Name, 'Process')
        [Environment]::SetEnvironmentVariable($Name, $Settings[$Name], 'Process')
    }
    $ServerProcess = Start-Process -FilePath $OllamaExe -ArgumentList 'serve' -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $Logs.FullName "ollama-vulkan-$Port.out.log") `
        -RedirectStandardError (Join-Path $Logs.FullName "ollama-vulkan-$Port.err.log")
} finally {
    foreach ($Name in $Previous.Keys) {
        [Environment]::SetEnvironmentVariable($Name, $Previous[$Name], 'Process')
    }
}

$BaseUrl = "http://127.0.0.1:$Port"
$Deadline = (Get-Date).AddSeconds(30)
do {
    if ($ServerProcess.HasExited) { throw "Ollama s'est arrete. Consulte les journaux dans $($Logs.FullName)." }
    try { $null = Invoke-RestMethod "$BaseUrl/api/version" -TimeoutSec 2; break } catch {
        if ((Get-Date) -gt $Deadline) { throw 'Ollama ne repond pas apres 30 secondes.' }
        Start-Sleep -Milliseconds 500
    }
} while ($true)

if (-not $Model) {
    $Models = @((Invoke-RestMethod "$BaseUrl/api/tags" -TimeoutSec 10).models)
    if ($Models.Count -eq 0) { throw 'Aucun modele installe. Installe un modele Ollama puis relance le script.' }
    $Model = $Models[0].name
}
Write-Host "Verification GPU du modele $Model..."
$Request = @{
    model = $Model
    prompt = 'Reply with OK only.'
    stream = $false
    keep_alive = '10m'
    options = @{ num_predict = 8; num_ctx = 4096; num_gpu = 99 }
} | ConvertTo-Json -Depth 4
$null = Invoke-RestMethod "$BaseUrl/api/generate" -Method Post -ContentType 'application/json' -Body $Request -TimeoutSec 180
$Running = @((Invoke-RestMethod "$BaseUrl/api/ps" -TimeoutSec 10).models) | Where-Object { $_.name -eq $Model -or $_.model -eq $Model }
if (-not $Running -or $Running[0].size_vram -le 0) {
    throw "Le modele ne travaille pas sur le GPU. Consulter les journaux dans $($Logs.FullName)."
}
$GpuGiB = [Math]::Round($Running[0].size_vram / 1GB, 2)
Write-Host "Ollama GPU Vulkan pret : $BaseUrl ; $GpuGiB Gio en memoire video ; PID $($ServerProcess.Id)." -ForegroundColor Green
Write-Host 'Tu peux lancer le backend et le frontend ECUME. Aucune variable Windows permanente n a ete modifiee.'
