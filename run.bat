@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo  먼저 1_설치.bat 을 실행해 주세요.
  pause
  exit /b 1
)
echo ==============================================
echo  제주 데이터 관제실 - 실행
echo ==============================================
echo  화면을 준비하고 있습니다. 전체 화면이 다 뜨기까지 PC 사양에 따라 1분~최대 5분쯤 걸립니다.
echo  - 실행할 때마다 데이터를 읽고 43개 읍면동의 이상 점수를 새로 계산하기 때문입니다.
echo  - 브라우저(http://127.0.0.1:8501)가 먼저 열려 빈 화면이나 "계산 중"이 보여도 그대로 기다려 주세요.
echo  - 브라우저가 열리지 않으면 주소창에 http://127.0.0.1:8501 을 직접 입력하세요.
echo.
echo  이 창이 프로그램입니다. 쓰는 동안 닫지 마세요.
echo  끝낼 때는 이 창에서 Ctrl+C 를 누르거나 창을 닫으세요.
echo.
rem 처음 실행 때 Streamlit이 이메일을 묻고 멈추지 않도록 headless로 띄우고, 브라우저는 몇 초 뒤 직접 연다
if not defined JEJU_NO_BROWSER start "" /b cmd /c "ping -n 7 127.0.0.1 >nul & start "" http://127.0.0.1:8501"
".venv\Scripts\python.exe" -m streamlit run app\ui\app.py --server.headless true
