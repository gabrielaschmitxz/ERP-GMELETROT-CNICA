@echo off
echo ========================================
echo Instalando dependencias do ERP Web
echo ========================================
echo.

cd /d "%~dp0"

echo Verificando se o arquivo requirements_web.txt existe...
if not exist "requirements_web.txt" (
    echo ERRO: Arquivo requirements_web.txt nao encontrado!
    echo Certifique-se de estar no diretorio correto do projeto.
    pause
    exit /b 1
)

echo.
echo Instalando dependencias...
pip install -r requirements_web.txt

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo Instalacao concluida com sucesso!
    echo ========================================
    echo.
    echo Para executar o sistema, use:
    echo   python app_web.py
    echo.
) else (
    echo.
    echo ========================================
    echo Erro na instalacao!
    echo ========================================
    echo.
    echo Tente instalar manualmente:
    echo   pip install Flask psycopg2-binary python-dotenv reportlab requests
    echo.
)

pause

