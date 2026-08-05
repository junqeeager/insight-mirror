# Windows 端口转发配置脚本
# 请以管理员身份运行此脚本

Write-Host "====================================" -ForegroundColor Cyan
Write-Host "  个人画像系统 - Windows 端口转发配置" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

# 获取 WSL IP
$wslIP = (wsl hostname -I).Trim().Split(" ")[0]
Write-Host "WSL2 IP: $wslIP" -ForegroundColor Yellow

# 配置端口转发
Write-Host ""
Write-Host "配置端口转发..." -ForegroundColor Green
netsh interface portproxy add v4tov4 listenport=8501 listenaddress=0.0.0.0 connectport=8501 connectaddress=$wslIP

# 配置防火墙
Write-Host "配置防火墙..." -ForegroundColor Green
netsh advfirewall firewall add rule name="Personal Profile 8501" dir=in action=allow protocol=TCP localport=8501

# 验证
Write-Host ""
Write-Host "验证配置:" -ForegroundColor Yellow
netsh interface portproxy show all

Write-Host ""
Write-Host "====================================" -ForegroundColor Cyan
Write-Host "  配置完成！" -ForegroundColor Green
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "下一步:" -ForegroundColor Yellow
Write-Host "  1. 将域名 506ikun.space 解析到你的公网 IP"
Write-Host "  2. 访问 http://506ikun.space:8501"
Write-Host ""
