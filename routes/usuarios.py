from flask import Blueprint, render_template, request, redirect, url_for, flash
from database_web import get_db_connection
from decorators import login_required, admin_required
from flask import session
import psycopg2.extras
import hashlib

bp = Blueprint('usuarios', __name__, url_prefix='/usuarios')

@bp.route('/')
@admin_required
def listar():
    """Listar todos os usuários"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('SELECT id, username, nome, email, admin, ativo, perm_clientes, perm_materiais, perm_servicos, perm_ordens, perm_financeiro, perm_configuracoes, perm_assinaturas FROM usuarios ORDER BY nome')
        usuarios = cursor.fetchall()
        conn.close()
        return render_template('usuarios/listar.html', usuarios=usuarios)
    except Exception as e:
        flash(f'Erro ao carregar usuários: {e}', 'danger')
        return render_template('usuarios/listar.html', usuarios=[])

@bp.route('/novo', methods=['GET', 'POST'])
@admin_required
def novo():
    """Criar novo usuário"""
    if request.method == 'POST':
            username = request.form.get('username', '').strip()
            nome = request.form.get('nome', '').strip()
            email = request.form.get('email', '').strip()
            senha = request.form.get('senha', '').strip()
            # Garantir que os valores booleanos sejam tratados corretamente
            admin = bool(request.form.get('admin') == 'on')
            ativo = bool(request.form.get('ativo') == 'on')
            # Permissões
            perm_clientes = bool(request.form.get('perm_clientes') == 'on')
            perm_materiais = bool(request.form.get('perm_materiais') == 'on')
            perm_servicos = bool(request.form.get('perm_servicos') == 'on')
            perm_ordens = bool(request.form.get('perm_ordens') == 'on')
            perm_financeiro = bool(request.form.get('perm_financeiro') == 'on')
            perm_configuracoes = bool(request.form.get('perm_configuracoes') == 'on')
            perm_assinaturas = bool(request.form.get('perm_assinaturas') == 'on')
            
            if not username or not nome or not senha:
                flash('Username, nome e senha são obrigatórios!', 'danger')
                return render_template('usuarios/form.html')
            
            try:
                senha_hash = hashlib.md5(senha.encode()).hexdigest()
                
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO usuarios (username, nome, email, senha, admin, ativo, 
                                        perm_clientes, perm_materiais, perm_servicos, 
                                        perm_ordens, perm_financeiro, perm_configuracoes, perm_assinaturas)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (username, nome, email or None, senha_hash, admin, ativo,
                     perm_clientes, perm_materiais, perm_servicos, perm_ordens, 
                     perm_financeiro, perm_configuracoes, perm_assinaturas))
                conn.commit()
                conn.close()
                
                flash('Usuário cadastrado com sucesso!', 'success')
                return redirect(url_for('usuarios.listar'))
            except Exception as e:
                flash(f'Erro ao cadastrar usuário: {e}', 'danger')
    
    return render_template('usuarios/form.html')

@bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@admin_required
def editar(id):
    """Editar usuário"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            nome = request.form.get('nome', '').strip()
            email = request.form.get('email', '').strip()
            senha = request.form.get('senha', '').strip()
            # Garantir que os valores booleanos sejam tratados corretamente
            admin = bool(request.form.get('admin') == 'on')
            ativo = bool(request.form.get('ativo') == 'on')
            # Permissões
            perm_clientes = bool(request.form.get('perm_clientes') == 'on')
            perm_materiais = bool(request.form.get('perm_materiais') == 'on')
            perm_servicos = bool(request.form.get('perm_servicos') == 'on')
            perm_ordens = bool(request.form.get('perm_ordens') == 'on')
            perm_financeiro = bool(request.form.get('perm_financeiro') == 'on')
            perm_configuracoes = bool(request.form.get('perm_configuracoes') == 'on')
            perm_assinaturas = bool(request.form.get('perm_assinaturas') == 'on')
            
            if not username or not nome:
                flash('Username e nome são obrigatórios!', 'danger')
                return redirect(url_for('usuarios.editar', id=id))
            
            try:
                if senha:
                    senha_hash = hashlib.md5(senha.encode()).hexdigest()
                    cursor.execute('''
                        UPDATE usuarios 
                        SET username = %s, nome = %s, email = %s, senha = %s, admin = %s, ativo = %s,
                            perm_clientes = %s, perm_materiais = %s, perm_servicos = %s,
                            perm_ordens = %s, perm_financeiro = %s, perm_configuracoes = %s, perm_assinaturas = %s
                        WHERE id = %s
                    ''', (username, nome, email or None, senha_hash, admin, ativo,
                         perm_clientes, perm_materiais, perm_servicos, perm_ordens,
                         perm_financeiro, perm_configuracoes, perm_assinaturas, id))
                else:
                    cursor.execute('''
                        UPDATE usuarios 
                        SET username = %s, nome = %s, email = %s, admin = %s, ativo = %s,
                            perm_clientes = %s, perm_materiais = %s, perm_servicos = %s,
                            perm_ordens = %s, perm_financeiro = %s, perm_configuracoes = %s, perm_assinaturas = %s
                        WHERE id = %s
                    ''', (username, nome, email or None, admin, ativo,
                         perm_clientes, perm_materiais, perm_servicos, perm_ordens,
                         perm_financeiro, perm_configuracoes, perm_assinaturas, id))
                
                conn.commit()
                conn.close()
                
                flash('Usuário atualizado com sucesso!', 'success')
                return redirect(url_for('usuarios.listar'))
            except Exception as e:
                flash(f'Erro ao atualizar usuário: {e}', 'danger')
        
        cursor.execute('SELECT * FROM usuarios WHERE id = %s', (id,))
        usuario = cursor.fetchone()
        conn.close()
        
        if not usuario:
            flash('Usuário não encontrado!', 'danger')
            return redirect(url_for('usuarios.listar'))
        
        return render_template('usuarios/form.html', usuario=usuario)
    except Exception as e:
        flash(f'Erro ao editar usuário: {e}', 'danger')
        return redirect(url_for('usuarios.listar'))

@bp.route('/excluir/<int:id>', methods=['POST'])
@admin_required
def excluir(id):
    """Excluir usuário"""
    try:
        # Não permitir excluir a si mesmo
        if id == session.get('user_id'):
            flash('Você não pode excluir seu próprio usuário!', 'danger')
            return redirect(url_for('usuarios.listar'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM usuarios WHERE id = %s', (id,))
        conn.commit()
        conn.close()
        
        flash('Usuário excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir usuário: {e}', 'danger')
    
    return redirect(url_for('usuarios.listar'))
