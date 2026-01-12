from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from database_web import get_db_connection
from decorators import login_required
from datetime import datetime
import psycopg2.extras

bp = Blueprint('servicos', __name__, url_prefix='/servicos')

@bp.route('/')
@login_required
def listar():
    """Listar todos os serviços"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Migração automática: adicionar colunas 'local' e 'data' se não existirem
        cursor.execute('''
            DO $$ 
            BEGIN 
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name='servicos' AND column_name='local'
                ) THEN
                    ALTER TABLE servicos ADD COLUMN local VARCHAR(255);
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name='servicos' AND column_name='data'
                ) THEN
                    ALTER TABLE servicos ADD COLUMN data DATE;
                END IF;
            END $$;
        ''')
        conn.commit()
        
        cursor.execute('SELECT * FROM servicos ORDER BY nome')
        servicos = cursor.fetchall()
        conn.close()
        return render_template('servicos/listar.html', servicos=servicos)
    except Exception as e:
        flash(f'Erro ao carregar serviços: {e}', 'danger')
        return render_template('servicos/listar.html', servicos=[])

@bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    """Criar novo serviço"""
    if request.method == 'POST':
        if request.is_json:
            data = request.get_json()
            nome = data.get('nome', '').strip()
            preco_unit = str(data.get('preco_unit', '0'))
            tempo_h = str(data.get('tempo_h', '0'))
        else:
            nome = request.form.get('nome', '').strip()
            preco_unit = request.form.get('preco_unit', '0').strip()
            tempo_h = request.form.get('tempo_h', '0').strip()
        
        if not nome:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Nome é obrigatório!'}), 400
            flash('Nome é obrigatório!', 'danger')
            return render_template('servicos/form.html')
        
        try:
            preco_unit = float(preco_unit.replace(',', '.')) if preco_unit else 0.0
            tempo_h = float(tempo_h.replace(',', '.')) if tempo_h else 0.0
            
            # Obter local e data do formulário
            if request.is_json:
                local = data.get('local', '').strip() or None
                data_servico = data.get('data') or None
            else:
                local = request.form.get('local', '').strip() or None
                data_servico_str = request.form.get('data', '').strip()
                data_servico = None
                if data_servico_str:
                    try:
                        data_servico = datetime.strptime(data_servico_str, "%Y-%m-%d").date()
                    except:
                        data_servico = None
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Migração automática: adicionar colunas 'local' e 'data' se não existirem
            cursor.execute('''
                DO $$ 
                BEGIN 
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='servicos' AND column_name='local'
                    ) THEN
                        ALTER TABLE servicos ADD COLUMN local VARCHAR(255);
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='servicos' AND column_name='data'
                    ) THEN
                        ALTER TABLE servicos ADD COLUMN data DATE;
                    END IF;
                END $$;
            ''')
            conn.commit()
            
            cursor.execute('''
                INSERT INTO servicos (nome, preco_unit, tempo_h, local, data)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            ''', (nome, preco_unit, tempo_h, local, data_servico))
            new_id = cursor.fetchone()[0]
            conn.commit()
            conn.close()
            
            if request.is_json:
                return jsonify({
                    'success': True, 
                    'id': new_id, 
                    'nome': nome, 
                    'preco_unit': preco_unit,
                    'tempo_h': tempo_h,
                    'local': local,
                    'data': data_servico.strftime('%Y-%m-%d') if data_servico else None
                })
            
            flash('Serviço cadastrado com sucesso!', 'success')
            return redirect(url_for('servicos.listar'))
        except ValueError:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Valores inválidos!'}), 400
            flash('Preço e tempo devem ser números decimais!', 'danger')
        except Exception as e:
            if request.is_json:
                return jsonify({'success': False, 'error': str(e)}), 500
            flash(f'Erro ao cadastrar serviço: {e}', 'danger')
    
    return render_template('servicos/form.html')

@bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Editar serviço"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        if request.method == 'POST':
            nome = request.form.get('nome', '').strip()
            preco_unit = request.form.get('preco_unit', '0').strip()
            tempo_h = request.form.get('tempo_h', '0').strip()
            local = request.form.get('local', '').strip() or None
            data_servico_str = request.form.get('data', '').strip()
            data_servico = None
            if data_servico_str:
                try:
                    data_servico = datetime.strptime(data_servico_str, "%Y-%m-%d").date()
                except:
                    data_servico = None
            
            if not nome:
                flash('Nome é obrigatório!', 'danger')
                return redirect(url_for('servicos.editar', id=id))
            
            try:
                preco_unit = float(preco_unit.replace(',', '.')) if preco_unit else 0.0
                tempo_h = float(tempo_h.replace(',', '.')) if tempo_h else 0.0
                
                # Migração automática: adicionar colunas 'local' e 'data' se não existirem
                cursor.execute('''
                    DO $$ 
                    BEGIN 
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name='servicos' AND column_name='local'
                        ) THEN
                            ALTER TABLE servicos ADD COLUMN local VARCHAR(255);
                        END IF;
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name='servicos' AND column_name='data'
                        ) THEN
                            ALTER TABLE servicos ADD COLUMN data DATE;
                        END IF;
                    END $$;
                ''')
                conn.commit()
                
                cursor.execute('''
                    UPDATE servicos 
                    SET nome = %s, preco_unit = %s, tempo_h = %s, local = %s, data = %s
                    WHERE id = %s
                ''', (nome, preco_unit, tempo_h, local, data_servico, id))
                conn.commit()
                conn.close()
                
                flash('Serviço atualizado com sucesso!', 'success')
                return redirect(url_for('servicos.listar'))
            except ValueError:
                flash('Preço e tempo devem ser números decimais!', 'danger')
        
        cursor.execute('SELECT * FROM servicos WHERE id = %s', (id,))
        servico = cursor.fetchone()
        conn.close()
        
        if not servico:
            flash('Serviço não encontrado!', 'danger')
            return redirect(url_for('servicos.listar'))
        
        return render_template('servicos/form.html', servico=servico)
    except Exception as e:
        flash(f'Erro ao editar serviço: {e}', 'danger')
        return redirect(url_for('servicos.listar'))

@bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    """Excluir serviço"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM servicos WHERE id = %s', (id,))
        conn.commit()
        conn.close()
        flash('Serviço excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir serviço: {e}', 'danger')
    return redirect(url_for('servicos.listar'))

