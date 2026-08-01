param(
  [string]$BaseUrl = $env:LOCAL_AI_BASE_URL,
  [string]$Model = $(if ($env:LOCAL_AI_REQUEST_MODEL) { $env:LOCAL_AI_REQUEST_MODEL } else { "ds4flash" }),
  [string]$Prompt,
  [switch]$ConfigureOpenCode,
  [string]$ConfigPath = "$HOME\.config\opencode\opencode.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $BaseUrl) {
  $BaseUrl = "http://127.0.0.1:8083/v1"
}

function Resolve-LocalAiBaseUrl {
  param([string]$Value)

  $parsed = $null
  if ([string]::IsNullOrWhiteSpace($Value) -or
      $Value -match '[\x00-\x20\x7f]' -or
      -not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$parsed)) {
    throw "Invalid base URL. Use an absolute http(s) URL without whitespace."
  }
  if ($parsed.Scheme -notin @("http", "https") -or
      [string]::IsNullOrWhiteSpace($parsed.Host) -or
      $parsed.UserInfo -or $parsed.Query -or $parsed.Fragment) {
    throw "Invalid base URL. Credentials, query strings and fragments are not allowed."
  }
  $parsed.AbsoluteUri.TrimEnd('/')
}

function Get-LocalAiApiKey {
  $key = $env:LOCAL_AI_API_KEY
  if ([string]::IsNullOrWhiteSpace($key) -or
      $key.Length -gt 4096 -or
      $key -match '[\x00-\x20\x7f]' -or
      $key -in @("CHANGE_ME", "CHANGE_ME_LONG_RANDOM_KEY")) {
    throw "Missing or invalid LOCAL_AI_API_KEY. Load it from a trusted secret source."
  }
  $key
}

$BaseUrl = Resolve-LocalAiBaseUrl -Value $BaseUrl

function Invoke-LocalAiPrompt {
  param([string]$Text)

  $apiKey = Get-LocalAiApiKey

  $body = @{
    model = $Model
    messages = @(@{ role = "user"; content = $Text })
    temperature = 0.15
    max_tokens = 512
  } | ConvertTo-Json -Depth 8

  $headers = @{
    Authorization = "Bearer $apiKey"
    "Content-Type" = "application/json"
  }

  $response = Invoke-RestMethod -Method Post -Uri "$BaseUrl/chat/completions" -Headers $headers -Body $body
  if ($response.choices -and $response.choices[0].message.content) {
    $response.choices[0].message.content
  } elseif ($response.PSObject.Properties.Name -contains "error") {
    throw $response.error.message
  } else {
    $response | ConvertTo-Json -Depth 8
  }
}

function Write-OpenCodeConfig {
  $dir = Split-Path -Parent $ConfigPath
  New-Item -ItemType Directory -Force -Path $dir | Out-Null

  $config = [ordered]@{
    '$schema' = "https://opencode.ai/config.json"
    model = "ds4-local/$Model"
    small_model = "ds4-local/$Model"
    provider = @{
      "ds4-local" = @{
        name = "DS4 Intel tailnet profile"
        npm = "@ai-sdk/openai-compatible"
        options = @{
          baseURL = '{env:LOCAL_AI_BASE_URL}'
          apiKey = '{env:LOCAL_AI_API_KEY}'
          timeout = 1800000
          chunkTimeout = 180000
        }
        models = @{
          $Model = @{
            name = "DeepSeek V4 Flash DS4 GGUF"
            limit = @{ context = 100000; output = 32768 }
          }
        }
      }
    }
    compaction = @{ auto = $true; prune = $true; reserved = 2048 }
    snapshot = $false
    watcher = @{
      ignore = @(".git/**", "node_modules/**", "dist/**", "build/**", ".venv/**", "venv/**", "__pycache__/**", "*.gguf", "*.bin", "*.sqlite", "*.db")
    }
  }

  $config | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 -Path $ConfigPath
  "wrote $ConfigPath"
}

if (-not $ConfigureOpenCode -and -not $Prompt) {
  @"
Usage:
  Set LOCAL_AI_API_KEY in this process from a trusted secret source, then run:
  powershell -ExecutionPolicy Bypass -File .\scripts\local-ai-client.ps1 -BaseUrl http://127.0.0.1:8083/v1 -Prompt 'Rispondi solo OK'
  powershell -ExecutionPolicy Bypass -File .\scripts\local-ai-client.ps1 -BaseUrl http://127.0.0.1:8083/v1 -ConfigureOpenCode
"@
  exit 0
}

if ($ConfigureOpenCode) {
  Write-OpenCodeConfig
}

if ($Prompt) {
  Invoke-LocalAiPrompt -Text $Prompt
}
