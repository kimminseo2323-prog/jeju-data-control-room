@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==============================================
echo  제주 데이터 관제실 - 설치
echo ==============================================

echo [1/4] 파이썬 3.12 찾는 중...
set "PY="
where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PY=py -3.12"
)
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info[:2]==(3,12) else 1)" >nul 2>nul
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  echo  파이썬 3.12를 찾지 못했습니다. 설치 매뉴얼 1단계를 먼저 해 주세요.
  pause
  exit /b 1
)
echo  사용: %PY%

echo [2/4] 가상환경 만드는 중...
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
if not exist ".venv\Scripts\python.exe" (
  echo  가상환경을 만들지 못했습니다.
  pause
  exit /b 1
)

echo [3/4] 패키지 설치 중... 처음에는 몇 분 걸립니다.
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
  echo  패키지 설치에 실패했습니다. 인터넷 연결을 확인하고 다시 실행해 주세요.
  pause
  exit /b 1
)

echo [4/4] 로컬 판단 모델 tev1 확인 중...
where ollama >nul 2>nul
if errorlevel 1 (
  echo  Ollama가 설치되어 있지 않아 건너뜁니다.
  echo  없어도 실행되며, 이때 원인 판정과 질문 분류는 규칙 기반으로 동작합니다.
) else (
  ollama pull tev1:4b
)
if not exist ".env" copy ".env.example" ".env" >nul

echo.
echo  설치가 끝났습니다. run.bat 을 더블클릭하면 화면이 열립니다.
pause
