<#
.SYNOPSIS
    Preflight checks + azd up for video-analysis-with-aoai.

.DESCRIPTION
    Verifies tools, Azure login, subscription, existing Azure OpenAI account and
    deployment, RBAC role of the signed-in user, registers required providers,
    sets azd environment variables and finally runs `azd up`.

.EXAMPLE
    ./azd-up.ps1 `
        -EnvironmentName     video-analysis-dev `
        -Location            westeurope `
        -AoaiResourceGroup   rg-openai `
        -AoaiAccountName     my-aoai `
        -AoaiDeploymentName  gpt-4o

.EXAMPLE
    # Use a specific subscription
    ./azd-up.ps1 -SubscriptionId 00000000-0000-0000-0000-000000000000 `
        -EnvironmentName video-analysis-dev -Location westeurope `
        -AoaiResourceGroup rg-openai -AoaiAccountName my-aoai -AoaiDeploymentName gpt-4o
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $EnvironmentName,
    [Parameter(Mandatory = $true)] [string] $Location,
    [Parameter(Mandatory = $true)] [string] $AoaiResourceGroup,
    [Parameter(Mandatory = $true)] [string] $AoaiAccountName,
    [Parameter(Mandatory = $true)] [string] $AoaiDeploymentName,

    [string] $SubscriptionId,
    [ValidateSet("local", "remote", "ask")]
    [string] $BuildMode = "ask",
    [switch] $SkipPreview,
    [switch] $YesToAll
)

$ErrorActionPreference = "Stop"

function Write-Step  ($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Write-Ok    ($m) { Write-Host "    [OK] $m" -ForegroundColor Green }
function Write-Warn2 ($m) { Write-Host "    [!] $m"  -ForegroundColor Yellow }
function Fail        ($m) { Write-Host "    [X] $m"  -ForegroundColor Red; throw $m }

# ---------- 1. Tooling ----------
Write-Step "Checking required tools"
foreach ($cmd in @("az", "azd")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Fail "$cmd not found in PATH. Install it and retry."
    }
    Write-Ok "$cmd available"
}

# ---------- 2. Azure CLI login ----------
Write-Step "Verifying Azure CLI login"
$accountJson = az account show 2>$null
if (-not $accountJson) {
    Write-Warn2 "Not logged in. Launching 'az login'..."
    az login | Out-Null
    $accountJson = az account show
}

if ($SubscriptionId) {
    Write-Step "Selecting subscription $SubscriptionId"
    az account set --subscription $SubscriptionId | Out-Null
    $accountJson = az account show
}

$account = $accountJson | ConvertFrom-Json
Write-Ok ("Subscription: {0} ({1})" -f $account.name, $account.id)
Write-Ok ("Signed-in as: {0}"        -f $account.user.name)

# ---------- 3. azd login ----------
Write-Step "Verifying azd login"
$azdStatus = azd auth login --check-status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warn2 "azd not logged in. Launching 'azd auth login'..."
    azd auth login | Out-Null
}
Write-Ok "azd authenticated"

# ---------- 4. Validate existing Azure OpenAI ----------
Write-Step "Validating Azure OpenAI account '$AoaiAccountName' in RG '$AoaiResourceGroup'"
$aoai = az cognitiveservices account show -g $AoaiResourceGroup -n $AoaiAccountName -o json 2>$null
if (-not $aoai) {
    Fail "Azure OpenAI / AI Services account '$AoaiAccountName' not found in RG '$AoaiResourceGroup'."
}
$aoaiObj = $aoai | ConvertFrom-Json
$validKinds = @("OpenAI", "AIServices")
if ($validKinds -notcontains $aoaiObj.kind) {
    Write-Warn2 "Resource kind is '$($aoaiObj.kind)', expected one of: $($validKinds -join ', '). Continuing anyway."
} else {
    Write-Ok "Resource kind: $($aoaiObj.kind)"
}
Write-Ok "AOAI endpoint: $($aoaiObj.properties.endpoint)"

Write-Step "Validating deployment '$AoaiDeploymentName'"
$dep = az cognitiveservices account deployment show -g $AoaiResourceGroup -n $AoaiAccountName --deployment-name $AoaiDeploymentName -o json 2>$null
if (-not $dep) {
    Fail "Deployment '$AoaiDeploymentName' not found on '$AoaiAccountName'."
}
Write-Ok "Deployment exists"

# ---------- 5. RBAC for current user ----------
Write-Step "Checking RBAC of signed-in user on the subscription"

$scope = "/subscriptions/$($account.id)"
$allowed = @("Owner", "User Access Administrator")
$assignee = $null

# Try Graph first (object id). If CAE/MFA blocks it, fall back to UPN.
try {
    $oid = (az ad signed-in-user show --query id -o tsv 2>$null)
    if (-not [string]::IsNullOrWhiteSpace($oid)) { $assignee = $oid }
} catch { }

if (-not $assignee) {
    Write-Warn2 "Could not resolve object id from Graph (likely CAE/MFA). Falling back to UPN."
    $assignee = $account.user.name
}

$roles = az role assignment list --assignee $assignee --scope $scope --include-inherited --query "[].roleDefinitionName" -o tsv 2>$null

if ([string]::IsNullOrWhiteSpace($roles)) {
    Write-Warn2 "Could not list role assignments for '$assignee'. Skipping pre-check."
    Write-Warn2 "If you are not Owner/User Access Administrator, 'azd up' will fail at role assignment time."
    if (-not $YesToAll) {
        $ans = Read-Host "Continue anyway? (y/N)"
        if ($ans -notmatch '^(y|yes)$') { Fail "Aborted by user." }
    }
} else {
    $roleList = ($roles -split "`n" | Where-Object { $_ } | ForEach-Object { $_.Trim() })
    $has = $false
    foreach ($r in $roleList) { if ($allowed -contains $r) { $has = $true; break } }
    if ($has) {
        Write-Ok "User can assign RBAC at subscription scope (roles: $($roleList -join ', '))"
    } else {
        Write-Warn2 "Signed-in user lacks 'Owner' or 'User Access Administrator' at subscription scope."
        Write-Warn2 "Roles found: $($roleList -join ', ')"
        if (-not $YesToAll) {
            $ans = Read-Host "Continue anyway? (y/N)"
            if ($ans -notmatch '^(y|yes)$') { Fail "Aborted by user." }
        }
    }
}

