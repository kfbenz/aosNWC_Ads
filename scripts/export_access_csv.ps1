# Copyright 2026 Archdiocese of Seattle
# Author: Kevin F Benz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

param(
    [Parameter(Mandatory = $true)]
    [string]$DatabasePath,

    [Parameter(Mandatory = $false)]
    [string]$OutputDir = ".\exports\access_csv",

    [Parameter(Mandatory = $false)]
    [string[]]$Tables = @("tbl_ProgressContacts_01", "tbl_ProgressAds_01")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path $DatabasePath)) {
    throw "Database not found: $DatabasePath"
}

if (-not (Test-Path $OutputDir)) {
    New-Item -Path $OutputDir -ItemType Directory | Out-Null
}

$connString = "Provider=Microsoft.ACE.OLEDB.12.0;Data Source=$DatabasePath;Persist Security Info=False;Mode=Read;"
$conn = New-Object System.Data.OleDb.OleDbConnection($connString)
$conn.Open()

$availableTables = $conn.GetSchema("Tables") |
    Where-Object { $_.TABLE_TYPE -eq "TABLE" -and $_.TABLE_NAME -notlike "MSys*" } |
    Select-Object -ExpandProperty TABLE_NAME

foreach ($tableName in $Tables) {
    if ($availableTables -notcontains $tableName) {
        Write-Warning "Skipping missing table: $tableName"
        continue
    }

    $quoted = "[$($tableName.Replace(']', ']]'))]"
    $query = "SELECT * FROM $quoted"

    $cmd = $conn.CreateCommand()
    $cmd.CommandText = $query

    $adapter = New-Object System.Data.OleDb.OleDbDataAdapter($cmd)
    $dt = New-Object System.Data.DataTable
    [void]$adapter.Fill($dt)

    $safeName = ($tableName -replace '[^A-Za-z0-9_\-]', '_')
    $outPath = Join-Path $OutputDir ("$safeName.csv")

    $dt | Export-Csv -Path $outPath -NoTypeInformation -Encoding UTF8

    Write-Host "Exported $tableName -> $outPath ($($dt.Rows.Count) rows)"
}

$conn.Close()
Write-Host "Done."
