param(
  [string]$Plan = 'out/video/narration_plan.json',
  [string]$OutDir = 'out/video/audio',
  [int]$Rate = 2
)
Add-Type -AssemblyName System.Speech
$segs = Get-Content $Plan -Raw -Encoding UTF8 | ConvertFrom-Json
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('Microsoft Huihui Desktop')
$s.Rate = $Rate
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
foreach ($seg in $segs) {
  $path = Join-Path $OutDir ("seg{0:D2}.wav" -f [int]$seg.i)
  $s.SetOutputToWaveFile($path)
  $s.Speak([string]$seg.text)
  $s.SetOutputToNull()
  Write-Output ("ok {0} {1}" -f $seg.i, $path)
}
