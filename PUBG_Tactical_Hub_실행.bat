@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================================
echo   PUBG Tactical Hub - 로컬 서버 & 외부 접속 터널 실행
echo ========================================================
echo.
echo [1/2] Streamlit 웹 대시보드 서버 시작 중 (http://localhost:8501)...
start "PUBG Tactical Hub - Streamlit" /min cmd /c "python -m streamlit run app.py --server.port 8501 --server.headless true"

timeout /t 3 /nobreak >nul

echo [2/2] Cloudflare 외부 접속 주소 생성 중...
echo 잠시 후 아래 박스에 https://...trycloudflare.com 주소가 표시됩니다.
echo (이 창을 켜두는 동안 외부에서도 계속 접속할 수 있습니다.)
echo.
"%~dp0tools\cloudflared.exe" tunnel --url http://localhost:8501

pause