# ---------- 6. Register resource providers ----------
Write-Step "Registering required resource providers"
$providers = @(
    "Microsoft.App",
    "Microsoft.OperationalInsights",
    "Microsoft.ContainerRegistry",
    "Microsoft.CognitiveServices"
)
foreach ($p in $providers) {
    $state = az provider show -n $p --query registrationState -o tsv 2>$null
    if ($state -eq "Registered") {
        Write-Ok "$p already registered"
    } else {
        Write-Host "    Registering $p ..." -ForegroundColor DarkGray
        az provider register -n $p --wait | Out-Null
        Write-Ok "$p registered"
    }
}

# ---------- 7. Initialize azd environment ----------
Write-Step "Configuring azd environment '$EnvironmentName'"
$existingEnvs = (azd env list --output json 2>$null | ConvertFrom-Json) | ForEach-Object { $_.Name }
if ($existingEnvs -contains $EnvironmentName) {
    azd env select $EnvironmentName | Out-Null
    Write-Ok "Selected existing azd env '$EnvironmentName'"
} else {
    azd env new $EnvironmentName | Out-Null
    Write-Ok "Created azd env '$EnvironmentName'"
}

azd env set AZURE_SUBSCRIPTION_ID         $account.id           | Out-Null
azd env set AZURE_LOCATION                $Location             | Out-Null
azd env set AZURE_OPENAI_RESOURCE_GROUP   $AoaiResourceGroup    | Out-Null
azd env set AZURE_OPENAI_ACCOUNT_NAME     $AoaiAccountName      | Out-Null
azd env set AZURE_OPENAI_DEPLOYMENT_NAME  $AoaiDeploymentName   | Out-Null
Write-Ok "azd env variables set"

# ---------- 7b. Choose build mode (local Docker vs ACR remote build) ----------
Write-Step "Selecting container build mode"

