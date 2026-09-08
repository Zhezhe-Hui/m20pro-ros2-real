[CmdletBinding()]
param(
    [Alias("Host")]
    [string]$RobotHost = $env:M20PRO_104_HOST,
    [string]$RemoteDir = "/home/user",
    [string]$Target = "/home/user/m20pro_real_ros2_ws",
    [ValidateSet("move", "shadow")]
    [string]$Mode = "move",
    [string]$Bundle = "",
    [string]$Revision = $env:M20PRO_BUNDLE_REVISION,
    [string]$EdgeHost = $env:M20PRO_EDGE_HOST,
    [switch]$RestartEdge106,
    [switch]$RequireFieldReady,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RobotHost)) {
    $RobotHost = "user@10.21.31.104"
}
if ([string]::IsNullOrWhiteSpace($EdgeHost)) {
    $EdgeHost = "user@10.21.31.106"
}

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required. Install or enable Windows OpenSSH Client first."
    }
}

Require-Command "ssh"
Require-Command "scp"

$ScriptPath = $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($ScriptPath)) {
    throw "Cannot resolve script path."
}
$ScriptDir = Split-Path -Parent $ScriptPath
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$DistDir = Join-Path $RepoRoot "dist"

if ([string]::IsNullOrWhiteSpace($Bundle)) {
    if (-not (Test-Path $DistDir)) {
        throw "dist directory not found: $DistDir. Run scripts/local_make_104_source_bundle.sh first."
    }
    $latest = Get-ChildItem -Path $DistDir -Filter "m20pro_real_ros2_ws_*.tgz" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -eq $latest) {
        throw "No source bundle found in $DistDir. Run scripts/local_make_104_source_bundle.sh first."
    }
    $BundlePath = $latest.FullName
} else {
    $BundlePath = (Resolve-Path $Bundle).Path
}

$ShaPath = "$BundlePath.sha256"
if (-not (Test-Path $ShaPath)) {
    throw "sha256 file not found: $ShaPath"
}

$InstallerPath = Join-Path (Split-Path -Parent $BundlePath) "104_install_source_bundle.sh"
if (-not (Test-Path $InstallerPath)) {
    $InstallerPath = Join-Path $DistDir "104_install_source_bundle.sh"
}
if (-not (Test-Path $InstallerPath)) {
    throw "104_install_source_bundle.sh not found next to bundle or in dist/"
}

if ([string]::IsNullOrWhiteSpace($Revision)) {
    $RevisionPath = "$BundlePath.revision"
    if (Test-Path $RevisionPath) {
        $Revision = (Get-Content -Path $RevisionPath -TotalCount 1).Trim()
    }
}
if ([string]::IsNullOrWhiteSpace($Revision)) {
    $Revision = "$(Split-Path -Leaf $BundlePath)-bundle"
}

$BundleName = Split-Path -Leaf $BundlePath
$ShaName = Split-Path -Leaf $ShaPath
$InstallerName = Split-Path -Leaf $InstallerPath
$InitialRequireReadyText = if ($RequireFieldReady.IsPresent -and -not $RestartEdge106.IsPresent) { "1" } else { "0" }
$RemoteRunnerName = ".m20pro_deploy_bundle_runner_$(Get-Date -Format 'yyyyMMdd_HHmmss').sh"
$RemoteRunnerPath = "$RemoteDir/$RemoteRunnerName"
$StageDir = Join-Path ([System.IO.Path]::GetTempPath()) ".m20pro_deploy_stage_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
$StagedBundlePath = Join-Path $StageDir $BundleName
$StagedShaPath = Join-Path $StageDir $ShaName
$StagedInstallerPath = Join-Path $StageDir $InstallerName

function Stage-File {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourcePath,
        [Parameter(Mandatory = $true)]
        [string]$DestinationDir
    )
    if (-not (Test-Path $DestinationDir)) {
        New-Item -ItemType Directory -Path $DestinationDir | Out-Null
    }
    $destination = Join-Path $DestinationDir (Split-Path -Leaf $SourcePath)
    Copy-Item -LiteralPath $SourcePath -Destination $destination -Force
    return $destination
}

