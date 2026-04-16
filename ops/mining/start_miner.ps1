# XMRig starter (PowerShell)
# Replace YOUR_WALLET_ADDRESS

$pool = "pool.supportxmr.com:3333"
$wallet = "YOUR_WALLET_ADDRESS"

Start-Process xmrig.exe -ArgumentList "-o $pool -u $wallet -p x -k --cpu-max-threads-hint=70"