function Test-DockerRunning {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { return $false }
    try {
        docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

$dockerRunning = Test-DockerRunning
if ($dockerRunning) { Write-Ok "Docker daemon is running" }
else                { Write-Warn2 "Docker daemon not detected" }

$chosen = $BuildMode
if ($chosen -eq "ask") {
    if ($YesToAll) {
        $chosen = if ($dockerRunning) { "local" } else { "remote" }
        Write-Ok "Auto-selected build mode: $chosen"
    } else {
        Write-Host "    Choose build mode:" -ForegroundColor DarkGray
        Write-Host "      [L] Local Docker  (requires Docker Desktop running)" -ForegroundColor DarkGray
        Write-Host "      [R] Remote build  (image built in Azure Container Registry)" -ForegroundColor DarkGray
        $default = if ($dockerRunning) { "L" } else { "R" }
        $ans = Read-Host "Selection (L/R) [default: $default]"
        if ([string]::IsNullOrWhiteSpace($ans)) { $ans = $default }
        switch -Regex ($ans.Trim().ToUpper()) {
            '^L'  { $chosen = "local" }
            '^R'  { $chosen = "remote" }
            default { Fail "Invalid selection '$ans'." }
        }
    }
}

if ($chosen -eq "local" -and -not $dockerRunning) {
    Write-Warn2 "Local build requested but Docker daemon is not running."
    if (-not $YesToAll) {
        $ans = Read-Host "Start Docker Desktop now and retry detection? (y/N)"
        if ($ans -match '^(y|yes)$') {
            $dd = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
            if (Test-Path $dd) {
                Start-Process $dd | Out-Null
                Write-Host "    Waiting for Docker to become ready..." -ForegroundColor DarkGray
                for ($i = 0; $i -lt 60; $i++) {
                    Start-Sleep -Seconds 2
                    if (Test-DockerRunning) { $dockerRunning = $true; break }
                }
            } else {
                Write-Warn2 "Docker Desktop not found at '$dd'. Start it manually."
            }
        }
    }
    if (-not $dockerRunning) {
        Fail "Docker is still not running. Re-run with -BuildMode remote, or start Docker Desktop."
    }
    Write-Ok "Docker is now running"
}

# Toggle remoteBuild in azure.yaml accordingly
$azureYaml = Join-Path $PSScriptRoot "azure.yaml"
$content = Get-Content $azureYaml -Raw
if ($chosen -eq "remote") {
    if ($content -notmatch "remoteBuild:\s*true") {
        if ($content -match "remoteBuild:\s*false") {
            $content = $content -replace "remoteBuild:\s*false", "remoteBuild: true"
        } else {
            $content = $content -replace "(?m)(^\s+context:\s*\.\s*)$", "`$1`r`n      remoteBuild: true"
        }
        Set-Content -Path $azureYaml -Value $content -NoNewline
    }
    Write-Ok "azure.yaml configured for ACR remote build"
} else {
    if ($content -match "remoteBuild:\s*true") {
        $content = $content -replace "(?m)^\s+remoteBuild:\s*true\s*\r?\n", ""
        Set-Content -Path $azureYaml -Value $content -NoNewline
    }
    Write-Ok "azure.yaml configured for local Docker build"
}

# ---------- 8. Bicep build (lint) ----------
Write-Step "Compiling Bicep to validate syntax"
az bicep build --file infra/main.bicep | Out-Null
Write-Ok "Bicep compiled successfully"

# ---------- 9. Provision preview ----------
if (-not $SkipPreview) {
    Write-Step "Previewing changes (azd provision --preview)"
    azd provision --preview
    if (-not $YesToAll) {
        $ans = Read-Host "Proceed with 'azd up'? (y/N)"
        if ($ans -notmatch '^(y|yes)$') { Fail "Aborted by user." }
    }
}

# ---------- 10. Deploy ----------
Write-Step "Running 'azd up'"
azd up --no-prompt
if ($LASTEXITCODE -ne 0) { Fail "'azd up' failed." }

# ---------- 11. Post-deploy: set ingress target port to 8501 ----------
Write-Step "Updating Container App ingress target port to 8501 (Streamlit)"
$envValues = azd env get-values
$rgName  = ($envValues | Select-String '^AZURE_RESOURCE_GROUP=')   | ForEach-Object { ($_ -split '=', 2)[1].Trim('"') }
$appName = ($envValues | Select-String '^AZURE_CONTAINER_APP_NAME=') | ForEach-Object { ($_ -split '=', 2)[1].Trim('"') }

if ($rgName -and $appName) {
    $currentPort = az containerapp ingress show -g $rgName -n $appName --query "targetPort" -o tsv 2>$null
    if ($currentPort -ne "8501") {
        az containerapp ingress update -g $rgName -n $appName --target-port 8501 --type external -o none
        if ($LASTEXITCODE -eq 0) { Write-Ok "Ingress target port set to 8501" }
        else                     { Write-Warn2 "Failed to update ingress target port; do it manually." }
    } else {
        Write-Ok "Ingress already on port 8501"
    }
} else {
    Write-Warn2 "Could not read RG/app name from azd env; skipping ingress port fix."
}

Write-Step "Done"
$fqdn = $envValues | Select-String '^AZURE_CONTAINER_APP_FQDN=' | ForEach-Object { ($_ -split '=', 2)[1].Trim('"') }
if ($fqdn) {
    Write-Host "    App URL: https://$fqdn" -ForegroundColor Green
}
