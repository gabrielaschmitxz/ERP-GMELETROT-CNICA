from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from database_web import get_db_connection
from decorators import login_required
import os
from werkzeug.utils import secure_filename

bp = Blueprint('relatorios', __name__, url_prefix='/relatorios')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route('/configurar', methods=['GET', 'POST'])
@login_required
def configurar():
    """Configurar imagem de capa do relatório"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Criar tabela configuracoes se não existir (migração)
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS configuracoes (
                id SERIAL PRIMARY KEY,
                chave VARCHAR(255) NOT NULL UNIQUE,
                valor TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
    except Exception as e:
        print(f"Erro ao criar tabela configuracoes: {e}")
        # Tabela pode já existir, continua
    
    # Buscar configuração atual
    try:
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'imagem_capa_relatorio'")
        result = cursor.fetchone()
        caminho_imagem = result[0] if result else None
    except Exception as e:
        print(f"Erro ao buscar configuração: {e}")
        caminho_imagem = None
    
    # Se não houver configuração, usar logo.png como padrão
    dimensoes_logo = None
    if not caminho_imagem:
        logo_path = "img/logo.png"
        if os.path.exists(logo_path):
            caminho_imagem = logo_path
            # Obter dimensões da imagem para mostrar nas instruções
            try:
                from PIL import Image as PILImage
                img = PILImage.open(logo_path)
                dimensoes_logo = f"{img.width} x {img.height} pixels"
            except Exception as e:
                print(f"Erro ao obter dimensões da imagem: {e}")
                dimensoes_logo = None
        else:
            dimensoes_logo = None
    else:
        dimensoes_logo = None
    
    if request.method == 'POST':
        # Processar upload de nova imagem
        if 'imagem' in request.files:
            file = request.files['imagem']
            if file and file.filename and allowed_file(file.filename):
                # Criar pasta de relatórios se não existir
                upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'relatorios')
                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)
                
                # Salvar arquivo
                filename = secure_filename(file.filename)
                import time
                timestamp = int(time.time())
                filename = f"capa_{timestamp}_{filename}"
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)
                caminho_imagem = os.path.join('uploads', 'relatorios', filename)
                
                # Salvar no banco
                cursor.execute("""
                    INSERT INTO configuracoes (chave, valor) 
                    VALUES ('imagem_capa_relatorio', %s)
                    ON CONFLICT (chave) 
                    DO UPDATE SET valor = %s, updated_at = CURRENT_TIMESTAMP
                """, (caminho_imagem, caminho_imagem))
                conn.commit()
                flash('Imagem de capa atualizada com sucesso!', 'success')
            else:
                flash('Arquivo inválido! Use PNG, JPG, JPEG ou GIF.', 'danger')
        else:
            flash('Nenhum arquivo selecionado!', 'danger')
    
    conn.close()
    return render_template('relatorios/configurar.html', caminho_imagem=caminho_imagem, dimensoes_logo=dimensoes_logo)

