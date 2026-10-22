@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/2] 安装构建工具（仅构建期需要，运行期零依赖）
python -m pip install --disable-pip-version-check -q pyinstaller || goto :err

echo [2/2] 打包托盘 exe
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name 电量托盘 ^
  --hidden-import rapoo_proto ^
  --hidden-import mchose_proto ^
  tray_app.py || goto :err

echo.
echo 完成：dist\电量托盘.exe
pause
exit /b 0

:err
echo.
echo 打包失败，请看上面的报错。
pause
exit /b 1
