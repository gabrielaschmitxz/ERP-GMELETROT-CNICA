from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from database_web import get_db_connection
from decorators import login_required
import psycopg2.extras

bp = Blueprint('configuracoes', __name__, url_prefix='/configuracoes')

@bp.route('/')
@login_required
def index():
    """Página de gerenciar"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Carregar formas de pagamento
        cursor.execute('SELECT * FROM formas_pagamento ORDER BY nome')
        formas = cursor.fetchall()
        
        # Carregar impostos
        cursor.execute("SELECT * FROM impostos_bdi WHERE tipo = 'imposto' ORDER BY descricao")
        impostos = cursor.fetchall()
        
        # Carregar BDI
        cursor.execute("SELECT * FROM impostos_bdi WHERE tipo = 'bdi' ORDER BY descricao")
        bdi_itens = cursor.fetchall()
        
        conn.close()
        
        return render_template('pagamento/imposto/bdi/index.html', formas=formas, impostos=impostos, bdi_itens=bdi_itens)
    except Exception as e:
        flash(f'Erro: {e}', 'danger')
        return render_template('pagamento/imposto/bdi/index.html', formas=[], impostos=[], bdi_itens=[])

@bp.route('/pagamento', methods=['GET', 'POST'])
@login_required
def pagamento():
    """Gerenciar formas de pagamento"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        if request.method == 'POST':
            if request.is_json:
                data = request.get_json()
                nome = data.get('nome', '').strip()
                parcelas_max = int(data.get('parcelas_max', 1))
            else:
                nome = request.form.get('nome', '').strip()
                parcelas_max = int(request.form.get('parcelas_max', 1) or 1)
            
            if not nome:
                if request.is_json:
                    conn.close()
                    return jsonify({'success': False, 'error': 'Nome é obrigatório!'}), 400
                flash('Nome é obrigatório!', 'danger')
                conn.close()
                return redirect(url_for('configuracoes.index'))
            else:
                # Verificar se já existe
                cursor.execute('SELECT id FROM formas_pagamento WHERE nome = %s', (nome,))
                existing = cursor.fetchone()
                
                if existing:
                    if request.is_json:
                        conn.close()
                        return jsonify({'success': False, 'error': 'Forma de pagamento já existe!'}), 400
                    flash('Forma de pagamento já existe!', 'danger')
                    conn.close()
                    return redirect(url_for('configuracoes.index'))
                else:
                    # Se for Parcelado, usar parcelas_max informado, senão usar 1
                    if 'parcelado' in nome.lower():
                        tipo = 'Parcelado'
                    else:
                        tipo = 'Dinheiro'
                        parcelas_max = 1
                    
                    cursor.execute('''
                        INSERT INTO formas_pagamento (nome, tipo, parcelas_max)
                        VALUES (%s, %s, %s)
                        RETURNING id
                    ''', (nome, tipo, parcelas_max))
                    new_id = cursor.fetchone()[0]
                    conn.commit()
                    if request.is_json:
                        conn.close()
                        return jsonify({'success': True, 'id': new_id, 'nome': nome})
                    flash('Forma de pagamento salva com sucesso!', 'success')
                    conn.close()
                    return redirect(url_for('configuracoes.index'))
        
        # Se chegou aqui, é GET ou POST com erro - redirecionar para index
        conn.close()
        return redirect(url_for('configuracoes.index'))
    except Exception as e:
        flash(f'Erro: {e}', 'danger')
        return render_template('configuracoes/pagamento.html', formas=[])

