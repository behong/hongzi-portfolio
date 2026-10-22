[CmdletBinding()]
param(
    [switch]$LocalOnly,
    [ValidateRange(1024, 65535)]
    [int]$PreviewPort = 18080
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Invoke-Docker {
    param([string[]]$Arguments)
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed (exit code $LASTEXITCODE). See the Docker error above for the cause."
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker Desktop is required.'
}
if (-not $LocalOnly -and -not (Test-Path -LiteralPath '.secrets/tunnel.json' -PathType Leaf)) {
    throw 'Missing .secrets/tunnel.json. Restore the tunnel credentials from your private backup. Use -LocalOnly to preview without a tunnel.'
}

Invoke-Docker -Arguments @('info', '--format', '{{.ServerVersion}}')
$composeArguments = @('compose', '-f', 'docker-compose.yml')
if ($LocalOnly) {
    $env:PREVIEW_PORT = [string]$PreviewPort
    $composeArguments += @('-f', 'docker-compose.preview.yml')
}
Invoke-Docker -Arguments ($composeArguments + @('config', '--quiet'))
Invoke-Docker -Arguments ($composeArguments + @('run', '--rm', '--no-deps', 'web', 'caddy', 'validate', '--config', '/etc/caddy/Caddyfile', '--adapter', 'caddyfile'))

if ($LocalOnly) {
    Invoke-Docker -Arguments ($composeArguments + @('up', '-d', '--wait', '--wait-timeout', '90', 'web'))
} else {
    Invoke-Docker -Arguments ($composeArguments + @('up', '-d', '--wait', '--wait-timeout', '90'))
}

Invoke-Docker -Arguments ($composeArguments + @('ps'))
if ($LocalOnly) {
    Write-Host "Local preview: http://localhost:$PreviewPort"
} else {
    Write-Host 'Check tunnel connections and DNS before opening https://hongzi.us.'
}
