from flask import Blueprint, render_template, request, flash, redirect, url_for, session, current_app
from database_web import get_db_connection
from decorators import login_required
import os
from werkzeug.utils import secure_filename

bp = Blueprint('assinaturas', __name__, url_prefix='/assinaturas')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route('/')
@login_required
def index():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Adicionar coluna cargo se não existir (migração)
    try:
        cursor.execute('''
            DO $$ 
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name='assinaturas' AND column_name='cargo'
                ) THEN
                    ALTER TABLE assinaturas ADD COLUMN cargo VARCHAR(255) DEFAULT 'Técnico Eletricista Industrial/Residencial';
                END IF;
            END $$;
        ''')
        conn.commit()
    except Exception as e:
        print(f"Erro ao adicionar coluna cargo: {e}")
        # Continua mesmo se falhar
    
    cursor.execute("""
        SELECT id, nome, cargo, caminho_imagem, ativo, padrao 
        FROM assinaturas 
        ORDER BY padrao DESC, nome
    """)
    assinaturas = cursor.fetchall()
    conn.close()
    return render_template('assinaturas/listar.html', assinaturas=assinaturas)

@bp.route('/nova', methods=['GET', 'POST'])
@login_required
def nova():
    # Adicionar coluna cargo se não existir (migração)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            DO $$ 
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name='assinaturas' AND column_name='cargo'
                ) THEN
                    ALTER TABLE assinaturas ADD COLUMN cargo VARCHAR(255) DEFAULT 'Técnico Eletricista Industrial/Residencial';
                END IF;
            END $$;
        ''')
        conn.commit()
    except Exception as e:
        print(f"Erro ao adicionar coluna cargo: {e}")
    conn.close()
    
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        cargo = request.form.get('cargo', '').strip() or 'Técnico Eletricista Industrial/Residencial'
        ativo = request.form.get('ativo') == 'on'
        padrao = request.form.get('padrao') == 'on'
        
        if not nome:
            flash('O nome é obrigatório!', 'danger')
            return render_template('assinaturas/form.html')
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Se esta for marcada como padrão, remover padrão das outras
            if padrao:
                cursor.execute("UPDATE assinaturas SET padrao = false WHERE padrao = true")
            
            # Processar upload de imagem
            caminho_imagem = None
            if 'imagem' in request.files:
                file = request.files['imagem']
                if file and file.filename and allowed_file(file.filename):
                    # Criar pasta de assinaturas se não existir
                    upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'assinaturas')
                    if not os.path.exists(upload_folder):
                        os.makedirs(upload_folder)
                    
                    # Salvar arquivo
                    filename = secure_filename(file.filename)
                    # Adicionar timestamp para evitar conflitos
                    import time
                    timestamp = int(time.time())
                    filename = f"{timestamp}_{filename}"
                    filepath = os.path.join(upload_folder, filename)
                    file.save(filepath)
                    caminho_imagem = os.path.join('uploads', 'assinaturas', filename)
            
            cursor.execute("""
                INSERT INTO assinaturas (nome, cargo, caminho_imagem, ativo, padrao) 
                VALUES (%s, %s, %s, %s, %s)
            """, (nome, cargo, caminho_imagem, ativo, padrao))
            conn.commit()
            conn.close()
            flash('Assinatura criada com sucesso!', 'success')
            return redirect(url_for('assinaturas.index'))
        except Exception as e:
            flash(f'Erro ao criar assinatura: {e}', 'danger')
    return render_template('assinaturas/form.html')

@bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Adicionar coluna cargo se não existir (migração)
    try:
        cursor.execute('''
            DO $$ 
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name='assinaturas' AND column_name='cargo'
                ) THEN
                    ALTER TABLE assinaturas ADD COLUMN cargo VARCHAR(255) DEFAULT 'Técnico Eletricista Industrial/Residencial';
                END IF;
            END $$;
        ''')
        conn.commit()
    except Exception as e:
        print(f"Erro ao adicionar coluna cargo: {e}")
    
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        cargo = request.form.get('cargo', '').strip() or 'Técnico Eletricista Industrial/Residencial'
        ativo = request.form.get('ativo') == 'on'
        padrao = request.form.get('padrao') == 'on'
        
        if not nome:
            flash('O nome é obrigatório!', 'danger')
            cursor.execute("SELECT id, nome, cargo, caminho_imagem, ativo, padrao FROM assinaturas WHERE id = %s", (id,))
            assinatura = cursor.fetchone()
            conn.close()
            return render_template('assinaturas/form.html', assinatura=assinatura)
        
        try:
            # Se esta for marcada como padrão, remover padrão das outras
            if padrao:
                cursor.execute("UPDATE assinaturas SET padrao = false WHERE padrao = true AND id != %s", (id,))
            
            # Processar upload de nova imagem (se houver)
            caminho_imagem = None
            if 'imagem' in request.files:
                file = request.files['imagem']
                if file and file.filename and allowed_file(file.filename):
                    # Criar pasta de assinaturas se não existir
                    upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'assinaturas')
                    if not os.path.exists(upload_folder):
                        os.makedirs(upload_folder)
                    
                    # Salvar arquivo
                    filename = secure_filename(file.filename)
                    # Adicionar timestamp para evitar conflitos
                    import time
                    timestamp = int(time.time())
                    filename = f"{timestamp}_{filename}"
                    filepath = os.path.join(upload_folder, filename)
                    file.save(filepath)
                    caminho_imagem = os.path.join('uploads', 'assinaturas', filename)
            
            # Buscar caminho atual da imagem
            cursor.execute("SELECT caminho_imagem FROM assinaturas WHERE id = %s", (id,))
            current_image = cursor.fetchone()[0]
            
            # Se não foi enviada nova imagem, manter a atual
            if not caminho_imagem:
                caminho_imagem = current_image
            
            cursor.execute("""
                UPDATE assinaturas 
                SET nome = %s, cargo = %s, caminho_imagem = %s, ativo = %s, padrao = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (nome, cargo, caminho_imagem, ativo, padrao, id))
            conn.commit()
            flash('Assinatura atualizada com sucesso!', 'success')
            conn.close()
            return redirect(url_for('assinaturas.index'))
        except Exception as e:
            flash(f'Erro ao atualizar assinatura: {e}', 'danger')
    
    cursor.execute("SELECT id, nome, cargo, caminho_imagem, ativo, padrao FROM assinaturas WHERE id = %s", (id,))
    assinatura = cursor.fetchone()
    conn.close()
    if not assinatura:
        flash('Assinatura não encontrada!', 'danger')
        return redirect(url_for('assinaturas.index'))
    return render_template('assinaturas/form.html', assinatura=assinatura)

@bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Buscar caminho da imagem para deletar o arquivo
        cursor.execute("SELECT caminho_imagem FROM assinaturas WHERE id = %s", (id,))
        result = cursor.fetchone()
        if result and result[0]:
            image_path = result[0]
            # Deletar arquivo se existir
            if os.path.exists(image_path):
                try:
                    os.remove(image_path)
                except:
                    pass  # Ignora erro se não conseguir deletar
        
        cursor.execute("DELETE FROM assinaturas WHERE id = %s", (id,))
        conn.commit()
        conn.close()
        flash('Assinatura excluída com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir assinatura: {e}', 'danger')
    return redirect(url_for('assinaturas.index'))

@bp.route('/definir_padrao/<int:id>', methods=['POST'])
@login_required
def definir_padrao(id):
    """Define uma assinatura como padrão"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Remover padrão de todas
        cursor.execute("UPDATE assinaturas SET padrao = false")
        # Definir esta como padrão
        cursor.execute("UPDATE assinaturas SET padrao = true WHERE id = %s", (id,))
        conn.commit()
        conn.close()
        flash('Assinatura definida como padrão!', 'success')
    except Exception as e:
        flash(f'Erro ao definir assinatura padrão: {e}', 'danger')
    return redirect(url_for('assinaturas.index'))

@bp.route('/toggle_ativo/<int:id>', methods=['POST'])
@login_required
def toggle_ativo(id):
    """Alterna o status ativo/inativo de uma assinatura"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ativo FROM assinaturas WHERE id = %s", (id,))
        result = cursor.fetchone()
        if result:
            novo_status = not result[0]
            cursor.execute("UPDATE assinaturas SET ativo = %s WHERE id = %s", (novo_status, id))
            conn.commit()
            flash(f'Assinatura {"ativada" if novo_status else "desativada"} com sucesso!', 'success')
        conn.close()
    except Exception as e:
        flash(f'Erro ao alterar status: {e}', 'danger')
    return redirect(url_for('assinaturas.index'))