@bp.route('/impostos', methods=['GET', 'POST'])
@login_required
def impostos():
    """Gerenciar impostos"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        if request.method == 'POST':
            if request.is_json:
                data = request.get_json()
                nome = data.get('nome', '').strip()
                try:
                    valor = float(data.get('valor', 0))
                except:
                    valor = 0.0
            else:
                nome = request.form.get('nome', '').strip()
                valor = request.form.get('valor', '0').replace(',', '.')
                try:
                    valor = float(valor)
                except:
                    valor = 0.0
            
            if not nome:
                if request.is_json:
                    conn.close()
                    return jsonify({'success': False, 'error': 'Nome é obrigatório!'}), 400
                flash('Nome é obrigatório!', 'danger')
                conn.close()
                return redirect(url_for('configuracoes.index'))
            else:
                # Verificar se já existe
                cursor.execute("SELECT id FROM impostos_bdi WHERE tipo = 'imposto' AND descricao = %s", (nome,))
                existing = cursor.fetchone()
                
                if existing:
                    if request.is_json:
                        conn.close()
                        return jsonify({'success': False, 'error': 'Imposto já existe!'}), 400
                    flash('Imposto já existe!', 'danger')
                    conn.close()
                    return redirect(url_for('configuracoes.index'))
                else:
                    # Manter compatibilidade com banco: usar valor padrão 0.0
                    cursor.execute('''
                        INSERT INTO impostos_bdi (tipo, descricao, valor)
                        VALUES ('imposto', %s, %s)
                        RETURNING id
                    ''', (nome, valor))
                    new_id = cursor.fetchone()[0]
                    conn.commit()
                    if request.is_json:
                        conn.close()
                        return jsonify({'success': True, 'id': new_id, 'descricao': nome})
                    flash('Imposto salvo com sucesso!', 'success')
                    conn.close()
                    # Usar JavaScript para redirecionar e ativar a tab
                    from flask import make_response
                    response = make_response(redirect(url_for('configuracoes.index')))
                    response.set_cookie('active_tab', 'impostos', max_age=2)
                    return response
        
        # Se chegou aqui, é GET ou POST com erro - redirecionar para index
        conn.close()
        return redirect(url_for('configuracoes.index'))
    except Exception as e:
        flash(f'Erro: {e}', 'danger')
        return render_template('configuracoes/impostos.html', impostos=[])

@bp.route('/bdi', methods=['GET', 'POST'])
@login_required
def bdi():
    """Gerenciar BDI"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        if request.method == 'POST':
            if request.is_json:
                data = request.get_json()
                descricao = data.get('descricao', '').strip()
                try:
                    valor = float(data.get('valor', 0))
                except:
                    valor = 0.0
            else:
                descricao = request.form.get('descricao', '').strip()
                valor = request.form.get('valor', '0').replace(',', '.')
                try:
                    valor = float(valor)
                except:
                    valor = 0.0
            
            if not descricao:
                if request.is_json:
                    conn.close()
                    return jsonify({'success': False, 'error': 'Nome é obrigatório!'}), 400
                flash('Nome é obrigatório!', 'danger')
                conn.close()
                return redirect(url_for('configuracoes.index'))
            else:
                # Verificar se já existe
                cursor.execute("SELECT id FROM impostos_bdi WHERE tipo = 'bdi' AND descricao = %s", (descricao,))
                existing = cursor.fetchone()
                
                if existing:
                    if request.is_json:
                        conn.close()
                        return jsonify({'success': False, 'error': 'BDI já existe!'}), 400
                    flash('BDI já existe!', 'danger')
                    conn.close()
                    return redirect(url_for('configuracoes.index'))
                else:
                    # Manter compatibilidade com banco: usar valor padrão 0.0
                    cursor.execute('''
                        INSERT INTO impostos_bdi (tipo, descricao, valor)
                        VALUES ('bdi', %s, %s)
                        RETURNING id
                    ''', (descricao, valor))
                    new_id = cursor.fetchone()[0]
                    conn.commit()
                    if request.is_json:
                        conn.close()
                        return jsonify({'success': True, 'id': new_id, 'descricao': descricao})
                    flash('BDI salvo com sucesso!', 'success')
                    conn.close()
                    # Usar JavaScript para redirecionar e ativar a tab
                    from flask import make_response
                    response = make_response(redirect(url_for('configuracoes.index')))
                    response.set_cookie('active_tab', 'bdi', max_age=2)
                    return response
        
        # Se chegou aqui, é GET ou POST com erro - redirecionar para index
        conn.close()
        return redirect(url_for('configuracoes.index'))
    except Exception as e:
        flash(f'Erro: {e}', 'danger')
        return render_template('configuracoes/bdi.html', bdi_list=[])