function Cleanup-TempArtifacts {
    param(
        [string]$StagePath,
        [string]$RunnerFile
    )
    if (Test-Path $StagePath) {
        try {
            [System.IO.Directory]::Delete($StagePath, $true)
        } catch {
            Remove-Item -LiteralPath $StagePath -Recurse -Force -ErrorAction SilentlyContinue
        }
        try {
            Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "if exist `"$StagePath`" rmdir /s /q `"$StagePath`"" -Wait -NoNewWindow | Out-Null
        } catch {
            Remove-Item -LiteralPath $StagePath -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    if (Test-Path $RunnerFile) {
        try {
            [System.IO.File]::Delete($RunnerFile)
        } catch {
            Remove-Item -LiteralPath $RunnerFile -Force -ErrorAction SilentlyContinue
        }
        try {
            Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "if exist `"$RunnerFile`" del /f /q `"$RunnerFile`"" -Wait -NoNewWindow | Out-Null
        } catch {
            Remove-Item -LiteralPath $RunnerFile -Force -ErrorAction SilentlyContinue
        }
    }
}

$RemoteScript = @'
set -euo pipefail
REMOTE_DIR="$1"
BUNDLE_NAME="$2"
SHA_NAME="$3"
TARGET="$4"
MODE="$5"
REVISION="$6"
REQUIRE_FIELD_READY="$7"

cd "${REMOTE_DIR}"
sha256sum -c "${SHA_NAME}"
chmod +x ./104_install_source_bundle.sh
M20PRO_BUNDLE_REVISION="${REVISION}" \
  bash ./104_install_source_bundle.sh "./${BUNDLE_NAME}" "${TARGET}" "${MODE}"

"${TARGET}/scripts/104_verify_dddmr_field_test_deploy.sh"

set +e
"${TARGET}/scripts/104_accept_dddmr_field_test.sh"
ACCEPT_CODE="$?"
set -e

"${TARGET}/scripts/104_dddmr_field_test_report.sh" || true

if [[ "${REQUIRE_FIELD_READY}" == "1" && "${ACCEPT_CODE}" -ne 0 ]]; then
  echo "[windows_deploy_104_bundle] DDDMR acceptance failed with code ${ACCEPT_CODE}" >&2
  exit "${ACCEPT_CODE}"
fi

echo "[windows_deploy_104_bundle] deployment finished; DDDMR acceptance exit=${ACCEPT_CODE}"
'@

$RunnerPath = Join-Path ([System.IO.Path]::GetTempPath()) $RemoteRunnerName

Write-Host "[windows_deploy_104_bundle] bundle=$BundlePath"
Write-Host "[windows_deploy_104_bundle] sha256=$ShaPath"
Write-Host "[windows_deploy_104_bundle] installer=$InstallerPath"
Write-Host "[windows_deploy_104_bundle] runner=$RunnerPath"
Write-Host "[windows_deploy_104_bundle] stage=$StageDir"
Write-Host "[windows_deploy_104_bundle] remote=${RobotHost}:$RemoteDir"
Write-Host "[windows_deploy_104_bundle] edge=${EdgeHost} restart_edge_106=$($RestartEdge106.IsPresent)"
Write-Host "[windows_deploy_104_bundle] target=$Target mode=$Mode revision=$Revision"

if ($DryRun.IsPresent) {
    Write-Host "[windows_deploy_104_bundle] DRY RUN"
    Write-Host "scp `"$StagedBundlePath`" `"$StagedShaPath`" `"$StagedInstallerPath`" `"${RobotHost}:$RemoteDir/`""
    Write-Host "scp `"$RunnerPath`" `"${RobotHost}:$RemoteRunnerPath`""
    Write-Host "ssh -tt $RobotHost bash $RemoteRunnerPath $RemoteDir $BundleName $ShaName $Target $Mode $Revision $InitialRequireReadyText"
    if ($RestartEdge106.IsPresent) {
        Write-Host "ssh -tt $EdgeHost sudo -v '&&' sudo -n systemctl restart m20pro-edge-scan-106.service '&&' sudo -n systemctl is-active --quiet m20pro-edge-scan-106.service"
        Write-Host "ssh -tt $RobotHost bash -lc '<verify + accept + report after 106 restart>'"
    }
    Cleanup-TempArtifacts -StagePath $StageDir -RunnerFile $RunnerPath
    exit 0
}

try {
    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($RunnerPath, $RemoteScript, $Utf8NoBom)
    $StagedBundlePath = Stage-File -SourcePath $BundlePath -DestinationDir $StageDir
    $StagedShaPath = Stage-File -SourcePath $ShaPath -DestinationDir $StageDir
    $StagedInstallerPath = Stage-File -SourcePath $InstallerPath -DestinationDir $StageDir

& scp $StagedBundlePath $StagedShaPath $StagedInstallerPath "${RobotHost}:$RemoteDir/"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
& scp $RunnerPath "${RobotHost}:$RemoteRunnerPath"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$SshArgs = @(
    "-tt",
    $RobotHost,
    "bash",
    $RemoteRunnerPath,
    $RemoteDir,
    $BundleName,
    $ShaName,
    $Target,
    $Mode,
    $Revision,
    $InitialRequireReadyText
)
& ssh @SshArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($RestartEdge106.IsPresent) {
    Write-Host "[windows_deploy_104_bundle] restarting 106 edge scan on $EdgeHost"
    & ssh -tt $EdgeHost "sudo -v && sudo -n systemctl restart m20pro-edge-scan-106.service && sudo -n systemctl is-active --quiet m20pro-edge-scan-106.service"
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    $PostEdgeCommand = "set +e; `"$Target/scripts/104_verify_dddmr_field_test_deploy.sh`"; VERIFY_CODE=`$?; `"$Target/scripts/104_accept_dddmr_field_test.sh`"; ACCEPT_CODE=`$?; `"$Target/scripts/104_dddmr_field_test_report.sh`" || true; if [[ `$VERIFY_CODE -ne 0 ]]; then exit `$VERIFY_CODE; fi; exit `$ACCEPT_CODE"
    & ssh -tt $RobotHost "bash -lc '$PostEdgeCommand'"
    $PostEdgeAcceptCode = $LASTEXITCODE
    if ($RequireFieldReady.IsPresent -and $PostEdgeAcceptCode -ne 0) {
        exit $PostEdgeAcceptCode
    }
    Write-Host "[windows_deploy_104_bundle] post-106-restart DDDMR acceptance exit=$PostEdgeAcceptCode"
}

exit 0
} finally {
    Cleanup-TempArtifacts -StagePath $StageDir -RunnerFile $RunnerPath
}
