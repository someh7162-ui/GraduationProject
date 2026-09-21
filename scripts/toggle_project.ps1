param(
    [Parameter(Mandatory = $true)]
    [string]$Root
)

$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath($Root).TrimEnd('\')
$RuntimeDir = Join-Path $Root '.private\runtime'
$StatePath = Join-Path $RuntimeDir 'project-processes.json'
$StatusPath = Join-Path $RuntimeDir 'project-status.txt'
$StopRequestPath = Join-Path $RuntimeDir 'project-stop.request'
$BackendOut = Join-Path $RuntimeDir 'backend.out.log'
$BackendErr = Join-Path $RuntimeDir 'backend.err.log'
$FrontendOut = Join-Path $RuntimeDir 'frontend.out.log'
$FrontendErr = Join-Path $RuntimeDir 'frontend.err.log'
$FrontendDir = Join-Path $Root 'frontend'
$EnvPath = Join-Path $Root '.env'
$BackendLauncher = Join-Path $Root 'scripts\run_backend.py'
$FrontendLauncher = Join-Path $Root 'scripts\run_frontend.mjs'
$FrontendUrl = 'http://127.0.0.1:5173'

function Write-Status([string]$Value) {
    Set-Content -LiteralPath $StatusPath -Value $Value -Encoding ASCII
}

function Get-TrackedProcess {
    param($Entry)

    if (-not $Entry -or -not $Entry.pid) {
        return $null
    }
    $process = Get-Process -Id ([int]$Entry.pid) -ErrorAction SilentlyContinue
    if (-not $process) {
        return $null
    }
    try {
        $actualPath = [System.IO.Path]::GetFullPath($process.Path)
        $expectedPath = [System.IO.Path]::GetFullPath([string]$Entry.executable)
    }
    catch {
        return $null
    }
    if (-not $actualPath.Equals($expectedPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $null
    }
    if ($Entry.startedAt) {
        try {
            $actualStart = $process.StartTime.ToUniversalTime()
            $expectedStart = [DateTimeOffset]::Parse([string]$Entry.startedAt).UtcDateTime
            if ([Math]::Abs(($actualStart - $expectedStart).TotalSeconds) -gt 2) {
                return $null
            }
        }
        catch {
            return $null
        }
    }
    return $process
}

function Stop-ProcessTree([int]$ProcessId) {
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }
    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) {
            return
        }
        Start-Sleep -Milliseconds 100
    }

    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & "$env:SystemRoot\System32\taskkill.exe" /PID $ProcessId /T /F 2> $null | Out-Null
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }

}

function Stop-TrackedProject($State) {
    Write-Status 'stopping'
    Set-Content -LiteralPath $StopRequestPath -Value ([DateTimeOffset]::Now.ToString('o')) -Encoding ASCII
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        $backend = Get-TrackedProcess -Entry $State.backend
        $frontend = Get-TrackedProcess -Entry $State.frontend
        if (-not $backend -and -not $frontend) {
            break
        }
        Start-Sleep -Milliseconds 250
    }
    foreach ($entry in @($State.frontend, $State.backend)) {
        $process = Get-TrackedProcess -Entry $entry
        if ($process) {
            Stop-ProcessTree -ProcessId ([int]$process.ProcessId)
        }
    }
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        $backend = Get-TrackedProcess -Entry $State.backend
        $frontend = Get-TrackedProcess -Entry $State.frontend
        if (-not $backend -and -not $frontend) {
            break
        }
        Start-Sleep -Milliseconds 250
    }
    if ((Get-TrackedProcess -Entry $State.backend) -or (Get-TrackedProcess -Entry $State.frontend)) {
        Write-Status 'failed: unable to stop tracked processes'
        return $false
    }
    if (Test-Path -LiteralPath $StatePath) {
        Remove-Item -LiteralPath $StatePath -Force
    }
    Remove-Item -LiteralPath $StopRequestPath -Force -ErrorAction SilentlyContinue
    Write-Status 'stopped'
    return $true
}

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutMilliseconds = 500
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connection = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $connection.AsyncWaitHandle.WaitOne($TimeoutMilliseconds, $false)) {
            return $false
        }
        $client.EndConnect($connection)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Get-DotEnvValue {
    param([string]$Name)

    if (-not (Test-Path -LiteralPath $EnvPath)) {
        return $null
    }
    foreach ($line in Get-Content -LiteralPath $EnvPath) {
        if ($line -match ('^\s*' + [regex]::Escape($Name) + '\s*=\s*(.*)\s*$')) {
            $value = $matches[1].Trim()
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            return $value
        }
    }
    return $null
}