@bp.route('/pagamento/editar/<int:id>', methods=['POST'])
@login_required
def editar_pagamento(id):
    """Editar forma de pagamento"""
    try:
        if request.is_json:
            data = request.get_json()
            nome = data.get('nome', '').strip()
            parcelas_max = int(data.get('parcelas_max', 1))
        else:
            nome = request.form.get('nome', '').strip()
            parcelas_max = int(request.form.get('parcelas_max', 1) or 1)
        
        if not nome:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Nome é obrigatório!'}), 400
            flash('Nome é obrigatório!', 'danger')
            return redirect(url_for('configuracoes.index'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar se já existe outro com mesmo nome
        cursor.execute('SELECT id FROM formas_pagamento WHERE nome = %s AND id != %s', (nome, id))
        existing = cursor.fetchone()
        
        if existing:
            conn.close()
            if request.is_json:
                return jsonify({'success': False, 'error': 'Forma de pagamento já existe!'}), 400
            flash('Já existe uma forma de pagamento com este nome!', 'danger')
            return redirect(url_for('configuracoes.index'))
        
        # Se for Parcelado, usar parcelas_max informado, senão usar 1
        if 'parcelado' in nome.lower():
            tipo = 'Parcelado'
        else:
            tipo = 'Dinheiro'
            parcelas_max = 1
        
        cursor.execute('UPDATE formas_pagamento SET nome = %s, tipo = %s, parcelas_max = %s WHERE id = %s', 
                      (nome, tipo, parcelas_max, id))
        conn.commit()
        conn.close()
        
        if request.is_json:
            return jsonify({'success': True})
        flash('Forma de pagamento atualizada com sucesso!', 'success')
    except Exception as e:
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 500
        flash(f'Erro ao atualizar forma de pagamento: {e}', 'danger')
    
    if request.is_json:
        return jsonify({'success': False}), 500
    return redirect(url_for('configuracoes.index'))

@bp.route('/assinaturas', methods=['POST'])
@login_required
def assinaturas():
    """Salvar nova assinatura"""
    try:
        nome = request.form.get('nome', '').strip()
        cargo = request.form.get('cargo', '').strip()
        
        if not nome or not cargo:
            flash('Nome e Cargo são obrigatórios!', 'danger')
        else:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('INSERT INTO assinaturas (nome, cargo) VALUES (%s, %s)', (nome, cargo))
            conn.commit()
            conn.close()
            flash('Assinatura salva com sucesso!', 'success')
            
    except Exception as e:
        flash(f'Erro ao salvar assinatura: {e}', 'danger')
    
    return redirect(url_for('configuracoes.index'))

@bp.route('/assinaturas/editar/<int:id>', methods=['POST'])
@login_required
def editar_assinatura(id):
    """Editar assinatura"""
    try:
        nome = request.form.get('nome', '').strip()
        cargo = request.form.get('cargo', '').strip()
        
        if not nome or not cargo:
            flash('Nome e Cargo são obrigatórios!', 'danger')
        else:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE assinaturas SET nome = %s, cargo = %s WHERE id = %s', (nome, cargo, id))
            conn.commit()
            conn.close()
            flash('Assinatura atualizada com sucesso!', 'success')
            
    except Exception as e:
        flash(f'Erro ao atualizar assinatura: {e}', 'danger')
    
    return redirect(url_for('configuracoes.index'))

@bp.route('/assinaturas/excluir/<int:id>', methods=['POST'])
@login_required
def excluir_assinatura(id):
    """Excluir assinatura"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar se há ordens de serviço usando esta assinatura
        cursor.execute('SELECT COUNT(*) FROM ordens_servico WHERE assinatura_id = %s', (id,))
        count = cursor.fetchone()[0]
        
        if count > 0:
            flash(f'Não é possível excluir esta assinatura pois ela está sendo utilizada em {count} ordem(ns) de serviço. Para excluir, primeiro remova ou altere a assinatura nas ordens de serviço.', 'warning')
            conn.close()
            return redirect(url_for('configuracoes.index'))
        
        cursor.execute('DELETE FROM assinaturas WHERE id = %s', (id,))
        conn.commit()
        conn.close()
        flash('Assinatura excluída com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir assinatura: {e}', 'danger')
    
    return redirect(url_for('configuracoes.index'))

@bp.route('/pagamento/excluir/<int:id>', methods=['POST'])
@login_required
def excluir_pagamento(id):
    """Excluir forma de pagamento"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar se está sendo usada em ordens de serviço
        cursor.execute('SELECT COUNT(*) FROM ordens_servico WHERE forma_pagamento_id = %s', (id,))
        count = cursor.fetchone()[0]
        
        if count > 0:
            conn.close()
            if request.is_json:
                return jsonify({'success': False, 'error': f'Não é possível excluir: esta forma de pagamento está sendo usada em {count} ordem(ns) de serviço!'}), 400
            flash(f'Não é possível excluir: esta forma de pagamento está sendo usada em {count} ordem(ns) de serviço!', 'danger')
            return redirect(url_for('configuracoes.index'))
        
        cursor.execute('DELETE FROM formas_pagamento WHERE id = %s', (id,))
        conn.commit()
        conn.close()
        
        if request.is_json:
            return jsonify({'success': True})
        flash('Forma de pagamento excluída com sucesso!', 'success')
    except Exception as e:
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 500
        flash(f'Erro ao excluir forma de pagamento: {e}', 'danger')
    
    if request.is_json:
        return jsonify({'success': False}), 500
    return redirect(url_for('configuracoes.index'))

@bp.route('/impostos/editar/<int:id>', methods=['POST'])
@login_required
def editar_imposto(id):
    """Editar imposto"""
    try:
        if request.is_json:
            data = request.get_json()
            nome = data.get('nome', '').strip()
            try:
                valor = float(data.get('valor', 0))
            except:
                valor = 0.0
        else:
            nome = request.form.get('nome', '').strip()
            valor = request.form.get('valor', '0').replace(',', '.')
            try:
                valor = float(valor)
            except:
                valor = 0.0
        
        if not nome:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Nome é obrigatório!'}), 400
            flash('Nome é obrigatório!', 'danger')
            return redirect(url_for('configuracoes.index'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar se já existe outro com mesmo nome
        cursor.execute("SELECT id FROM impostos_bdi WHERE tipo = 'imposto' AND descricao = %s AND id != %s", (nome, id))
        existing = cursor.fetchone()
        
        if existing:
            conn.close()
            if request.is_json:
                return jsonify({'success': False, 'error': 'Já existe um imposto com este nome!'}), 400
            flash('Já existe um imposto com este nome!', 'danger')
            return redirect(url_for('configuracoes.index'))
        
        cursor.execute("UPDATE impostos_bdi SET descricao = %s, valor = %s WHERE id = %s", (nome, valor, id))
        conn.commit()
        conn.close()
        
        if request.is_json:
            return jsonify({'success': True})
        flash('Imposto atualizado com sucesso!', 'success')
    except Exception as e:
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 500
        flash(f'Erro ao atualizar imposto: {e}', 'danger')
    
    if request.is_json:
        return jsonify({'success': False}), 500
    return redirect(url_for('configuracoes.index'))

@bp.route('/impostos/excluir/<int:id>', methods=['POST'])
@login_required
def excluir_imposto(id):
    """Excluir imposto"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM impostos_bdi WHERE id = %s', (id,))
        conn.commit()
        conn.close()
        
        if request.is_json:
            return jsonify({'success': True})
        flash('Imposto excluído com sucesso!', 'success')
    except Exception as e:
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 500
        flash(f'Erro ao excluir imposto: {e}', 'danger')
    
    if request.is_json:
        return jsonify({'success': False}), 500
    return redirect(url_for('configuracoes.index'))

@bp.route('/bdi/editar/<int:id>', methods=['POST'])
@login_required
def editar_bdi(id):
    """Editar BDI"""
    try:
        if request.is_json:
            data = request.get_json()
            descricao = data.get('descricao', '').strip()
            try:
                valor = float(data.get('valor', 0))
            except:
                valor = 0.0
        else:
            descricao = request.form.get('descricao', '').strip()
            valor = request.form.get('valor', '0').replace(',', '.')
            try:
                valor = float(valor)
            except:
                valor = 0.0
        
        if not descricao:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Nome é obrigatório!'}), 400
            flash('Nome é obrigatório!', 'danger')
            return redirect(url_for('configuracoes.index'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar se já existe outro com mesmo nome
        cursor.execute("SELECT id FROM impostos_bdi WHERE tipo = 'bdi' AND descricao = %s AND id != %s", (descricao, id))
        existing = cursor.fetchone()
        
        if existing:
            conn.close()
            if request.is_json:
                return jsonify({'success': False, 'error': 'Já existe um BDI com este nome!'}), 400
            flash('Já existe um BDI com este nome!', 'danger')
            return redirect(url_for('configuracoes.index'))
        
        cursor.execute("UPDATE impostos_bdi SET descricao = %s, valor = %s WHERE id = %s", (descricao, valor, id))
        conn.commit()
        conn.close()
        
        if request.is_json:
            return jsonify({'success': True})
        flash('BDI atualizado com sucesso!', 'success')
    except Exception as e:
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 500
        flash(f'Erro ao atualizar BDI: {e}', 'danger')
    
    if request.is_json:
        return jsonify({'success': False}), 500
    return redirect(url_for('configuracoes.index'))

@bp.route('/bdi/excluir/<int:id>', methods=['POST'])
@login_required
def excluir_bdi(id):
    """Excluir BDI"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM impostos_bdi WHERE id = %s', (id,))
        conn.commit()
        conn.close()
        
        if request.is_json:
            return jsonify({'success': True})
        flash('BDI excluído com sucesso!', 'success')
    except Exception as e:
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 500
        flash(f'Erro ao excluir BDI: {e}', 'danger')
    
    if request.is_json:
        return jsonify({'success': False}), 500
    return redirect(url_for('configuracoes.index'))
