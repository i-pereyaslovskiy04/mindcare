$dir = Join-Path $PSScriptRoot "migrations"
$out = Join-Path $PSScriptRoot "full_schema.sql"

$header = @"
-- =====================================================================
-- ПОЛНАЯ СХЕМА БАЗЫ ДАННЫХ
-- Проект: «Психологическая помощь в ДонГУ»
-- СУБД: PostgreSQL 15+
-- Дата: $(Get-Date -Format 'yyyy-MM-dd')
--
-- Создание БД:
--   createdb -U postgres dongu_psychology_portal
--   psql -U postgres -d dongu_psychology_portal -f full_schema.sql
-- =====================================================================

"@

[IO.File]::WriteAllText($out, $header, [Text.Encoding]::UTF8)

$files = Get-ChildItem $dir -Filter "*.sql" | Sort-Object Name
foreach ($f in $files) {
    $content = [IO.File]::ReadAllText($f.FullName, [Text.Encoding]::UTF8)
    [IO.File]::AppendAllText($out, $content + "`n", [Text.Encoding]::UTF8)
}

Write-Host "Created: $out ($((Get-Item $out).Length) bytes, $($files.Count) files merged)"
