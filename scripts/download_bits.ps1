param(
    [string[]]$Only = @()
)

$ErrorActionPreference = "Stop"
$base = "https://huggingface.co/datasets/minhSpaceX/home_credit/resolve/main"
$dest = Join-Path $PSScriptRoot "..\data\raw"
New-Item -ItemType Directory -Force -Path $dest | Out-Null

$files = [ordered]@{
    "HomeCredit_columns_description.csv" = 37383
    "application_train.csv"               = 166133370
    "previous_application.csv"            = 404973293
    "installments_payments.csv"           = 723118349
    "POS_CASH_balance.csv"                 = 392703158
    "credit_card_balance.csv"              = 424582605
    "bureau.csv"                           = 170016717
    "bureau_balance.csv"                   = 375592889
}

foreach ($name in $files.Keys) {
    if ($Only.Count -gt 0 -and $Only -notcontains $name) { continue }
    $target = Join-Path $dest $name
    $expected = $files[$name]
    if ((Test-Path $target) -and ((Get-Item $target).Length -eq $expected)) {
        Write-Output "SKIP $name"
        continue
    }
    if (Test-Path $target) { Remove-Item -LiteralPath $target -Force }
    Write-Output "BITS $name"
    Start-BitsTransfer -Source "$base/$name" -Destination $target -DisplayName "homecredit-$name" -Description "Home Credit public dataset" -Priority Foreground
    $actual = (Get-Item $target).Length
    if ($actual -ne $expected) { throw "Size mismatch for $name : $actual != $expected" }
    Write-Output "DONE $name $actual"
}
Write-Output "ALL_DONE"
