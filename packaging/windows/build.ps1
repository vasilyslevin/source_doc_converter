param(
    [string]$Python = "python",
    [string]$OutputDirectory = "",
    [string]$TesseractRoot = "",
    [string]$InstallerCacheDirectory = "",
    [ValidateSet("Full", "Lite")]
    [string]$PackageFlavor = "Full"
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $RepositoryRoot "build\windows"
} else {
    $OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
}
if ([string]::IsNullOrWhiteSpace($InstallerCacheDirectory)) {
    $InstallerCacheDirectory = Join-Path $RepositoryRoot "build\tesseract-cache"
} else {
    $InstallerCacheDirectory = [System.IO.Path]::GetFullPath($InstallerCacheDirectory)
}

$SourceRoot = Join-Path $RepositoryRoot "src"
$GuiEntry = Join-Path $PSScriptRoot "SourceDocumentConverter.py"
$ToolsEntry = Join-Path $PSScriptRoot "docling-tools.py"
$OcrEntry = Join-Path $SourceRoot "source_doc_converter\ocrmypdf_entry.py"
$IconGenerator = Join-Path $PSScriptRoot "create_icon.py"
$IconSource = Join-Path $SourceRoot "source_doc_converter\assets\app_icon.svg"
$IconPath = Join-Path $OutputDirectory "SourceDocumentConverter.ico"
$TesseractBundler = Join-Path $PSScriptRoot "bundle-tesseract.ps1"
$TorchvisionRuntimeHook = Join-Path $PSScriptRoot "pyi_rth_torchvision.py"
$PackagingNotes = Join-Path $PSScriptRoot "PACKAGING_NOTES.txt"
$LitePackagingNotes = Join-Path $PSScriptRoot "PACKAGING_NOTES_LITE.txt"
$BuildManifestName = "build_manifest.json"
$StagingDirectory = Join-Path $OutputDirectory "dist"
$WorkDirectory = Join-Path $OutputDirectory "work"
$SpecDirectory = Join-Path $OutputDirectory "spec"

if (Test-Path $OutputDirectory) {
    Remove-Item $OutputDirectory -Recurse -Force
}
New-Item -ItemType Directory -Path $StagingDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $WorkDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $SpecDirectory -Force | Out-Null

& $Python $IconGenerator $IconPath
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $IconPath -PathType Leaf)) {
    throw "Could not generate the Windows application icon."
}

$InspectTorchvisionEnvironment = @'
import importlib.metadata
import importlib.util
import json
import struct
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version
import torch
import torchvision


def read_pe_machine(path: Path) -> int:
    with path.open("rb") as fh:
        dos_header = fh.read(64)
        if len(dos_header) < 64 or dos_header[:2] != b"MZ":
            raise SystemExit(f"Not a PE file: {path}")
        pe_offset = struct.unpack("<I", dos_header[60:64])[0]
        fh.seek(pe_offset)
        pe_header = fh.read(6)
        if len(pe_header) < 6 or pe_header[:4] != b"PE\0\0":
            raise SystemExit(f"Invalid PE header: {path}")
        return struct.unpack("<H", pe_header[4:6])[0]


torch_version = Version(torch.__version__.split("+", 1)[0])
torchvision_version = Version(torchvision.__version__.split("+", 1)[0])
requires_dist = importlib.metadata.metadata("torchvision").get_all("Requires-Dist") or []
torch_requirement = None
for item in requires_dist:
    requirement = Requirement(item)
    if requirement.name.lower() == "torch":
        torch_requirement = requirement
        break
if torch_requirement is None:
    raise SystemExit("torchvision metadata does not declare a torch dependency.")
if not torch_requirement.specifier.contains(str(torch_version), prereleases=True):
    raise SystemExit(
        f"Incompatible torch/torchvision pair: torch {torch.__version__} does not satisfy {torch_requirement.specifier}."
    )
if torch.version.cuda is not None:
    raise SystemExit(
        f"Expected CPU torch wheel for packaging, but torch reports CUDA runtime {torch.version.cuda}."
    )

