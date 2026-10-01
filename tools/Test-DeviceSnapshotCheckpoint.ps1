$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'Collect-DeviceSnapshot.ps1'
$tokens=$null; $parseErrors=$null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($source,[ref]$tokens,[ref]$parseErrors)
if ($parseErrors.Count) { throw 'Bundled collector failed to parse.' }
# Load only these known pure helpers; this test never performs collection.
foreach ($functionName in @('Save', 'Sum-CapacityBytes')) {
    $functionAst = $ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $functionName}, $true)
    . ([ScriptBlock]::Create($functionAst.Extent.Text))
}
$twoModules = @([ordered]@{capacityBytes=8589934592L}, [ordered]@{capacityBytes=8589934592L})
if ((Sum-CapacityBytes $twoModules) -ne 17179869184L) { throw 'Installed RAM sum is not 16 GiB.' }
if ($null -ne (Sum-CapacityBytes @([ordered]@{capacityBytes=$null}))) { throw 'Unknown module became zero installed RAM.' }
$testDirectory = Join-Path ([IO.Path]::GetTempPath()) ('device-checkpoint-' + [Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($testDirectory)
$OutputPath = Join-Path $testDirectory 'checkpoint.json'
$CancelPath = Join-Path $testDirectory 'cancel'
$state = [ordered]@{phase='fixture'; value=1}
try {
    Save 'first'
    $state.value = 2
    Save 'second'
    $result = [IO.File]::ReadAllText($OutputPath) | ConvertFrom-Json
    if ($result.value -ne 2 -or $result.phase -ne 'second') { throw 'Checkpoint replacement lost the second value.' }
    if ([IO.File]::Exists($OutputPath + '.bak')) { throw 'Checkpoint backup was not cleaned.' }
    'PASS: Windows PowerShell checkpoint create/replace/backup cleanup and 2 x 8 GiB installed RAM / unknown capacity.'
} finally {
    foreach ($suffix in @('', '.bak', '.tmp')) { [IO.File]::Delete($OutputPath + $suffix) }
    [IO.Directory]::Delete($testDirectory)
}
