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
        
        # Adicionar coluna ativo se não existir (migração)
        try:
            cursor.execute('''
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='materiais' AND column_name='ativo'
                    ) THEN
                        ALTER TABLE materiais ADD COLUMN ativo BOOLEAN DEFAULT true;
                    END IF;
                END $$;
            ''')
            conn.commit()
        except Exception as e:
            print(f"Erro ao adicionar coluna ativo: {e}")
        
        # Buscar materiais cadastrados
        cursor.execute('SELECT * FROM materiais ORDER BY nome')
        materiais_cadastrados = cursor.fetchall()
        
        # Buscar materiais únicos das ordens que não estão na tabela materiais
        # Extrair nome e marca da descrição
        cursor.execute('''
            SELECT DISTINCT 
                descricao,
                CASE 
                    WHEN descricao LIKE '%% - %%' THEN SUBSTRING(descricao FROM 1 FOR POSITION(' - ' IN descricao) - 1)
                    ELSE descricao
                END as nome,
                CASE 
                    WHEN descricao LIKE '%% - %%' THEN SUBSTRING(descricao FROM POSITION(' - ' IN descricao) + 3)
                    ELSE NULL
                END as marca,
                AVG(valor_unit) as preco_unit,
                MIN(data) as data
            FROM itens_material
            WHERE (material_id IS NULL OR material_id NOT IN (SELECT id FROM materiais WHERE id IS NOT NULL))
            GROUP BY descricao
            ORDER BY nome
        ''')
        materiais_ordens = cursor.fetchall()
        
        # Sincronizar materiais das ordens para a tabela materiais (apenas os que não estão cadastrados)
        materiais_cadastrados_nomes = {f"{m['nome'].strip().lower()}_{(m.get('marca') or '').strip().lower()}" for m in materiais_cadastrados}
        
        for m in materiais_ordens:
            nome = m['nome'].strip() if m['nome'] else ''
            marca = m.get('marca', '').strip() if m.get('marca') else None
            chave = f"{nome.lower()}_{(marca or '').lower()}"
            
            if nome and chave not in materiais_cadastrados_nomes:
                # Criar material na tabela materiais
                try:
                    cursor.execute('''
                        INSERT INTO materiais (nome, marca, quantidade, preco_unit, data)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id
                    ''', (nome, marca, 0, float(m['preco_unit']) if m['preco_unit'] else 0.0, m.get('data')))
                    new_id = cursor.fetchone()[0]
                    
                    # Atualizar material_id nos itens_material que usam este material
                    # Atualizar todos os itens com a mesma descrição que não têm material_id válido
                    cursor.execute('''
                        UPDATE itens_material 
                        SET material_id = %s 
                        WHERE descricao = %s 
                        AND (material_id IS NULL OR material_id NOT IN (SELECT id FROM materiais WHERE id IS NOT NULL))
                    ''', (new_id, m['descricao']))
                    
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    print(f"Erro ao sincronizar material {nome}: {e}")
        
        # Buscar todos os materiais atualizados
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
            preco_unit = str(data.get('preco_unit', '0'))
            data_material = data.get('data', '').strip()
        else:
            nome = request.form.get('nome', '').strip()
            marca = request.form.get('marca', '').strip()
            preco_unit = request.form.get('preco_unit', '0').strip()
            data_material = request.form.get('data', '').strip()
        
        if not nome:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Nome é obrigatório!'}), 400
            flash('Nome é obrigatório!', 'danger')
            return render_template('materiais/form.html')
        
        try:
            preco_unit = float(preco_unit.replace(',', '.')) if preco_unit else 0.0
            
            # Converter data se fornecida
            data_material_parsed = None
            if data_material:
                try:
                    from datetime import datetime
                    data_material_parsed = datetime.strptime(data_material, '%Y-%m-%d').date()
                except:
                    pass
            
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO materiais (nome, marca, quantidade, preco_unit, data)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            ''', (nome, marca or None, 0, preco_unit, data_material_parsed))
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
            flash('Preço deve ser um número decimal!', 'danger')
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
            preco_unit = request.form.get('preco_unit', '0').strip()
            data_material = request.form.get('data', '').strip()
            
            if not nome:
                flash('Nome é obrigatório!', 'danger')
                return redirect(url_for('materiais.editar', id=id))
            
            try:
                preco_unit = float(preco_unit.replace(',', '.')) if preco_unit else 0.0
                
                # Converter data se fornecida
                data_material_parsed = None
                if data_material:
                    try:
                        from datetime import datetime
                        data_material_parsed = datetime.strptime(data_material, '%Y-%m-%d').date()
                    except:
                        pass
                
                cursor.execute('''
                    UPDATE materiais 
                    SET nome = %s, marca = %s, preco_unit = %s, data = %s
                    WHERE id = %s
                ''', (nome, marca or None, preco_unit, data_material_parsed, id))
                conn.commit()
                conn.close()
                
                flash('Material atualizado com sucesso!', 'success')
                return redirect(url_for('materiais.listar'))
            except ValueError:
                flash('Preço deve ser um número decimal!', 'danger')
        
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
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Buscar nome do material para a mensagem
        cursor.execute('SELECT nome, marca FROM materiais WHERE id = %s', (id,))
        material = cursor.fetchone()
        nome_material = f"{material['nome']} - {material.get('marca', '')}" if material.get('marca') else material['nome']
        
        # Verificar se o material está sendo usado em alguma ordem (por material_id)
        cursor.execute('''
            SELECT DISTINCT os.id, os.data, c.nome as cliente_nome
            FROM itens_material im
            JOIN ordens_servico os ON im.ordem_id = os.id
            LEFT JOIN clientes c ON os.cliente_id = c.id
            WHERE im.material_id = %s
            ORDER BY os.id
        ''', (id,))
        ordens = cursor.fetchall()
        
        # Verificar também por descrição (caso tenha sido criado diretamente na ordem)
        # Construir padrão de busca para a descrição
        descricao_pattern = f"%{material['nome']}%"
        if material.get('marca'):
            descricao_pattern = f"%{material['nome']}%{material['marca']}%"
        
        cursor.execute('''
            SELECT DISTINCT os.id, os.data, c.nome as cliente_nome
            FROM itens_material im
            JOIN ordens_servico os ON im.ordem_id = os.id
            LEFT JOIN clientes c ON os.cliente_id = c.id
            WHERE (im.material_id IS NULL OR im.material_id != %s)
            AND im.descricao ILIKE %s
            AND os.id NOT IN (SELECT ordem_id FROM itens_material WHERE material_id = %s)
            ORDER BY os.id
        ''', (id, descricao_pattern, id))
        ordens_descricao = cursor.fetchall()
        
        # Combinar as duas listas
        todas_ordens = ordens + ordens_descricao
        # Remover duplicatas
        ordens_unicas = {}
        for ordem in todas_ordens:
            ordens_unicas[ordem['id']] = ordem
        
        if ordens_unicas:
            # Não permitir exclusão, apenas inativação
            flash(f'Não é possível excluir o material "{nome_material}" pois ele está sendo usado em ordens de serviço. Use o botão de inativar para ocultá-lo de novas ordens.', 'warning')
            conn.close()
            return redirect(url_for('materiais.listar'))
        
        # Se não estiver sendo usado, pode excluir
        cursor.execute('DELETE FROM materiais WHERE id = %s', (id,))
        conn.commit()
        conn.close()
        flash('Material excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir material: {e}', 'danger')
    return redirect(url_for('materiais.listar'))

@bp.route('/toggle_ativo/<int:id>', methods=['POST'])
@login_required
def toggle_ativo(id):
    """Alterna o status ativo/inativo de um material"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Adicionar coluna ativo se não existir (migração)
        try:
            cursor.execute('''
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='materiais' AND column_name='ativo'
                    ) THEN
                        ALTER TABLE materiais ADD COLUMN ativo BOOLEAN DEFAULT true;
                    END IF;
                END $$;
            ''')
            conn.commit()
        except Exception as e:
            print(f"Erro ao adicionar coluna ativo: {e}")
        
        cursor.execute("SELECT ativo FROM materiais WHERE id = %s", (id,))
        result = cursor.fetchone()
        if result:
            novo_status = not result[0]
            cursor.execute("UPDATE materiais SET ativo = %s WHERE id = %s", (novo_status, id))
            conn.commit()
            flash(f'Material {"ativado" if novo_status else "desativado"} com sucesso!', 'success')
        conn.close()
    except Exception as e:
        flash(f'Erro ao alterar status: {e}', 'danger')
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
                WHERE ativo = true AND (nome ILIKE %s OR marca ILIKE %s)
                ORDER BY 
                    CASE 
                        WHEN nome ILIKE %s THEN 1
                        WHEN nome ILIKE %s THEN 2
                        ELSE 3
                    END,
                    nome
            ''', (f'%{search}%', f'%{search}%', f'{search}%', f'%{search}%'))
        else:
            cursor.execute('SELECT id, nome, marca, preco_unit FROM materiais WHERE ativo = true ORDER BY nome')
        
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