spec = importlib.util.find_spec("torchvision")
if spec is None or spec.submodule_search_locations is None:
    raise SystemExit("torchvision package was not found")
torchvision_root = Path(next(iter(spec.submodule_search_locations)))
matches = sorted(torchvision_root.glob("_C*.pyd"))
if not matches:
    raise SystemExit("torchvision native extension _C.pyd was not found")
extension = matches[0]
if read_pe_machine(extension) != 0x8664:
    raise SystemExit(f"torchvision native extension has unexpected architecture: {extension}")
torch_lib_dir = Path(torch.__file__).resolve().parent / "lib"
if not torch_lib_dir.is_dir():
    raise SystemExit(f"Torch DLL directory was not found: {torch_lib_dir}")
if not any(torch_lib_dir.glob("*.dll")):
    raise SystemExit(f"Torch DLL directory does not contain DLL files: {torch_lib_dir}")

print(
    json.dumps(
        {
            "torch_version": str(torch_version),
            "torchvision_version": str(torchvision_version),
            "torch_requirement": str(torch_requirement.specifier),
            "torchvision_extension": str(extension),
            "torchvision_root": str(torchvision_root),
            "torch_lib_dir": str(torch_lib_dir),
        }
    )
)
'@
$TorchvisionInfoJson = (& $Python -c $InspectTorchvisionEnvironment).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($TorchvisionInfoJson)) {
    throw "Could not inspect the installed torch/torchvision runtime."
}
$TorchvisionInfo = $TorchvisionInfoJson | ConvertFrom-Json
$TorchvisionExtension = [string]$TorchvisionInfo.torchvision_extension
$TorchvisionRoot = [string]$TorchvisionInfo.torchvision_root
$TorchLibDirectory = [string]$TorchvisionInfo.torch_lib_dir
if (-not (Test-Path $TorchvisionExtension -PathType Leaf)) {
    throw "Could not locate the installed torchvision native extension."
}
if (-not (Test-Path $TorchLibDirectory -PathType Container)) {
    throw "Could not locate the installed torch DLL directory."
}

$CheckSciPyRuntime = @'
import importlib
from scipy import ndimage

array_api_namespaces = (
    "scipy._external.array_api_compat",
    "scipy._lib.array_api_compat",
)
detected_namespace = None
for namespace in array_api_namespaces:
    try:
        importlib.import_module(f"{namespace}.numpy.fft")
    except ModuleNotFoundError:
        continue
    detected_namespace = namespace
    break

if detected_namespace is None:
    raise SystemExit(
        "SciPy array API compatibility module is unavailable "
        "(expected scipy._external.array_api_compat.numpy.fft or scipy._lib.array_api_compat.numpy.fft)."
    )

result = ndimage.gaussian_filter1d([1.0, 2.0, 3.0], sigma=0.1)
if len(result) != 3:
    raise SystemExit("SciPy ndimage pre-freeze check produced an unexpected result.")

print(detected_namespace)
'@
$ScipyArrayApiNamespace = (& $Python -c $CheckSciPyRuntime).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($ScipyArrayApiNamespace)) {
    throw "SciPy pre-freeze check failed."
}

$CommonArguments = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onedir",
    "--paths=$SourceRoot",
    "--distpath=$StagingDirectory",
    "--specpath=$SpecDirectory"
)
$DoclingArguments = @(
    "--collect-all=docling",
    "--collect-all=docling_core",
    "--collect-all=docling_parse",
    "--collect-all=pypdf",
    "--copy-metadata=pypdf",
    "--collect-all=rapidocr",
    "--collect-all=transformers",
    "--collect-submodules=$ScipyArrayApiNamespace.numpy",
    "--collect-binaries=torch",
    "--collect-binaries=torchvision",
    "--add-binary=$TorchvisionExtension;torchvision",
    "--add-binary=$TorchLibDirectory\\*.dll;torch\\lib",
    "--add-data=$TorchvisionRoot\\_meta_registrations.py;torchvision",
    "--runtime-hook=$TorchvisionRuntimeHook",
    "--hidden-import=docling.cli.tools",
    "--hidden-import=docling.document_converter",
    "--hidden-import=pypdf._reader",
    "--hidden-import=pypdf._writer"
)
$GuiArguments = $DoclingArguments + @(
    "--icon=$IconPath",
    "--add-data=$IconSource;source_doc_converter/assets"
)
$OcrArguments = @(
    "--collect-all=ocrmypdf",
    "--hidden-import=ocrmypdf.__main__"
)

