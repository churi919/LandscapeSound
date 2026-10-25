$expectedApp = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'app.py'))
$connections = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue
foreach ($taskConnection in $connections) {
    $taskProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($taskConnection.OwningProcess)"
    if ($taskProcess -and $taskProcess.CommandLine -and $taskProcess.CommandLine.Contains($expectedApp) -and $taskProcess.CommandLine -match 'streamlit\s+run') {
        Stop-Process -Id $taskProcess.ProcessId
        Write-Output 'LandscapeSound stopped.'
    }
}