function Use-SqliteWhenMySqlUnavailable {
    if (-not [string]::IsNullOrWhiteSpace($env:DATABASE_URL)) {
        return
    }

    $databaseUrl = Get-DotEnvValue -Name 'DATABASE_URL'
    $mysqlHost = if ($env:MYSQL_HOST) { $env:MYSQL_HOST } else { Get-DotEnvValue -Name 'MYSQL_HOST' }
    $mysqlPortValue = if ($env:MYSQL_PORT) { $env:MYSQL_PORT } else { Get-DotEnvValue -Name 'MYSQL_PORT' }
    $mysqlPassword = [Environment]::GetEnvironmentVariable('MYSQL_PASSWORD')
    if ($null -eq $mysqlPassword) {
        $mysqlPassword = Get-DotEnvValue -Name 'MYSQL_PASSWORD'
    }

    $usesMySql = $false
    if (-not [string]::IsNullOrWhiteSpace($databaseUrl)) {
        if ($databaseUrl -notmatch '^mysql(?:\+[^:]+)?://') {
            return
        }
        try {
            $uri = [Uri]$databaseUrl
            $mysqlHost = $uri.Host
            $mysqlPortValue = if ($uri.IsDefaultPort) { 3306 } else { $uri.Port }
            $usesMySql = $true
        }
        catch {
            return
        }
    }
    elseif ($null -ne $mysqlPassword) {
        $usesMySql = $true
    }

    if (-not $usesMySql) {
        return
    }

    if ([string]::IsNullOrWhiteSpace($mysqlHost)) {
        $mysqlHost = '127.0.0.1'
    }
    $mysqlPort = 3306
    if ($mysqlPortValue -and -not [int]::TryParse([string]$mysqlPortValue, [ref]$mysqlPort)) {
        $mysqlPort = 3306
    }

    if (-not (Test-TcpPort -HostName $mysqlHost -Port $mysqlPort)) {
        $sqlitePath = (Join-Path $Root 'campus.db').Replace('\', '/')
        $env:DATABASE_URL = 'sqlite:///' + $sqlitePath
        $env:MYSQL_PASSWORD = ''
    }
}

function Test-Url([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    }
    catch {
        return $false
    }
}

$mutex = New-Object System.Threading.Mutex($false, 'Local\CampusRecommenderProjectToggle')
$locked = $false
try {
    $locked = $mutex.WaitOne(5000)
    if (-not $locked) {
        exit 2
    }

    New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null

    if (Test-Path -LiteralPath $StatePath) {
        $state = $null
        try {
            $state = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        }
        catch {
            Remove-Item -LiteralPath $StatePath -Force -ErrorAction SilentlyContinue
        }
        if ($state) {
            $backend = Get-TrackedProcess -Entry $state.backend
            $frontend = Get-TrackedProcess -Entry $state.frontend
            if ($backend -or $frontend) {
                if (Stop-TrackedProject -State $state) {
                    exit 0
                }
                exit 6
            }
            Remove-Item -LiteralPath $StatePath -Force
        }
    }

    Remove-Item -LiteralPath $StopRequestPath -Force -ErrorAction SilentlyContinue

    $pythonCandidates = @(
        (Join-Path $Root '.venv\Scripts\python.exe'),
        (Join-Path $Root '.venv-academic\Scripts\python.exe')
    )
    $PythonExe = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    $NodeExe = (Get-Command node.exe -ErrorAction SilentlyContinue).Source
    $ViteModule = Join-Path $FrontendDir 'node_modules\vite\dist\node\index.js'

    if (-not $PythonExe -or -not $NodeExe -or -not (Test-Path -LiteralPath $ViteModule) -or -not (Test-Path -LiteralPath $BackendLauncher) -or -not (Test-Path -LiteralPath $FrontendLauncher)) {
        Write-Status 'failed: runtime dependency missing'
        exit 3
    }

    if ((Test-TcpPort -HostName '127.0.0.1' -Port 8000) -or (Test-TcpPort -HostName '127.0.0.1' -Port 5173)) {
        Write-Status 'failed: port already in use'
        exit 5
    }

    $env:PYTHONPATH = $Root
    Use-SqliteWhenMySqlUnavailable
    $backend = Start-Process -FilePath $PythonExe -ArgumentList ('"' + $BackendLauncher + '"') -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $BackendOut -RedirectStandardError $BackendErr -PassThru
    $frontend = Start-Process -FilePath $NodeExe -ArgumentList ('"' + $FrontendLauncher + '"') -WorkingDirectory $FrontendDir -WindowStyle Hidden -RedirectStandardOutput $FrontendOut -RedirectStandardError $FrontendErr -PassThru

    $state = [ordered]@{
        startedAt = [DateTimeOffset]::Now.ToString('o')
        backend = [ordered]@{ pid = $backend.Id; executable = $PythonExe; startedAt = $backend.StartTime.ToUniversalTime().ToString('o') }
        frontend = [ordered]@{ pid = $frontend.Id; executable = $NodeExe; startedAt = $frontend.StartTime.ToUniversalTime().ToString('o') }
    }
    $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $StatePath -Encoding UTF8

    $ready = $false
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        $trackedBackend = Get-TrackedProcess -Entry ([pscustomobject]$state.backend)
        $trackedFrontend = Get-TrackedProcess -Entry ([pscustomobject]$state.frontend)
        if (-not $trackedBackend -or -not $trackedFrontend) {
            break
        }
        if ((Test-Url 'http://127.0.0.1:8000/health') -and (Test-Url 'http://127.0.0.1:5173')) {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 1
    }

    if ($ready) {
        Write-Status 'running'
        try {
            Start-Process -FilePath $FrontendUrl -ErrorAction Stop | Out-Null
        }
        catch {
        }
        exit 0
    }

    Stop-TrackedProject -State ([pscustomobject]$state) | Out-Null
    Write-Status 'failed: startup health check failed'
    exit 4
}
catch {
    New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
    Write-Status ('failed: ' + $_.Exception.Message)
    exit 1
}
finally {
    if ($locked) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
