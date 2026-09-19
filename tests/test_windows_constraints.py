from pathlib import Path

ROOT = Path(__file__).parents[1]
CONSTRAINTS = ROOT / "packaging" / "windows" / "constraints-windows.txt"
BUILD_REQUIREMENTS = ROOT / "packaging" / "windows" / "requirements-build.txt"
WINDOWS_WORKFLOW = ROOT / ".github" / "workflows" / "windows-package.yml"
BUNDLE_SCRIPT = ROOT / "packaging" / "windows" / "bundle-tesseract.ps1"
TESSERACT_LOCK = ROOT / "packaging" / "windows" / "tesseract-bundle.lock.json"


def test_windows_constraints_pin_critical_packages() -> None:
    pins = {
        line.split("==", 1)[0].lower(): line.split("==", 1)[1]
        for line in CONSTRAINTS.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }

    assert {
        "docling",
        "transformers",
        "torch",
        "torchvision",
        "pyside6",
        "ocrmypdf",
        "rapidocr",
        "onnxruntime",
        "pyinstaller",
        "pyinstaller-hooks-contrib",
    } <= pins.keys()
    assert pins["transformers"] == "4.51.3"


def test_windows_package_install_uses_constraints() -> None:
    requirements = BUILD_REQUIREMENTS.read_text(encoding="utf-8")
    workflow = WINDOWS_WORKFLOW.read_text(encoding="utf-8")

    assert "-c constraints-windows.txt" in requirements
    assert ".[full,dev]" in requirements
    assert "pip install -r packaging/windows/requirements-build.txt" in workflow


def test_windows_workflow_caches_pinned_tesseract_installer() -> None:
    workflow = WINDOWS_WORKFLOW.read_text(encoding="utf-8")

    assert "Read Tesseract lock metadata" in workflow
    assert "actions/cache@v4" in workflow
    assert "build/tesseract-cache" in workflow
    assert "windows-tesseract-installer-${{ runner.os }}" in workflow
    assert "${{ env.TESSERACT_LOCK_VERSION }}" in workflow
    assert "${{ env.TESSERACT_LOCK_SHA256 }}" in workflow
    assert "tesseract-bundle.lock.json" in workflow


def test_bundle_script_uses_7zip_extraction_with_timeout() -> None:
    script = BUNDLE_SCRIPT.read_text(encoding="utf-8")

    assert "--connect-timeout 30" in script
    assert "--max-time 300" in script
    assert "--retry 3" in script
    assert "Get-Command 7z.exe" in script
    assert "dl.7z" in script
    assert "Wait-Process -Id $ExtractionProcess.Id -Timeout $TimeoutSeconds" in script
    assert "taskkill.exe /PID $ExtractionProcess.Id /T /F" in script
    assert "Start-Process -FilePath $ArchivePath" not in script
    assert "Remove-Item $PluginDirectory -Recurse -Force" in script
    assert "Expected exactly one extracted Tesseract root containing tesseract.exe" in script
    assert "Write-Host \"[bundle-tesseract]" in script
    assert "Get-ChildItem -Path $SourceDirectory -Filter \"*.dll\" -File" in script
    assert "No root-level DLL files were found in extracted Tesseract root" in script
    assert "Copy-Item $Executable (Join-Path $DestinationDirectory \"tesseract.exe\") -Force" in script
    assert "Copy-Item $Dll.FullName (Join-Path $DestinationDirectory $Dll.Name) -Force" in script
    assert "Invoke-CheckedExecutable -ExecutablePath $BundledExecutable -Arguments @(\"--version\")" in script
    assert "Invoke-CheckedExecutable -ExecutablePath $BundledExecutable -Arguments @(\"--list-langs\")" in script
    assert "failed (exit code $ExitCode). Output:" in script
    assert "foreach ($Language in $BundledLanguages)" in script
    assert "Copy-Item (Join-Path $Tessdata \"$Language.traineddata\") $DestinationTessdata -Force" in script
    assert "Copy-Item $SourceConfigs (Join-Path $DestinationTessdata \"configs\") -Recurse -Force" in script
    assert "Join-Path $DestinationTessdata \"configs\\hocr\"" in script


def test_windows_build_hashes_full_tesseract_payload() -> None:
    build_script = (ROOT / "packaging" / "windows" / "build.ps1").read_text(encoding="utf-8")

    assert "Get-ChildItem (Join-Path $Distribution \"tools\\tesseract\") -File -Recurse" in build_script
    assert "No bundled tesseract files were found for hashing." in build_script
    assert "$HashTargets += $RelativeTesseractFiles" in build_script
    assert "$HashTargets = $HashTargets | Sort-Object -Unique" in build_script


