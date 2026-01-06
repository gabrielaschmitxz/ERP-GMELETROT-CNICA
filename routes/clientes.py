from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from database_web import get_db_connection
from decorators import login_required
import psycopg2.extras
import re

bp = Blueprint('clientes', __name__, url_prefix='/clientes')

def formatar_cpf_cnpj(value):
    """Formata CPF ou CNPJ"""
    if not value:
        return ''
    # Remove caracteres não numéricos
    digits = re.sub(r'\D', '', str(value))
    
    if len(digits) == 11:  # CPF
        return f"{digits[0:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:11]}"
    elif len(digits) == 14:  # CNPJ
        return f"{digits[0:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:14]}"
    else:
        return value  # Retorna sem formatação se não for CPF nem CNPJ

def formatar_telefone(value):
    """Formata telefone"""
    if not value:
        return ''
    # Remove caracteres não numéricos
    digits = re.sub(r'\D', '', str(value))
    
    if len(digits) == 10:  # Telefone fixo
        return f"({digits[0:2]}) {digits[2:6]}-{digits[6:10]}"
    elif len(digits) == 11:  # Celular
        return f"({digits[0:2]}) {digits[2:7]}-{digits[7:11]}"
    else:
        return value  # Retorna sem formatação se não tiver 10 ou 11 dígitos

@bp.route('/')
@login_required
def listar():
    """Listar todos os clientes"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        search = request.args.get('search', '')
        query = "SELECT * FROM clientes"
        params = []
        
        if search:
            query += " WHERE nome ILIKE %s OR cnpj_cpf ILIKE %s"
            params.extend([f'%{search}%', f'%{search}%'])
        
        query += " ORDER BY nome"
        cursor.execute(query, params)
        clientes = cursor.fetchall()
        conn.close()
        
        # Adicionar funções de formatação ao contexto do template
        return render_template('clientes/listar.html', 
                             clientes=clientes, 
                             search=search,
                             formatar_cpf_cnpj=formatar_cpf_cnpj,
                             formatar_telefone=formatar_telefone)
    except Exception as e:
        flash(f'Erro ao carregar clientes: {e}', 'danger')
        return render_template('clientes/listar.html', clientes=[], search='')

@bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    """Criar novo cliente"""
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        # Remover formatação do CNPJ/CPF e telefone
        cnpj_cpf = re.sub(r'\D', '', request.form.get('cnpj_cpf', '').strip())
        endereco = request.form.get('endereco', '').strip()
        telefone = re.sub(r'\D', '', request.form.get('telefone', '').strip())
        email = request.form.get('email', '').strip()
        
        if not nome:
            flash('Nome é obrigatório!', 'danger')
            return render_template('clientes/form.html')
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Verificar CNPJ/CPF único
            if cnpj_cpf:
                cursor.execute('SELECT id FROM clientes WHERE cnpj_cpf = %s', (cnpj_cpf,))
                if cursor.fetchone():
                    flash('CNPJ/CPF já cadastrado!', 'danger')
                    conn.close()
                    return render_template('clientes/form.html', 
                                         nome=nome, cnpj_cpf=cnpj_cpf, endereco=endereco,
                                         telefone=telefone, email=email)
            
            cursor.execute('''
                INSERT INTO clientes (nome, cnpj_cpf, endereco, telefone, email)
                VALUES (%s, %s, %s, %s, %s)
            ''', (nome, cnpj_cpf or None, endereco or None, telefone or None, email or None))
            
            conn.commit()
            conn.close()
            
            flash('Cliente cadastrado com sucesso!', 'success')
            return redirect(url_for('clientes.listar'))
            
        except Exception as e:
            flash(f'Erro ao cadastrar cliente: {e}', 'danger')
    
    return render_template('clientes/form.html')

@bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Editar cliente"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        if request.method == 'POST':
            nome = request.form.get('nome', '').strip()
            # Remover formatação do CNPJ/CPF e telefone
            cnpj_cpf = re.sub(r'\D', '', request.form.get('cnpj_cpf', '').strip())
            endereco = request.form.get('endereco', '').strip()
            telefone = re.sub(r'\D', '', request.form.get('telefone', '').strip())
            email = request.form.get('email', '').strip()
            
            if not nome:
                flash('Nome é obrigatório!', 'danger')
                return redirect(url_for('clientes.editar', id=id))
            
            # Verificar CNPJ/CPF único (exceto para o próprio cliente)
            if cnpj_cpf:
                cursor.execute('SELECT id FROM clientes WHERE cnpj_cpf = %s AND id != %s', (cnpj_cpf, id))
                if cursor.fetchone():
                    flash('CNPJ/CPF já cadastrado para outro cliente!', 'danger')
                    conn.close()
                    return redirect(url_for('clientes.editar', id=id))
            
            cursor.execute('''
                UPDATE clientes 
                SET nome = %s, cnpj_cpf = %s, endereco = %s, telefone = %s, email = %s
                WHERE id = %s
            ''', (nome, cnpj_cpf or None, endereco or None, telefone or None, email or None, id))
            
            conn.commit()
            conn.close()
            
            flash('Cliente atualizado com sucesso!', 'success')
            return redirect(url_for('clientes.listar'))
        
        # GET - carregar dados do cliente
        cursor.execute('SELECT * FROM clientes WHERE id = %s', (id,))
        cliente = cursor.fetchone()
        conn.close()
        
        if not cliente:
            flash('Cliente não encontrado!', 'danger')
            return redirect(url_for('clientes.listar'))
        
        return render_template('clientes/form.html', cliente=cliente)
        
    except Exception as e:
        flash(f'Erro ao editar cliente: {e}', 'danger')
        return redirect(url_for('clientes.listar'))

@bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    """Excluir cliente"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar se tem ordens de serviço
        cursor.execute('SELECT COUNT(*) FROM ordens_servico WHERE cliente_id = %s', (id,))
        count = cursor.fetchone()[0]
        
        if count > 0:
            flash(f'Não é possível excluir o cliente pois ele possui {count} ordem(ns) de serviço associada(s).', 'danger')
            conn.close()
            return redirect(url_for('clientes.listar'))
        
        cursor.execute('DELETE FROM clientes WHERE id = %s', (id,))
        conn.commit()
        conn.close()
        
        flash('Cliente excluído com sucesso!', 'success')
        
    except Exception as e:
        flash(f'Erro ao excluir cliente: {e}', 'danger')
    
    return redirect(url_for('clientes.listar'))

@bp.route('/api/buscar')
@login_required
def api_buscar():
    """API para buscar clientes (usado em autocomplete)"""
    try:
        search = request.args.get('q', '')
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        if search:
            search_pattern_start = f'{search}%'
            search_pattern_any = f'%{search}%'
            cursor.execute('''
                SELECT id, nome FROM clientes 
                WHERE nome ILIKE %s OR cnpj_cpf ILIKE %s
                ORDER BY 
                    CASE 
                        WHEN nome ILIKE %s THEN 1
                        WHEN nome ILIKE %s THEN 2
                        ELSE 3
                    END,
                    nome
            ''', (search_pattern_any, search_pattern_any, search_pattern_start, search_pattern_any))
        else:
            cursor.execute('SELECT id, nome FROM clientes ORDER BY nome')
        
        clientes = cursor.fetchall()
        conn.close()
        
        results = [{'id': c['id'], 'nome': c['nome']} for c in clientes]
        return jsonify(results)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
