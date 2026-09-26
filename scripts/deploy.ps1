# Deployment script for Windows PowerShell
# Builds image remotely via GCP Cloud Build (no local Docker required!) and deploys to Cloud Run

$ErrorActionPreference = "Stop"

$ProjectId = if ($env:GCP_PROJECT_ID) { $env:GCP_PROJECT_ID } else { "project-dd21ce0e-1dd3-476c-af0" }
$Region = if ($env:GCP_REGION) { $env:GCP_REGION } else { "europe-west4" }
$ServiceName = if ($env:CLOUD_RUN_SERVICE) { $env:CLOUD_RUN_SERVICE } else { "tm-bingo" }
$RepoName = "tm-bingo-repo"
$ImageTag = "$Region-docker.pkg.dev/$ProjectId/$RepoName/${ServiceName}:latest"
$ServiceAccount = "tm-bingo-runner@$ProjectId.iam.gserviceaccount.com"

Write-Host "=== Deploying $ServiceName to Google Cloud Run ==="
Write-Host "Project:  $ProjectId"
Write-Host "Region:   $Region"
Write-Host "Image:    $ImageTag"
Write-Host "Service:  $ServiceName`n"

# 1. Build and push container image using Cloud Build (Runs on Google's cloud - NO local Docker needed!)
Write-Host "--> [1/2] Building container image with Cloud Build..."
$env:CLOUDSDK_METRICS_ENVIRONMENT = "datacloud.antigravity"
gcloud builds submit `
  --project="$ProjectId" `
  --tag="$ImageTag" `
  --quiet

# 2. Deploy to Cloud Run
Write-Host "--> [2/2] Deploying container image to Cloud Run..."
gcloud run deploy "$ServiceName" `
  --project="$ProjectId" `
  --image="$ImageTag" `
  --platform=managed `
  --region="$Region" `
  --allow-unauthenticated `
  --port=8080 `
  --max-instances=1 `
  --timeout=3600 `
  --service-account="$ServiceAccount" `
  --set-secrets="BASIC_AUTH=tm-bingo-basic-auth:latest,APP_PASSWORD_HASH=tm-bingo-password-hash:latest" `
  --quiet

# 3. Retrieve service URL
$ServiceUrl = gcloud run services describe "$ServiceName" `
  --project="$ProjectId" `
  --region="$Region" `
  --format="value(status.url)"

Write-Host "`n=== Deployment Successful ==="
Write-Host "Service URL: $ServiceUrl"
Write-Host "Short URL:   https://shorturl.fm/tm-bingo"
