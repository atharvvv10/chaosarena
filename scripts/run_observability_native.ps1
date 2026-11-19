$ErrorActionPreference = "Stop"
$root = "D:\Projects\1\chaosarena"
$prom = Join-Path $root "tools\prometheus-2.53.2.windows-amd64\prometheus.exe"
$graf = Join-Path $root "tools\grafana-v11.2.0\bin\grafana-server.exe"

if (-not (Test-Path $prom)) { throw "Prometheus not found. Download it into tools/ first." }
if (-not (Test-Path $graf)) { throw "Grafana not found. Download it into tools/ first." }

Start-Process -FilePath $prom -ArgumentList @(
    "--config.file=$root\infra\local\prometheus.yml"
    "--storage.tsdb.path=$root\tools\prometheus-data"
    "--web.listen-address=:9090"
) -WindowStyle Hidden

$env:GF_PATHS_PROVISIONING = Join-Path $root "infra\local\provisioning"
$env:GF_SECURITY_ADMIN_PASSWORD = "admin"
$env:GF_USERS_ALLOW_SIGN_UP = "false"
Start-Process -FilePath $graf -ArgumentList @("--homepath=$root\tools\grafana-v11.2.0") -WindowStyle Hidden

Write-Host "Prometheus: http://localhost:9090"
Write-Host "Grafana:    http://localhost:3000  (admin / admin)"
