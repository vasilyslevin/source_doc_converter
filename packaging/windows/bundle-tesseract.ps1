param(
    [Parameter(Mandatory = $true)]
    [string]$DestinationDirectory,
    [string]$SourceDirectory = "",
    [string]$WorkDirectory = "",
    [string]$InstallerCacheDirectory = ""
)

$ErrorActionPreference = "Stop"
$LockFile = Join-Path $PSScriptRoot "tesseract-bundle.lock.json"
if (-not (Test-Path $LockFile -PathType Leaf)) {
    throw "Missing lock file: $LockFile"
}
$LockData = Get-Content $LockFile -Raw | ConvertFrom-Json
$ExpectedVersion = "$($LockData.version)"
$DownloadUrl = "$($LockData.download_url)"
$ExpectedSha256 = "$($LockData.sha256)".ToLowerInvariant()
$RequiredRuntimeFiles = @($LockData.required_runtime_files)
$BundledLanguages = @($LockData.languages)
if ([string]::IsNullOrWhiteSpace($ExpectedVersion) -or [string]::IsNullOrWhiteSpace($DownloadUrl) -or [string]::IsNullOrWhiteSpace($ExpectedSha256)) {
    throw "Lock file is missing required fields (version, download_url, sha256)."
}
if ($BundledLanguages.Count -eq 0) {
    throw "Lock file must specify at least one required language."
}
$ExtractionTimeoutSeconds = 600

function Write-Stage {
    param([string]$Message)
    Write-Host "[bundle-tesseract] $Message"
}

function Download-Installer {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    $CurlCommand = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($null -ne $CurlCommand) {
        & $CurlCommand.Source `
            --fail `
            --location `
            --retry 3 `
            --retry-all-errors `
            --connect-timeout 30 `
            --max-time 300 `
            --output $Destination `
            $Url
        if ($LASTEXITCODE -eq 0) {
            return
        }
        throw "curl.exe download failed with exit code $LASTEXITCODE."
    }

    $LastError = $null
    foreach ($Attempt in 1..3) {
        try {
            Invoke-WebRequest -Uri $Url -OutFile $Destination -TimeoutSec 300
            return
        } catch {
            $LastError = $_
            if ($Attempt -lt 3) {
                Start-Sleep -Seconds 2
            }
        }
    }
    throw "Fallback download failed after 3 attempts: $LastError"
}

function Expand-InstallerArchive {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ArchivePath,
        [Parameter(Mandatory = $true)]
        [string]$ExtractDirectory,
        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds
    )

    $SevenZip = Get-Command 7z.exe -ErrorAction SilentlyContinue
    if ($null -eq $SevenZip) {
        throw "7z.exe was not found on PATH. Cannot extract Tesseract archive."
    }
    $SevenZipInput = Join-Path ([System.IO.Path]::GetDirectoryName($ArchivePath)) "dl.7z"
    Copy-Item $ArchivePath $SevenZipInput -Force

    $Arguments = @(
        "x",
        "-y",
        "-bd",
        "-bso1",
        "-bse1",
        "-o$ExtractDirectory",
        $SevenZipInput
    )
    Write-Stage "Launching 7-Zip extraction process."
    $ExtractionProcess = Start-Process -FilePath $SevenZip.Source -ArgumentList $Arguments -PassThru
    $ExtractionFinished = $true
    try {
        Wait-Process -Id $ExtractionProcess.Id -Timeout $TimeoutSeconds -ErrorAction Stop
    } catch {
        $ExtractionFinished = $false
    }
    if (-not $ExtractionFinished) {
        Write-Stage "7-Zip extraction timed out after $TimeoutSeconds seconds. Terminating process tree."
        & taskkill.exe /PID $ExtractionProcess.Id /T /F | Out-Null
        throw "7-Zip extraction timed out after $TimeoutSeconds seconds (PID $($ExtractionProcess.Id))."
    }
    if ($ExtractionProcess.ExitCode -ne 0) {
        throw "7-Zip extraction failed with exit code $($ExtractionProcess.ExitCode)."
    }
    Write-Stage "7-Zip extraction process completed."
}

function Resolve-TesseractRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExtractDirectory
    )

    $Candidates = @(
        Get-ChildItem -Path $ExtractDirectory -Filter "tesseract.exe" -File -Recurse |
            Where-Object {
                $_.FullName -notlike "*\`$PLUGINSDIR\*" -and $_.FullName -notlike "*\`$PLUGINSDIR"
            } |
            ForEach-Object { $_.Directory.FullName } |
            Sort-Object -Unique
    )
    if ($Candidates.Count -eq 0) {
        throw "No extracted Tesseract root containing tesseract.exe was found."
    }
    if ($Candidates.Count -ne 1) {
        $Listed = $Candidates -join "; "
        throw "Expected exactly one extracted Tesseract root containing tesseract.exe, found $($Candidates.Count): $Listed"
    }
    return $Candidates[0]
}

