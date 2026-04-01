param(
    [switch]$ResetData,
    [switch]$SkipMigration,
    [switch]$StartApp
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot ".env.postgres"
$envExampleFile = Join-Path $projectRoot ".env.postgres.example"
$composeFile = Join-Path $projectRoot "docker-compose.yml"
$pythonFromVenv = Join-Path $projectRoot ".venv\Scripts\python.exe"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Import-EnvFile {
    param([string]$Path)
    Get-Content $Path | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
            [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
        }
    }
}

function Get-PythonExe {
    if (Test-Path $pythonFromVenv) {
        return $pythonFromVenv
    }
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        return $pythonCommand.Source
    }
    throw "Python introuvable. Active ton environnement ou installe Python."
}

function Wait-ForDockerContainer {
    param(
        [string]$ContainerName,
        [int]$TimeoutSeconds = 90
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $state = docker inspect --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" $ContainerName 2>$null
        if ($LASTEXITCODE -eq 0 -and ($state -eq "healthy" -or $state -eq "running")) {
            return
        }
        Start-Sleep -Seconds 2
    }

    throw "Le conteneur $ContainerName n'est pas pret a temps."
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker n'est pas installe ou n'est pas dans le PATH."
}

if (-not (Test-Path $composeFile)) {
    throw "docker-compose.yml introuvable dans $projectRoot"
}

if (-not (Test-Path $envFile)) {
    if (-not (Test-Path $envExampleFile)) {
        throw ".env.postgres et .env.postgres.example sont introuvables."
    }
    Copy-Item $envExampleFile $envFile
}

Write-Step "Chargement de la configuration locale"
Import-EnvFile -Path $envFile

if (-not $env:PROJETCITY_DATABASE_URL) {
    throw "PROJETCITY_DATABASE_URL est manquante dans .env.postgres"
}

if ($ResetData) {
    Write-Step "Suppression des volumes PostgreSQL locaux"
    docker compose --env-file $envFile down -v
}

Write-Step "Demarrage de PostgreSQL/PostGIS"
docker compose --env-file $envFile up -d

Write-Step "Attente du conteneur PostgreSQL"
Wait-ForDockerContainer -ContainerName "projetcity-postgres"

$pythonExe = Get-PythonExe

if (-not $SkipMigration) {
    Write-Step "Migration SQLite -> PostgreSQL"
    & $pythonExe (Join-Path $projectRoot "scripts\migrate_sqlite_to_postgres.py") `
        --pg-dsn $env:PROJETCITY_DATABASE_URL `
        --truncate-target
    if ($LASTEXITCODE -ne 0) {
        throw "La migration a echoue."
    }
}

Write-Step "Base PostgreSQL locale prete"
Write-Host "DSN : $env:PROJETCITY_DATABASE_URL" -ForegroundColor Green
Write-Host "Commandes utiles :" -ForegroundColor Green
Write-Host "  docker compose --env-file .env.postgres ps"
Write-Host "  docker compose --env-file .env.postgres logs -f postgres"
Write-Host "  python run_web.py"

if ($StartApp) {
    Write-Step "Lancement de l'application"
    Push-Location $projectRoot
    try {
        & $pythonExe "run_web.py"
    }
    finally {
        Pop-Location
    }
}
