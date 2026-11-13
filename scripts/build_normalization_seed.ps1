param(
    [Parameter(Mandatory = $false)]
    [string]$AnalysisDir = ".\analysis",

    [Parameter(Mandatory = $false)]
    [string]$OutputCsv = ".\analysis\normalization_seed.csv",

    [Parameter(Mandatory = $false)]
    [string]$OutputSql = ".\sql\003_seed_normalization_map.sql"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Format-Whitespace {
    param([string]$Value)
    return (($Value -replace "\s+", " ").Trim())
}

function ConvertTo-Text {
    param($Value)
    if ($null -eq $Value) { return "" }
    return [string]$Value
}

function ConvertTo-SizeCode {
    param([string]$Raw)

    $value = Format-Whitespace -Value (ConvertTo-Text -Value $Raw)
    $lower = $value.ToLowerInvariant()

    if ($lower -eq "") { return "unknown" }
    if ($lower -match "^\?+$|^\-+$|^n/?a$|^na$") { return "unknown" }

    if ($lower -match "1\s*/\s*8") { return "1/8 pg" }
    if ($lower -match "1\s*/\s*6") { return "1/6 pg" }
    if ($lower -match "1\s*/\s*4") { return "1/4 pg" }
    if ($lower -match "1\s*/\s*3") { return "1/3 pg" }
    if ($lower -match "1\s*/\s*2") { return "1/2 pg" }
    if ($lower -match "3\s*/\s*4") { return "3/4 pg" }
    if ($lower -match "full|^1$|^1\s*pg|^pg$") { return "full pg" }
    if ($lower -match "cover") { return "cover" }

    $clean = ($lower -replace "\.", "" -replace "-", " " -replace "page", "pg")
    return Format-Whitespace -Value $clean
}

function ConvertTo-SectionCode {
    param([string]$Raw)

    $value = Format-Whitespace -Value (ConvertTo-Text -Value $Raw)
    $lower = $value.ToLowerInvariant()

    if ($lower -eq "") { return "unknown" }
    if ($lower -in @("- -", "--", "-", "?", "??", "cal?", "n/a", "na")) { return "unknown" }

    $clean = ($lower -replace "\.", "" -replace "-", " ")
    return Format-Whitespace -Value $clean
}

function ConvertTo-SalesCode {
    param([string]$Raw)

    $value = Format-Whitespace -Value (ConvertTo-Text -Value $Raw)
    if ($value -eq "") { return "UNASSIGNED" }

    return $value.ToUpperInvariant()
}

function ConvertTo-BillingCode {
    param([string]$Raw)

    $value = Format-Whitespace -Value (ConvertTo-Text -Value $Raw)
    $lower = $value.ToLowerInvariant()

    if ($lower -eq "") { return "unbilled" }
    if ($lower -in @("x", "yes", "true", "y", "1")) { return "billed" }
    if ($lower -in @("na", "n/a")) { return "not_applicable" }

    return $lower
}

function ConvertTo-SqlLiteral {
    param([string]$Value)
    return ($Value -replace "'", "''")
}

$domainFiles = @(
    @{ Domain = "size"; File = "ads_size_distinct.csv"; Normalize = "ConvertTo-SizeCode" },
    @{ Domain = "section"; File = "ads_section_distinct.csv"; Normalize = "ConvertTo-SectionCode" },
    @{ Domain = "sales"; File = "ads_sales_distinct.csv"; Normalize = "ConvertTo-SalesCode" },
    @{ Domain = "billed"; File = "ads_billed_distinct.csv"; Normalize = "ConvertTo-BillingCode" }
)

$rows = @()

foreach ($entry in $domainFiles) {
    $path = Join-Path $AnalysisDir $entry.File
    if (-not (Test-Path $path)) {
        throw "Missing analysis input: $path"
    }

    $source = Import-Csv -Path $path

    foreach ($item in $source) {
        $raw = [string]$item.$($entry.Domain.Substring(0,1).ToUpper() + $entry.Domain.Substring(1))
        if ($entry.Domain -eq "sales") { $raw = [string]$item.Sales }
        if ($entry.Domain -eq "size") { $raw = [string]$item.Size }
        if ($entry.Domain -eq "section") { $raw = [string]$item.Section }
        if ($entry.Domain -eq "billed") { $raw = [string]$item.Billed }

        $cnt = 0
        if ($item.PSObject.Properties.Name -contains "Cnt") {
            $cnt = [int]$item.Cnt
        }

        $rawValue = Format-Whitespace -Value (ConvertTo-Text -Value $raw)
        $normalized = & $entry.Normalize $rawValue

        $rows += [pscustomobject]@{
            Domain = $entry.Domain
            RawValue = $rawValue
            NormalizedValue = $normalized
            SourceCount = $cnt
            Notes = "First-pass auto map"
        }
    }
}

$rows = $rows |
    Group-Object Domain, RawValue |
    ForEach-Object { $_.Group | Sort-Object SourceCount -Descending | Select-Object -First 1 } |
    Sort-Object Domain, RawValue

$rows | Export-Csv -Path $OutputCsv -NoTypeInformation -Encoding UTF8

$sqlLines = @()
$sqlLines += "INSERT INTO ad_normalization_map (domain, raw_value, normalized_value, notes) VALUES"

for ($i = 0; $i -lt $rows.Count; $i++) {
    $row = $rows[$i]
    $domain = ConvertTo-SqlLiteral -Value $row.Domain
    $rawValue = ConvertTo-SqlLiteral -Value $row.RawValue
    $normalized = ConvertTo-SqlLiteral -Value $row.NormalizedValue
    $notes = ConvertTo-SqlLiteral -Value $row.Notes

    $line = "('$domain', '$rawValue', '$normalized', '$notes')"
    if ($i -lt ($rows.Count - 1)) {
        $line += ","
    }

    $sqlLines += $line
}

$sqlLines += "ON DUPLICATE KEY UPDATE"
$sqlLines += "    normalized_value = VALUES(normalized_value),"
$sqlLines += "    notes = VALUES(notes);"

Set-Content -Path $OutputSql -Value $sqlLines -Encoding UTF8

Write-Host "Generated normalization seed CSV: $OutputCsv"
Write-Host "Generated normalization seed SQL: $OutputSql"
Write-Host "Rows: $($rows.Count)"
