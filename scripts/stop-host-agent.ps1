Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*scripts\host_agent.py*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
