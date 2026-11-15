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
  echo.
  echo  파이썬 3.12를 찾지 못했습니다.
  where python >nul 2>nul
  if not errorlevel 1 (
    for /f "delims=" %%v in ('python --version 2^>^&1') do echo  지금 이 PC에 있는 파이썬: %%v ^(이 프로그램은 3.12가 필요합니다^)
  )
  echo.
  echo  파이썬 내려받기 페이지를 엽니다. 다음 순서로 설치해 주세요.
  echo    1^) "Python 3.12.x" 항목의 "Windows installer (64-bit)"를 내려받아 실행
  echo    2^) 첫 화면 아래 "Add python.exe to PATH"에 체크한 뒤 "Install Now"
  echo    3^) 설치가 끝나면 이 창을 닫고 1_설치.bat 을 다시 더블클릭
  echo  자세한 내용: docs\설치_실행_매뉴얼.md 1단계
  if not defined JEJU_NO_BROWSER start "" "https://www.python.org/downloads/windows/"
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
  if errorlevel 1 (
    echo  판단 모델을 받지 못했습니다. 인터넷 연결을 확인하고 1_설치.bat 을 다시 실행하거나,
    echo  그대로 써도 됩니다. 이때 원인 판정과 질문 분류는 규칙 기반으로 동작합니다.
  )
)
if not exist ".env" copy ".env.example" ".env" >nul

echo.
echo  설치가 끝났습니다. 2_실행.bat 을 더블클릭하면 화면이 열립니다.
pause