function Invoke-PackageBuild {
    param(
        [string]$Name,
        [string]$EntryPoint,
        [string]$ConsoleMode,
        [string[]]$AdditionalArguments = @()
    )

    $Arguments = $CommonArguments + $AdditionalArguments + @(
        "--workpath=$(Join-Path $WorkDirectory $Name)",
        "--name=$Name",
        $ConsoleMode,
        $EntryPoint
    )
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed for $Name with exit code $LASTEXITCODE."
    }
}

Push-Location $RepositoryRoot
try {
    Invoke-PackageBuild -Name "SourceDocumentConverter" -EntryPoint $GuiEntry -ConsoleMode "--windowed" -AdditionalArguments $GuiArguments
    Invoke-PackageBuild -Name "docling-tools" -EntryPoint $ToolsEntry -ConsoleMode "--console" -AdditionalArguments $DoclingArguments
    if ($PackageFlavor -eq "Full") {
        Invoke-PackageBuild -Name "ocrmypdf" -EntryPoint $OcrEntry -ConsoleMode "--console" -AdditionalArguments $OcrArguments
    }

    $Distribution = Join-Path $StagingDirectory "SourceDocumentConverter"
    $ToolsDistribution = Join-Path $StagingDirectory "docling-tools"
    $GuiExecutable = Join-Path $Distribution "SourceDocumentConverter.exe"
    $ToolsExecutable = Join-Path $ToolsDistribution "docling-tools.exe"
    $OcrDistribution = Join-Path $StagingDirectory "ocrmypdf"
    $OcrExecutable = Join-Path $OcrDistribution "ocrmypdf.exe"

    if (-not (Test-Path $GuiExecutable -PathType Leaf)) {
        throw "SourceDocumentConverter.exe was not produced."
    }
    if (-not (Test-Path $ToolsExecutable -PathType Leaf)) {
        throw "docling-tools.exe was not produced."
    }
    if ($PackageFlavor -eq "Full" -and -not (Test-Path $OcrExecutable -PathType Leaf)) {
        throw "ocrmypdf.exe was not produced."
    }

    Copy-Item (Join-Path $ToolsDistribution "*") $Distribution -Recurse -Force
    if ($PackageFlavor -eq "Full") {
        Copy-Item (Join-Path $OcrDistribution "*") $Distribution -Recurse -Force
    }
    Remove-Item $ToolsDistribution -Recurse -Force
    if (Test-Path $OcrDistribution) {
        Remove-Item $OcrDistribution -Recurse -Force
    }

    $PackagedTorchvisionExtensions = Get-ChildItem -Path $Distribution -Filter "_C*.pyd" -File -Recurse |
        Where-Object { $_.FullName -like "*\\torchvision\\*" }
    if ($PackagedTorchvisionExtensions.Count -eq 0) {
        throw "Packaged torchvision native extension _C.pyd was not found."
    }

    $PackagedTorchLibDirectory = @(
        Join-Path $Distribution "torch\\lib",
        Join-Path $Distribution "_internal\\torch\\lib"
    ) | Where-Object { Test-Path $_ -PathType Container } | Select-Object -First 1
    if (-not $PackagedTorchLibDirectory) {
        throw "Packaged torch DLL directory was not found in torch\\lib or _internal\\torch\\lib."
    }
    if ((Get-ChildItem -Path $PackagedTorchLibDirectory -Filter "*.dll" -File).Count -eq 0) {
        throw "Packaged torch DLL directory does not contain DLL files."
    }

    & (Join-Path $Distribution "docling-tools.exe") --runtime-check
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged Docling runtime check failed with exit code $LASTEXITCODE."
    }

    if ($PackageFlavor -eq "Full") {
        $TesseractDestination = Join-Path $Distribution "tools\tesseract"
        $TesseractWorkDirectory = Join-Path $WorkDirectory "tesseract"
        if ([string]::IsNullOrWhiteSpace($TesseractRoot)) {
            & $TesseractBundler `
                -DestinationDirectory $TesseractDestination `
                -WorkDirectory $TesseractWorkDirectory `
                -InstallerCacheDirectory $InstallerCacheDirectory
        } else {
            & $TesseractBundler `
                -SourceDirectory $TesseractRoot `
                -DestinationDirectory $TesseractDestination `
                -WorkDirectory $TesseractWorkDirectory `
                -InstallerCacheDirectory $InstallerCacheDirectory
        }
        if ($LASTEXITCODE -ne 0) {
            throw "Tesseract bundling failed with exit code $LASTEXITCODE."
        }
    }

    Copy-Item (Join-Path $RepositoryRoot "LICENSE") $Distribution -Force
    Copy-Item (Join-Path $RepositoryRoot "THIRD_PARTY_NOTICES.md") $Distribution -Force
    if ($PackageFlavor -eq "Lite") {
        if (-not (Test-Path $LitePackagingNotes -PathType Leaf)) {
            throw "Missing Lite package notes file: $LitePackagingNotes"
        }
        Copy-Item $LitePackagingNotes (Join-Path $Distribution "PACKAGING_NOTES.txt") -Force
    } else {
        Copy-Item $PackagingNotes (Join-Path $Distribution "PACKAGING_NOTES.txt") -Force
    }

    $AppVersion = (& $Python -c "from source_doc_converter import __version__; print(__version__)").Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($AppVersion)) {
        throw "Could not determine application version for build manifest."
    }
    $CommitSha = $env:GITHUB_SHA
    if ([string]::IsNullOrWhiteSpace($CommitSha)) {
        $CommitSha = (& git rev-parse --verify HEAD 2>$null).Trim()
        if ($LASTEXITCODE -ne 0) {
            $CommitSha = $null
        }
    }
    $Manifest = [ordered]@{
        application_version = $AppVersion
        package_flavor      = $PackageFlavor
        source_commit_sha   = if ([string]::IsNullOrWhiteSpace($CommitSha)) { $null } else { $CommitSha }
    } | ConvertTo-Json -Depth 3
    Set-Content -LiteralPath (Join-Path $Distribution $BuildManifestName) -Encoding utf8 -Value $Manifest

    $HashTargets = @(
        "SourceDocumentConverter.exe",
        "docling-tools.exe",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "PACKAGING_NOTES.txt",
        $BuildManifestName
    )
    if ($PackageFlavor -eq "Full") {
        $HashTargets += @(
            "ocrmypdf.exe",
            "tools\tesseract\BUNDLE_INFO.txt"
        )
        $TesseractFiles = Get-ChildItem (Join-Path $Distribution "tools\tesseract") -File -Recurse |
            Sort-Object FullName
        if ($TesseractFiles.Count -eq 0) {
            throw "No bundled tesseract files were found for hashing."
        }
        $RelativeTesseractFiles = $TesseractFiles |
            ForEach-Object {
                $_.FullName.Substring($Distribution.Length + 1)
            }
        $HashTargets += $RelativeTesseractFiles
    }
    $HashTargets = $HashTargets | Sort-Object -Unique
    $Hashes = foreach ($RelativePath in $HashTargets) {
        $Target = Join-Path $Distribution $RelativePath
        if (-not (Test-Path $Target -PathType Leaf)) {
            throw "Cannot hash missing package file: $RelativePath"
        }
        $Digest = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash
        if ([string]::IsNullOrWhiteSpace($Digest)) {
            throw "Could not calculate SHA-256 for package file: $RelativePath"
        }
        "$($Digest.ToLowerInvariant())  $RelativePath"
    }
    $Hashes | Set-Content (Join-Path $Distribution "SHA256SUMS.txt") -Encoding utf8

    Write-Host "Windows development package created at: $Distribution"
} finally {
    Pop-Location
}
