@echo off
echo ========================================
echo Iniciando ERP Eletrotecnica WEB
echo ========================================
echo.

cd /d "%~dp0"

echo Verificando se o Python esta instalado...
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERRO: Python nao encontrado!
    echo Por favor, instale o Python primeiro.
    pause
    exit /b 1
)

echo.
echo Verificando dependencias...
python -c "import flask" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Dependencias nao encontradas. Instalando...
    pip install -r requirements_web.txt
    if %ERRORLEVEL% NEQ 0 (
        echo ERRO: Falha ao instalar dependencias!
        pause
        exit /b 1
    )
)

echo.
echo ========================================
echo Iniciando servidor web...
echo ========================================
echo.
echo O sistema estara disponivel em:
echo   http://localhost:5000
echo   http://127.0.0.1:5000
echo.
echo Usuario padrao: admin
echo Senha padrao: admin123
echo.
echo Pressione Ctrl+C para parar o servidor
echo ========================================
echo.

python app_web.py

pause

