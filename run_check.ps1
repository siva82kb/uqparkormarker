# Used by run.bat: what, if anything, is answering on the app's port?
#
# Prints lines of NAME=value. STATE is one of:
#   free     nothing is on the port
#   mine     this copy of the app is already running
#   other    a copy of the app in another folder (FOLDER, PID, BUSY follow)
#   unknown  some other program (PROGRAM follows, if it could be found)

param([int]$Port = 5000)

$here = $PSScriptRoot.TrimEnd('\')

try { (New-Object Net.Sockets.TcpClient('127.0.0.1', $Port)).Close() }
catch { "STATE=free"; exit 0 }

# Something answers. Ask it whether it is the app, and from which folder.
$who = $null
try { $who = Invoke-RestMethod -UseBasicParsing -Uri "http://127.0.0.1:$Port/whoami" -TimeoutSec 5 } catch {}

if ($who -and $who.app -eq 'uq-parkour-annotator') {
    if ("$($who.folder)".TrimEnd('\') -ieq $here) { "STATE=mine"; exit 0 }
    "STATE=other"
    "FOLDER=$($who.folder)"
    "PID=$($who.pid)"
    "BUSY=$($who.busy)"
    exit 0
}

"STATE=unknown"
try {
    $owner = (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
              Select-Object -First 1).OwningProcess
    "PROGRAM=$((Get-Process -Id $owner -ErrorAction Stop).ProcessName)"
} catch {}
exit 0
