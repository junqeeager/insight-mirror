# ====================================
# 个人画像系统 - 一键端口转发配置
# 请以管理员身份运行 PowerShell
# ====================================

Write-Host ""
Write-Host "====================================" -ForegroundColor Cyan
Write-Host "  个人画像系统 - 端口转发配置" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

# 获取 WSL IP
Write-Host "📡 获取 WSL2 IP..." -ForegroundColor Yellow
$wslIP = (wsl hostname -I).Trim().Split(" ")[0]
Write-Host "  WSL2 IP: $wslIP" -ForegroundColor Green

# 删除旧规则（如果有）
Write-Host ""
Write-Host "清理旧规则..." -ForegroundColor Yellow
netsh interface portproxy delete v4tov4 listenport=8501 listenaddress=0.0.0.0 2>$null
netsh advfirewall firewall delete rule name="Personal Profile 8501" 2>$null

# 添加端口转发
Write-Host ""
Write-Host "配置端口转发 0.0.0.0:8501 -> ${wslIP}:8501..." -ForegroundColor Yellow
netsh interface portproxy add v4tov4 listenport=8501 listenaddress=0.0.0.0 connectport=8501 connectaddress=$wslIP

# 添加防火墙规则
Write-Host "配置防火墙规则..." -ForegroundColor Yellow
netsh advfirewall firewall add rule name="Personal Profile 8501" dir=in action=allow protocol=TCP localport=8501

# 验证配置
Write-Host ""
Write-Host "====================================" -ForegroundColor Cyan
Write-Host "  验证配置" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "端口转发规则:" -ForegroundColor Yellow
netsh interface portproxy show all | Select-String "8501"

Write-Host ""
Write-Host "防火墙规则:" -ForegroundColor Yellow
netsh advfirewall firewall show rule name="Personal Profile 8501" | Select-String "Rule Name|Enabled|Action"

# 获取公网IP
Write-Host ""
Write-Host "====================================" -ForegroundColor Cyan
Write-Host "  访问地址" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

$publicIP = (Invoke-WebRequest -Uri "https://api.ipify.org" -UseBasicParsing).Content
Write-Host "公网 IP: $publicIP" -ForegroundColor Green
Write-Host ""
Write-Host "请将域名 506ikun.space 解析到: $publicIP" -ForegroundColor Yellow
Write-Host ""
Write-Host "访问地址:" -ForegroundColor Yellow
Write-Host "  http://$publicIP:8501" -ForegroundColor Green
Write-Host "  http://506ikun.space:8501 (DNS生效后)" -ForegroundColor Green
Write-Host ""
Write-Host "====================================" -ForegroundColor Cyan
Write-Host "  配置完成！" -ForegroundColor Green
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

# 测试连接
Write-Host "测试端口监听..." -ForegroundColor Yellow
$test = Test-NetConnection -ComputerName localhost -Port 8501 -WarningAction SilentlyContinue
if ($test.TcpTestSucceeded) {
    Write-Host "  ✅ 端口 8501 可达" -ForegroundColor Green
} else {
    Write-Host "  ❌ 端口 8501 不可达" -ForegroundColor Red
}

Write-Host ""
Write-Host "按任意键退出..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