def test_windows_build_preserves_tesseract_installer_cache_outside_output_cleanup() -> None:
    build_script = (ROOT / "packaging" / "windows" / "build.ps1").read_text(encoding="utf-8")
    workflow = WINDOWS_WORKFLOW.read_text(encoding="utf-8")

    assert "[string]$InstallerCacheDirectory = \"\"" in build_script
    assert 'Join-Path $RepositoryRoot "build\\tesseract-cache"' in build_script
    assert "Remove-Item $OutputDirectory -Recurse -Force" in build_script
    assert "Remove-Item $InstallerCacheDirectory -Recurse -Force" not in build_script
    assert "-InstallerCacheDirectory $InstallerCacheDirectory" in build_script
    assert "build.ps1 -InstallerCacheDirectory build/tesseract-cache" in workflow


def test_windows_workflow_runs_hocr_smoke_test() -> None:
    workflow = WINDOWS_WORKFLOW.read_text(encoding="utf-8")

    assert "configs\\\\hocr" in workflow
    assert "tesseract-smoke.pgm" in workflow
    assert "& $BundledTesseract $SmokeInput $SmokeOutBase -l eng hocr" in workflow
    assert "$SmokeOutBase.hocr" in workflow
    assert "hOCR smoke output is empty" in workflow


def test_windows_build_supports_lite_package() -> None:
    build_script = (ROOT / "packaging" / "windows" / "build.ps1").read_text(encoding="utf-8")
    workflow = WINDOWS_WORKFLOW.read_text(encoding="utf-8")
    notes = (ROOT / "packaging" / "windows" / "PACKAGING_NOTES_LITE.txt").read_text(
        encoding="utf-8"
    )

    assert '[ValidateSet("Full", "Lite")]' in build_script
    assert '$PackageFlavor = "Full"' in build_script
    assert "build.ps1 -PackageFlavor Lite" in workflow
    assert "SourceDocumentConverter-Windows-x64-Full" in workflow
    assert "SourceDocumentConverter-Windows-x64-Lite" in workflow
    assert "Install Missing OCR Tools" in notes


def test_windows_workflow_smokes_lite_distribution_independently() -> None:
    workflow = WINDOWS_WORKFLOW.read_text(encoding="utf-8")

    assert "Smoke test Lite packaged executables" in workflow
    assert "$GuiPathLite = Join-Path $env:DIST_DIR_LITE \"SourceDocumentConverter.exe\"" in workflow
    assert "$GuiProcessLite = Start-Process -FilePath $GuiPathLite -ArgumentList \"--package-smoke-test\"" in workflow
    assert "Join-Path $env:DIST_DIR_LITE \"docling-tools.exe\") --help" in workflow
    assert "Join-Path $env:DIST_DIR_LITE \"docling-tools.exe\") --runtime-check" in workflow
    assert "Join-Path $env:DIST_DIR_LITE \"docling-tools.exe\") models download --help" in workflow


def test_windows_workflow_enforces_lite_negative_payload_assertions() -> None:
    workflow = WINDOWS_WORKFLOW.read_text(encoding="utf-8")

    assert "$ForbiddenPatterns = @(" in workflow
    assert "(?i)(^|[\\\\/])pikepdf([\\\\/]|$)" in workflow
    assert "(?i)(^|[\\\\/])qpdf\\\\.exe$" in workflow
    assert "(?i)(^|[\\\\/])libqpdf[^\\\\/]*\\\\.dll$" in workflow
    assert "(?i)(^|[\\\\/])gswin(32|64)c?\\\\.exe$" in workflow
    assert "(?i)(^|[\\\\/])gsdll(32|64)\\\\.dll$" in workflow
    assert "(?i)(^|[\\\\/])libgs[^\\\\/]*\\\\.dll$" in workflow
    assert "Lite package unexpectedly contains forbidden payload" in workflow


def test_tesseract_bundle_metadata_does_not_include_source_paths() -> None:
    script = BUNDLE_SCRIPT.read_text(encoding="utf-8")

    assert "\"Provenance: Pinned UB-Mannheim installer archive (checksum-verified extraction)\"" in script
    assert "\"Source directory: $SourceDirectory\"" not in script


def test_tesseract_lock_contains_version_and_checksum() -> None:
    lock_text = TESSERACT_LOCK.read_text(encoding="utf-8")

    assert '"version"' in lock_text
    assert '"sha256"' in lock_text
