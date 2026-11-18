
param(
  [string]$root = "",
  [string]$title = "qqaibot-QQ",
  [int]$tries = 12
)
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class W {
  [DllImport("user32.dll", SetLastError=true)]
  public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, IntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out IntPtr lpdwResult);
}
'@
$rootL = $root.ToLower()
for ($i = 0; $i -lt $tries; $i++) {
  Start-Sleep -Seconds 5
  $procs = Get-CimInstance Win32_Process -Filter "Name='QQ.exe'" | Where-Object {
    ($_.ExecutablePath -and $_.ExecutablePath.ToLower().Contains($rootL)) -or
    ($_.CommandLine -and $_.CommandLine.ToLower().Contains($rootL))
  }
  if (-not $procs) { continue }
  foreach ($p in $procs) {
    $gp = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
    if ($gp -and $gp.MainWindowHandle -ne [IntPtr]::Zero) {
      $r = [IntPtr]::Zero
      [W]::SendMessageTimeout($gp.MainWindowHandle, 0x000C, [IntPtr]::Zero, $title, 2, 2000, [ref]$r) | Out-Null
    }
  }
  if ($i -ge 3) { break }   # ???????? QQ ?????????
}
