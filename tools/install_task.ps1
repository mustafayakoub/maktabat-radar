<#
  يُنشئ مهمّةَ ويندوز تمسحُ المكتباتِ كلَّ ساعة، فيعرفُ الرادارُ متى وصلَ كلُّ كتاب.

  التشغيل (بصلاحيّات المستخدم نفسِه، لا يلزم مديرُ النظام):
      powershell -ExecutionPolicy Bypass -File tools\install_task.ps1
  والإلغاء:
      powershell -ExecutionPolicy Bypass -File tools\install_task.ps1 -Remove

  ⚠ المهمّةُ تُسجَّلُ باسم المستخدم الحاليّ لتصلَ إلى مشاركةِ السيرفر؛ ومهمّةٌ تعملُ
  بحساب SYSTEM لا ترى مشاركةَ الشبكة فلا تُستعمَل.
#>
param(
    [int]$EveryMinutes = 60,
    [switch]$Remove,
    [string]$TaskName = "رادار المكتبات — مسحٌ دوريّ"
)

$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$cmd = Join-Path $root "tools\scan.cmd"

if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Output "أُلغيت المهمّة: $TaskName"
    } else {
        Write-Output "لا مهمّةَ بهذا الاسم."
    }
    return
}

if (-not (Test-Path $cmd)) { throw "لم أجد $cmd" }

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$cmd`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "يمسحُ الهاردَ والسيرفرَ ويكتبُ سجلَّ وصولِ الكتب (maktabat-radar)." | Out-Null

Write-Output "سُجّلت المهمّة: $TaskName — كلَّ $EveryMinutes دقيقة."
Write-Output "السجلّ: $root\data\logs\"
Write-Output "للتشغيل الآن: Start-ScheduledTask -TaskName '$TaskName'"
