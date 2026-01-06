from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from database_web import get_db_connection
from decorators import login_required
import psycopg2.extras

bp = Blueprint('materiais', __name__, url_prefix='/materiais')

@bp.route('/')
@login_required
def listar():
    """Listar todos os materiais"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('SELECT * FROM materiais ORDER BY nome')
        materiais = cursor.fetchall()
        conn.close()
        return render_template('materiais/listar.html', materiais=materiais)
    except Exception as e:
        flash(f'Erro ao carregar materiais: {e}', 'danger')
        return render_template('materiais/listar.html', materiais=[])

@bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    """Criar novo material"""
    if request.method == 'POST':
        if request.is_json:
            data = request.get_json()
            nome = data.get('nome', '').strip()
            marca = data.get('marca', '').strip()
            quantidade = str(data.get('quantidade', '0'))
            preco_unit = str(data.get('preco_unit', '0'))
        else:
            nome = request.form.get('nome', '').strip()
            marca = request.form.get('marca', '').strip()
            quantidade = request.form.get('quantidade', '0').strip()
            preco_unit = request.form.get('preco_unit', '0').strip()
        
        if not nome:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Nome é obrigatório!'}), 400
            flash('Nome é obrigatório!', 'danger')
            return render_template('materiais/form.html')
        
        try:
            quantidade = int(quantidade) if quantidade else 0
            preco_unit = float(preco_unit.replace(',', '.')) if preco_unit else 0.0
            
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO materiais (nome, marca, quantidade, preco_unit)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            ''', (nome, marca or None, quantidade, preco_unit))
            new_id = cursor.fetchone()[0]
            conn.commit()
            conn.close()
            
            if request.is_json:
                return jsonify({
                    'success': True, 
                    'id': new_id, 
                    'nome': f"{nome} - {marca}" if marca else nome,
                    'preco_unit': preco_unit
                })
            
            flash('Material cadastrado com sucesso!', 'success')
            return redirect(url_for('materiais.listar'))
        except ValueError:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Valores inválidos!'}), 400
            flash('Quantidade deve ser um número inteiro e preço um número decimal!', 'danger')
        except Exception as e:
            if request.is_json:
                return jsonify({'success': False, 'error': str(e)}), 500
            flash(f'Erro ao cadastrar material: {e}', 'danger')
    
    return render_template('materiais/form.html')

@bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Editar material"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        if request.method == 'POST':
            nome = request.form.get('nome', '').strip()
            marca = request.form.get('marca', '').strip()
            quantidade = request.form.get('quantidade', '0').strip()
            preco_unit = request.form.get('preco_unit', '0').strip()
            
            if not nome:
                flash('Nome é obrigatório!', 'danger')
                return redirect(url_for('materiais.editar', id=id))
            
            try:
                quantidade = int(quantidade) if quantidade else 0
                preco_unit = float(preco_unit.replace(',', '.')) if preco_unit else 0.0
                
                cursor.execute('''
                    UPDATE materiais 
                    SET nome = %s, marca = %s, quantidade = %s, preco_unit = %s
                    WHERE id = %s
                ''', (nome, marca or None, quantidade, preco_unit, id))
                conn.commit()
                conn.close()
                
                flash('Material atualizado com sucesso!', 'success')
                return redirect(url_for('materiais.listar'))
            except ValueError:
                flash('Quantidade deve ser um número inteiro e preço um número decimal!', 'danger')
        
        cursor.execute('SELECT * FROM materiais WHERE id = %s', (id,))
        material = cursor.fetchone()
        conn.close()
        
        if not material:
            flash('Material não encontrado!', 'danger')
            return redirect(url_for('materiais.listar'))
        
        return render_template('materiais/form.html', material=material)
    except Exception as e:
        flash(f'Erro ao editar material: {e}', 'danger')
        return redirect(url_for('materiais.listar'))

@bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    """Excluir material"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM materiais WHERE id = %s', (id,))
        conn.commit()
        conn.close()
        flash('Material excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir material: {e}', 'danger')
    return redirect(url_for('materiais.listar'))

@bp.route('/api/buscar')
@login_required
def api_buscar():
    """API para buscar materiais"""
    try:
        search = request.args.get('q', '')
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        if search:
            cursor.execute('''
                SELECT id, nome, marca, preco_unit FROM materiais 
                WHERE nome ILIKE %s OR marca ILIKE %s
                ORDER BY 
                    CASE 
                        WHEN nome ILIKE %s THEN 1
                        WHEN nome ILIKE %s THEN 2
                        ELSE 3
                    END,
                    nome
            ''', (f'%{search}%', f'%{search}%', f'{search}%', f'%{search}%'))
        else:
            cursor.execute('SELECT id, nome, marca, preco_unit FROM materiais ORDER BY nome')
        
        materiais = cursor.fetchall()
        conn.close()
        
        results = []
        for m in materiais:
            marca_text = f" - {m['marca']}" if m['marca'] else ""
            results.append({
                'id': m['id'],
                'nome': f"{m['nome']}{marca_text}",
                'preco_unit': float(m['preco_unit'])
            })
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