@bp.route('/api/buscar')
@login_required
def api_buscar():
    """API para buscar serviços"""
    try:
        search = request.args.get('q', '').strip()
        import time
        start_time = time.time()
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Migração automática: adicionar colunas 'local' e 'data' se não existirem
        cursor.execute('''
            DO $$ 
            BEGIN 
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name='servicos' AND column_name='local'
                ) THEN
                    ALTER TABLE servicos ADD COLUMN local VARCHAR(255);
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name='servicos' AND column_name='data'
                ) THEN
                    ALTER TABLE servicos ADD COLUMN data DATE;
                END IF;
            END $$;
        ''')
        conn.commit()
        
        if search:
            # Busca com priorização: primeiro os que começam com o termo, depois os que contêm
            search_pattern_start = f'{search}%'
            search_pattern_any = f'%{search}%'
            cursor.execute('''
                SELECT id, nome, preco_unit, tempo_h, local, data FROM servicos 
                WHERE nome ILIKE %s
                ORDER BY 
                    CASE 
                        WHEN nome ILIKE %s THEN 1
                        ELSE 2
                    END,
                    nome
            ''', (search_pattern_any, search_pattern_start))
            print(f'[DEBUG] Busca de serviços: "{search}" - {cursor.rowcount} resultados')
        else:
            # Sem busca, retornar todos ordenados
            cursor.execute('SELECT id, nome, preco_unit, tempo_h, local, data FROM servicos ORDER BY nome')
            print(f'[DEBUG] Listando todos os serviços - {cursor.rowcount} resultados')
        
        servicos = cursor.fetchall()
        conn.close()
        
        elapsed_time = time.time() - start_time
        print(f'[DEBUG] Tempo de busca: {elapsed_time:.3f}s')
        
        results = [{
            'id': s['id'],
            'nome': s['nome'],
            'preco_unit': float(s['preco_unit']),
            'tempo_h': float(s['tempo_h'] or 0),
            'local': s.get('local') or None,
            'data': s.get('data').strftime('%Y-%m-%d') if s.get('data') else None
        } for s in servicos]
        
        print(f'[DEBUG] Retornando {len(results)} serviços')
        return jsonify(results)
    except Exception as e:
        print(f'[DEBUG] Erro na busca de serviços: {e}')
        return jsonify({'error': str(e)}), 500
