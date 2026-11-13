param(
    [Parameter(Mandatory = $true)]
    [string]$DatabasePath,

    [Parameter(Mandatory = $false)]
    [string]$OutputDir = ".\analysis"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path $DatabasePath)) {
    throw "Database not found: $DatabasePath"
}

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

$connString = "Provider=Microsoft.ACE.OLEDB.12.0;Data Source=$DatabasePath;Persist Security Info=False;Mode=Read;"
$conn = New-Object System.Data.OleDb.OleDbConnection($connString)
$conn.Open()

function Invoke-Scalar {
    param(
        [System.Data.OleDb.OleDbConnection]$Connection,
        [string]$Sql
    )

    $cmd = $Connection.CreateCommand()
    $cmd.CommandText = $Sql
    return $cmd.ExecuteScalar()
}

function Invoke-DataTable {
    param(
        [System.Data.OleDb.OleDbConnection]$Connection,
        [string]$Sql
    )

    $cmd = $Connection.CreateCommand()
    $cmd.CommandText = $Sql

    $adapter = New-Object System.Data.OleDb.OleDbDataAdapter($cmd)
    $table = New-Object System.Data.DataTable
    [void]$adapter.Fill($table)
    return $table
}

function ConvertTo-AccessIdentifier {
    param([string]$Name)
    return "[$($Name.Replace(']', ']]'))]"
}

function Get-ColumnValue {
    param(
        [System.Data.DataRow]$Row,
        [string]$ColumnName
    )

    if ($Row.Table.Columns.Contains($ColumnName)) {
        return $Row[$ColumnName]
    }

    return $null
}

$tables = $conn.GetSchema("Tables") |
    Where-Object { $_.TABLE_TYPE -eq "TABLE" -and $_.TABLE_NAME -notlike "MSys*" } |
    Select-Object -ExpandProperty TABLE_NAME |
    Sort-Object

$rowCounts = @()
$columnRows = @()
$allColumns = $conn.GetSchema("Columns")

foreach ($tableName in $tables) {
    $quotedTable = ConvertTo-AccessIdentifier -Name $tableName
    $count = Invoke-Scalar -Connection $conn -Sql "SELECT COUNT(*) FROM $quotedTable"

    $rowCounts += [pscustomobject]@{
        TableName = $tableName
        RowCount = [int64]$count
    }

    $columns = $allColumns |
        Where-Object { $_.TABLE_NAME -eq $tableName } |
        Sort-Object ORDINAL_POSITION

    foreach ($column in $columns) {
        $columnRows += [pscustomobject]@{
            TableName = $tableName
            ColumnName = Get-ColumnValue -Row $column -ColumnName "COLUMN_NAME"
            DataType = Get-ColumnValue -Row $column -ColumnName "DATA_TYPE"
            TypeName = Get-ColumnValue -Row $column -ColumnName "TYPE_NAME"
            CharacterMaxLength = Get-ColumnValue -Row $column -ColumnName "CHARACTER_MAXIMUM_LENGTH"
            NumericPrecision = Get-ColumnValue -Row $column -ColumnName "NUMERIC_PRECISION"
            NumericScale = Get-ColumnValue -Row $column -ColumnName "NUMERIC_SCALE"
            IsNullable = Get-ColumnValue -Row $column -ColumnName "IS_NULLABLE"
            OrdinalPosition = Get-ColumnValue -Row $column -ColumnName "ORDINAL_POSITION"
        }
    }
}

$quality = [ordered]@{}

if ($tables -contains "tbl_ProgressAds_01") {
    $quality.TotalAds = [int64](Invoke-Scalar -Connection $conn -Sql "SELECT COUNT(*) FROM tbl_ProgressAds_01")
    $quality.AdsWithNullAccount = [int64](Invoke-Scalar -Connection $conn -Sql "SELECT COUNT(*) FROM tbl_ProgressAds_01 WHERE AccountNumber IS NULL OR Trim(AccountNumber) = ''")
    $quality.AdsWithNullDateRun = [int64](Invoke-Scalar -Connection $conn -Sql "SELECT COUNT(*) FROM tbl_ProgressAds_01 WHERE DateRun IS NULL")
    $quality.AdsWithNullDateSold = [int64](Invoke-Scalar -Connection $conn -Sql "SELECT COUNT(*) FROM tbl_ProgressAds_01 WHERE DateSold IS NULL")

    $orphanSql = @"
SELECT COUNT(*)
FROM tbl_ProgressAds_01 AS a
LEFT JOIN tbl_ProgressContacts_01 AS c
    ON a.AccountNumber = c.AccountNumber
WHERE (a.AccountNumber IS NOT NULL AND Trim(a.AccountNumber) <> '')
  AND c.AccountNumber IS NULL
"@
    $quality.OrphanAds = [int64](Invoke-Scalar -Connection $conn -Sql $orphanSql)

    $sizeDistinct = Invoke-DataTable -Connection $conn -Sql "SELECT Size, COUNT(*) AS Cnt FROM tbl_ProgressAds_01 GROUP BY Size ORDER BY COUNT(*) DESC"
    $sizeDistinct | Export-Csv -Path (Join-Path $OutputDir "ads_size_distinct.csv") -NoTypeInformation

    $sectionDistinct = Invoke-DataTable -Connection $conn -Sql "SELECT Section, COUNT(*) AS Cnt FROM tbl_ProgressAds_01 GROUP BY Section ORDER BY COUNT(*) DESC"
    $sectionDistinct | Export-Csv -Path (Join-Path $OutputDir "ads_section_distinct.csv") -NoTypeInformation

    $salesDistinct = Invoke-DataTable -Connection $conn -Sql "SELECT Sales, COUNT(*) AS Cnt FROM tbl_ProgressAds_01 GROUP BY Sales ORDER BY COUNT(*) DESC"
    $salesDistinct | Export-Csv -Path (Join-Path $OutputDir "ads_sales_distinct.csv") -NoTypeInformation

    $billedDistinct = Invoke-DataTable -Connection $conn -Sql "SELECT Billed, COUNT(*) AS Cnt FROM tbl_ProgressAds_01 GROUP BY Billed ORDER BY COUNT(*) DESC"
    $billedDistinct | Export-Csv -Path (Join-Path $OutputDir "ads_billed_distinct.csv") -NoTypeInformation
}

$rowCounts | Export-Csv -Path (Join-Path $OutputDir "table_row_counts.csv") -NoTypeInformation
$columnRows | Export-Csv -Path (Join-Path $OutputDir "schema_columns.csv") -NoTypeInformation

$summary = [pscustomobject]@{
    DatabasePath = $DatabasePath
    GeneratedAtUtc = (Get-Date).ToUniversalTime().ToString("o")
    TableCount = $tables.Count
    Tables = $tables
    Quality = $quality
}

$summary | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $OutputDir "profile_summary.json") -Encoding UTF8

$conn.Close()

Write-Host "Profile complete. Output folder: $OutputDir"
