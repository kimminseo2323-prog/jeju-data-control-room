@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo  먼저 1_설치.bat 을 실행해 주세요.
  pause
  exit /b 1
)
echo  잠시 후 브라우저에 http://127.0.0.1:8501 화면이 열립니다.
echo  끝낼 때는 이 창에서 Ctrl+C 를 누르거나 창을 닫으세요.
rem 처음 실행 때 Streamlit이 이메일을 묻고 멈추지 않도록 headless로 띄우고, 브라우저는 몇 초 뒤 직접 연다
if not defined JEJU_NO_BROWSER start "" /b cmd /c "ping -n 7 127.0.0.1 >nul & start "" http://127.0.0.1:8501"
".venv\Scripts\python.exe" -m streamlit run app\ui\app.py --server.headless true
