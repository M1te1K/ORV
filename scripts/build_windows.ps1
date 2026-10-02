$ErrorActionPreference = 'Stop'

python -m PyInstaller --clean --noconfirm ORVISimulator.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }

$exe = Join-Path (Get-Location) 'dist/ORVISimulator.exe'
if (-not (Test-Path $exe)) { throw "Missing build output: $exe" }

New-Item -ItemType Directory -Path 'releases' -Force | Out-Null
Compress-Archive -LiteralPath $exe -DestinationPath 'releases/ORVISimulator-Windows-x64.zip' -Force
Write-Host 'Created releases/ORVISimulator-Windows-x64.zip'
