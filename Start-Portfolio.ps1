[CmdletBinding()]
param([switch]$LocalOnly)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Invoke-Docker {
    param([string[]]$Arguments)
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed. Open Docker Desktop and verify Docker Engine access, then retry."
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker Desktop is required.'
}
if (-not $LocalOnly -and -not (Test-Path -LiteralPath '.secrets/tunnel.json' -PathType Leaf)) {
    throw 'Missing .secrets/tunnel.json. Restore the tunnel credentials from your private backup. Use -LocalOnly to preview without a tunnel.'
}

Invoke-Docker -Arguments @('info', '--format', '{{.ServerVersion}}')
Invoke-Docker -Arguments @('compose', 'config', '--quiet')
Invoke-Docker -Arguments @('compose', 'run', '--rm', '--no-deps', 'web', 'caddy', 'validate', '--config', '/etc/caddy/Caddyfile', '--adapter', 'caddyfile')

if ($LocalOnly) {
    Invoke-Docker -Arguments @('compose', 'up', '-d', '--wait', '--wait-timeout', '90', 'web')
} else {
    Invoke-Docker -Arguments @('compose', 'up', '-d', '--wait', '--wait-timeout', '90')
}

Invoke-Docker -Arguments @('compose', 'ps')
Write-Host 'Local preview: http://localhost:8080'
if (-not $LocalOnly) {
    Write-Host 'Check tunnel connections and DNS before opening https://hongzi.us.'
}
