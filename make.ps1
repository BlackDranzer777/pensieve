<#
.SYNOPSIS
    PowerShell task runner for Pensieve — the same targets as the Makefile.

.DESCRIPTION
    `make` is not installed by default on Windows. This script exposes the same
    target names and runs the same underlying commands, so the documented
    workflow works on Windows without installing extra tooling.

    The Makefile remains the canonical runner for CI, Docker, Linux and macOS.

.EXAMPLE
    .\make.ps1 setup
    .\make.ps1 test
    .\make.ps1 seed -Rows 50000
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Target = 'help',

    [int]$Rows = 10000
)

$ErrorActionPreference = 'Stop'
$RepoRoot = $PSScriptRoot
$Py = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$Web = Join-Path $RepoRoot 'apps\web'

function Assert-Venv {
    if (-not (Test-Path $Py)) {
        throw "Virtualenv not found at $Py. Run '.\make.ps1 setup' first."
    }
}

# Runs a command and stops the script if it fails, so a broken step is never
# mistaken for a passing one.
function Invoke-Step {
    param([string]$Name, [scriptblock]$Action)
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

function Invoke-Npm {
    param([string]$Name, [string[]]$NpmArgs)
    Push-Location $Web
    try { Invoke-Step $Name { & npm @NpmArgs } }
    finally { Pop-Location }
}

function Show-Help {
    Write-Host "Pensieve - available targets:`n" -ForegroundColor White
    $targets = [ordered]@{
        'setup'          = 'Create the venv, install Python and npm dependencies, write .env'
        'check'          = 'Report whether this machine can run each part of the platform'
        'dev'            = 'Run the API and the dashboard together (two windows)'
        'dev-api'        = 'Run only the FastAPI backend with autoreload'
        'dev-web'        = 'Run only the Vite dev server'
        'test'           = 'Run every test suite'
        'test-api'       = 'Backend tests'
        'test-pipelines' = 'Pipeline tests'
        'test-web'       = 'Frontend tests'
        'lint'           = 'Lint and type-check everything'
        'format'         = 'Auto-format Python and TypeScript'
        'seed'           = 'Generate a synthetic dataset (-Rows 50000)'
        'pipeline'       = 'Run the full pipeline: Bronze -> Silver -> Gold'
        'gold'           = 'Run only the PySpark Silver -> Gold stage (needs JDK 17+)'
        'gold-docker'    = 'Run the Gold stage in Docker (use when the local JDK is < 17)'
        'benchmark'      = 'Timed pipeline run; records measured results'
        'db-up'          = 'Start PostgreSQL only'
        'db-down'        = 'Stop PostgreSQL'
        'migrate'        = 'Apply Alembic migrations'
        'docker-up'      = 'Start the full stack'
        'docker-down'    = 'Stop the stack and remove volumes'
        'clean'          = 'Remove generated data, build output and caches'
    }
    foreach ($key in $targets.Keys) {
        Write-Host ('  {0,-16}' -f $key) -ForegroundColor Cyan -NoNewline
        Write-Host $targets[$key]
    }
    Write-Host ''
}

Push-Location $RepoRoot
try {
    switch ($Target.ToLowerInvariant()) {
        'help' { Show-Help }

        'setup' {
            Invoke-Step 'Creating virtualenv' { & python -m venv .venv }
            Invoke-Step 'Upgrading pip' { & $Py -m pip install --upgrade pip --quiet }
            Invoke-Step 'Installing Python dependencies' { & $Py -m pip install -e ".[api,pipelines,dev]" --quiet }
            Invoke-Npm 'Installing npm dependencies' @('install')
            if (-not (Test-Path (Join-Path $RepoRoot '.env'))) {
                Copy-Item (Join-Path $RepoRoot '.env.example') (Join-Path $RepoRoot '.env')
                Write-Host 'Created .env from .env.example' -ForegroundColor Green
            }
            Write-Host ''
            & $Py scripts\check_env.py
        }

        'check' { Assert-Venv; & $Py scripts\check_env.py }

        'dev' {
            Assert-Venv
            Write-Host 'API -> http://localhost:8000/docs' -ForegroundColor Green
            Write-Host 'Web -> http://localhost:5173' -ForegroundColor Green
            Write-Host 'Opening two windows; close them to stop.' -ForegroundColor Yellow
            Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$RepoRoot'; & '$Py' -m uvicorn app.main:app --reload --port 8000"
            Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$Web'; npm run dev"
        }

        'dev-api' { Assert-Venv; & $Py -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 }
        'dev-web' { Invoke-Npm 'Vite dev server' @('run', 'dev') }

        'test' {
            Assert-Venv
            Invoke-Step 'Backend tests' { & $Py -m pytest apps/api/tests }
            Invoke-Step 'Pipeline tests' { & $Py -m pytest pipelines/tests }
            Invoke-Npm 'Frontend tests' @('run', 'test')
        }
        'test-api' { Assert-Venv; Invoke-Step 'Backend tests' { & $Py -m pytest apps/api/tests } }
        'test-pipelines' { Assert-Venv; Invoke-Step 'Pipeline tests' { & $Py -m pytest pipelines/tests } }
        'test-web' { Invoke-Npm 'Frontend tests' @('run', 'test') }

        'lint' {
            Assert-Venv
            Invoke-Step 'ruff check' { & $Py -m ruff check . }
            Invoke-Step 'ruff format --check' { & $Py -m ruff format --check . }
            Invoke-Step 'mypy' { & $Py -m mypy }
            Invoke-Npm 'eslint' @('run', 'lint')
            Invoke-Npm 'tsc' @('run', 'typecheck')
            Invoke-Npm 'prettier' @('run', 'format:check')
        }

        'format' {
            Assert-Venv
            Invoke-Step 'ruff format' { & $Py -m ruff format . }
            Invoke-Step 'ruff --fix' { & $Py -m ruff check --fix . }
            Invoke-Npm 'prettier' @('run', 'format')
        }

        'seed' { Assert-Venv; & $Py scripts\seed_demo_data.py --rows $Rows }
        'pipeline' { Assert-Venv; & $Py -m pipelines.jobs.run_pipeline }
        'gold' { Assert-Venv; & $Py -m pipelines.jobs.run_gold }
        'gold-docker' { & docker compose --profile spark run --rm spark-job }
        'benchmark' { Assert-Venv; & $Py scripts\benchmark.py }

        'db-up' { Invoke-Step 'Starting PostgreSQL' { & docker compose up -d postgres } }
        'db-down' { & docker compose stop postgres }
        'migrate' {
            Assert-Venv
            Push-Location (Join-Path $RepoRoot 'apps\api')
            try { Invoke-Step 'alembic upgrade head' { & $Py -m alembic upgrade head } }
            finally { Pop-Location }
        }

        'docker-build' { Invoke-Step 'docker compose build' { & docker compose build } }
        'docker-up' { & docker compose up --build }
        'docker-down' { & docker compose down -v }

        'clean' { Assert-Venv; & $Py scripts\clean.py }

        default {
            Write-Host "Unknown target: $Target`n" -ForegroundColor Red
            Show-Help
            exit 1
        }
    }
}
finally {
    Pop-Location
}
