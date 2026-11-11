@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo  먼저 install.bat 을 실행해 주세요.
  pause
  exit /b 1
)
echo  잠시 후 브라우저에 http://127.0.0.1:8501 화면이 열립니다.
echo  끝낼 때는 이 창에서 Ctrl+C 를 누르거나 창을 닫으세요.
".venv\Scripts\python.exe" -m streamlit run app\ui\app.py --server.headless false