function Invoke-CheckedExecutable {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExecutablePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$OperationName
    )

    $CommandOutput = & $ExecutablePath @Arguments 2>&1
    $ExitCode = $LASTEXITCODE
    $OutputText = ($CommandOutput | ForEach-Object { "$_" }) -join [Environment]::NewLine
    if ($ExitCode -ne 0) {
        throw "$OperationName failed (exit code $ExitCode). Output:`n$OutputText"
    }
    return ,$CommandOutput
}

$BundleRoot = if ([string]::IsNullOrWhiteSpace($WorkDirectory)) {
    Join-Path ([System.IO.Path]::GetTempPath()) "source-doc-converter\tesseract-bundle"
} else {
    [System.IO.Path]::GetFullPath($WorkDirectory)
}
$InstallerCacheRoot = if ([string]::IsNullOrWhiteSpace($InstallerCacheDirectory)) {
    Join-Path $BundleRoot "download"
} else {
    [System.IO.Path]::GetFullPath($InstallerCacheDirectory)
}
$DownloadDirectory = $InstallerCacheRoot
$ExtractDirectory = Join-Path $BundleRoot "extract"
$ArchivePath = Join-Path $DownloadDirectory "tesseract-ocr-w64-setup-$ExpectedVersion.exe"

$SourceProvided = -not [string]::IsNullOrWhiteSpace($SourceDirectory)
if ($SourceProvided) {
    $SourceDirectory = [System.IO.Path]::GetFullPath($SourceDirectory)
}
$DestinationDirectory = [System.IO.Path]::GetFullPath($DestinationDirectory)

if (-not $SourceProvided) {
    Write-Stage "Preparing download and extraction directories."
    New-Item -ItemType Directory -Path $DownloadDirectory -Force | Out-Null
    New-Item -ItemType Directory -Path $ExtractDirectory -Force | Out-Null

    $HaveValidArchive = $false
    if (Test-Path $ArchivePath -PathType Leaf) {
        Write-Stage "Found cached installer archive at $ArchivePath. Verifying checksum."
        $CachedHash = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($CachedHash -eq $ExpectedSha256) {
            $HaveValidArchive = $true
            Write-Stage "Cached installer checksum verified."
        } else {
            Write-Stage "Cached installer checksum mismatch; deleting cached archive."
            Remove-Item $ArchivePath -Force
        }
    }

    if (-not $HaveValidArchive) {
        Write-Stage "Downloading pinned Tesseract installer."
        Download-Installer -Url $DownloadUrl -Destination $ArchivePath
        Write-Stage "Installer download completed."
    }

    Write-Stage "Verifying installer checksum."
    $ActualHash = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualHash -ne $ExpectedSha256) {
        throw "Tesseract archive checksum mismatch. Expected $ExpectedSha256, got $ActualHash."
    }
    Write-Stage "Installer checksum verified."

    if (Test-Path $ExtractDirectory) {
        Remove-Item $ExtractDirectory -Recurse -Force
    }
    New-Item -ItemType Directory -Path $ExtractDirectory -Force | Out-Null
    Write-Stage "Extracting checksum-verified installer archive using 7-Zip."
    Expand-InstallerArchive -ArchivePath $ArchivePath -ExtractDirectory $ExtractDirectory -TimeoutSeconds $ExtractionTimeoutSeconds
    $PluginDirectory = Join-Path $ExtractDirectory '$PLUGINSDIR'
    if (Test-Path $PluginDirectory -PathType Container) {
        Write-Stage "Removing extraction-only directory: $PluginDirectory"
        Remove-Item $PluginDirectory -Recurse -Force
    }

    Write-Stage "Locating extracted Tesseract root."
    $SourceDirectory = Resolve-TesseractRoot -ExtractDirectory $ExtractDirectory
    Write-Stage "Using extracted Tesseract root: $SourceDirectory"
}

$Executable = Join-Path $SourceDirectory "tesseract.exe"
$Tessdata = Join-Path $SourceDirectory "tessdata"
if (-not (Test-Path $Executable -PathType Leaf)) {
    throw "Tesseract executable not found: $Executable"
}

Write-Stage "Checking extracted Tesseract version."
$VersionResult = Invoke-CheckedExecutable -ExecutablePath $Executable -Arguments @("--version") -OperationName "Extracted Tesseract version check"
$VersionOutput = ($VersionResult | Select-Object -First 1).ToString()
if ($VersionOutput -notmatch [regex]::Escape($ExpectedVersion)) {
    throw "Expected Tesseract $ExpectedVersion, but found: $VersionOutput"
}

foreach ($Relative in $RequiredRuntimeFiles) {
    $RuntimePath = Join-Path $SourceDirectory $Relative
    if (-not (Test-Path $RuntimePath -PathType Leaf)) {
        throw "Required Tesseract runtime file missing: $Relative"
    }
}
foreach ($Language in $BundledLanguages) {
    $DataFile = Join-Path $Tessdata "$Language.traineddata"
    if (-not (Test-Path $DataFile -PathType Leaf)) {
        throw "Required Tesseract language data not found: $DataFile"
    }
}
$SourceConfigs = Join-Path $Tessdata "configs"
if (-not (Test-Path (Join-Path $SourceConfigs "hocr") -PathType Leaf)) {
    throw "Required Tesseract config file not found: tessdata/configs/hocr"
}
$SourceTessconfigs = Join-Path $Tessdata "tessconfigs"

if (Test-Path $DestinationDirectory) {
    Remove-Item $DestinationDirectory -Recurse -Force
}
New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null
Write-Stage "Copying Tesseract executable and all root-level runtime DLLs into package directory."
$RootDlls = @(Get-ChildItem -Path $SourceDirectory -Filter "*.dll" -File)
if ($RootDlls.Count -eq 0) {
    throw "No root-level DLL files were found in extracted Tesseract root: $SourceDirectory"
}
Copy-Item $Executable (Join-Path $DestinationDirectory "tesseract.exe") -Force
foreach ($Dll in $RootDlls) {
    Copy-Item $Dll.FullName (Join-Path $DestinationDirectory $Dll.Name) -Force
}

$DestinationTessdata = Join-Path $DestinationDirectory "tessdata"
if (Test-Path $DestinationTessdata) {
    Remove-Item $DestinationTessdata -Recurse -Force
}
New-Item -ItemType Directory -Path $DestinationTessdata -Force | Out-Null
foreach ($Language in $BundledLanguages) {
    Copy-Item (Join-Path $Tessdata "$Language.traineddata") $DestinationTessdata -Force
}
Copy-Item $SourceConfigs (Join-Path $DestinationTessdata "configs") -Recurse -Force
if (Test-Path $SourceTessconfigs -PathType Container) {
    Copy-Item $SourceTessconfigs (Join-Path $DestinationTessdata "tessconfigs") -Recurse -Force
}
if (-not (Test-Path (Join-Path $DestinationTessdata "configs\hocr") -PathType Leaf)) {
    throw "Bundled Tesseract missing required config file: tessdata/configs/hocr"
}

$BundledExecutable = Join-Path $DestinationDirectory "tesseract.exe"
$BundledTessdata = Join-Path $DestinationDirectory "tessdata"
$PreviousTessdataPrefix = $env:TESSDATA_PREFIX
try {
    Write-Stage "Verifying bundled Tesseract version in destination directory."
    $BundledVersionResult = Invoke-CheckedExecutable -ExecutablePath $BundledExecutable -Arguments @("--version") -OperationName "Bundled Tesseract version check"
    $BundledVersionLine = ($BundledVersionResult | Select-Object -First 1).ToString()
    if ($BundledVersionLine -notmatch [regex]::Escape($ExpectedVersion)) {
        $BundledVersionText = ($BundledVersionResult | ForEach-Object { "$_" }) -join [Environment]::NewLine
        throw "Bundled Tesseract version mismatch. Expected $ExpectedVersion. Output:`n$BundledVersionText"
    }
    Write-Stage "Verifying bundled language data with tesseract --list-langs."
    $env:TESSDATA_PREFIX = $BundledTessdata
    $Languages = Invoke-CheckedExecutable -ExecutablePath $BundledExecutable -Arguments @("--list-langs") -OperationName "Bundled Tesseract language listing"
    foreach ($Language in $BundledLanguages) {
        if ($Languages -notcontains $Language) {
            $LanguageOutput = ($Languages | ForEach-Object { "$_" }) -join [Environment]::NewLine
            throw "Bundled Tesseract missing required language: $Language. Output:`n$LanguageOutput"
        }
    }
} finally {
    $env:TESSDATA_PREFIX = $PreviousTessdataPrefix
}
Write-Stage "Bundled language verification succeeded."

@(
    "Distribution: UB-Mannheim.TesseractOCR",
    "Version: $ExpectedVersion",
    "Download URL: $DownloadUrl",
    "SHA-256: $ExpectedSha256",
    "Languages: $($BundledLanguages -join ', ')",
    "Provenance: Pinned UB-Mannheim installer archive (checksum-verified extraction)",
    "Runtime language data: tessdata",
    "Required configs: tessdata/configs/hocr"
) | Set-Content (Join-Path $DestinationDirectory "BUNDLE_INFO.txt") -Encoding utf8
Write-Stage "Tesseract bundle metadata written."
