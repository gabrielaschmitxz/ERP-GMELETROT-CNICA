from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from database_web import get_db_connection
from decorators import login_required
from mapbox_integration_web import MapboxIntegration
from pdf_generator import OrderPDFGenerator
from datetime import datetime
import psycopg2.extras
import json

bp = Blueprint('ordens', __name__, url_prefix='/ordens')
mapbox = MapboxIntegration()
pdf_generator = OrderPDFGenerator()

@bp.route('/')
@login_required
def listar():
    """Listar todas as ordens de serviço"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Filtros
        cliente_id = request.args.get('cliente_id', type=int)
        status = request.args.get('status', '')
        
        query = '''
            SELECT os.*, c.nome as cliente_nome, fp.nome as forma_pagamento_nome
            FROM ordens_servico os
            LEFT JOIN clientes c ON os.cliente_id = c.id
            LEFT JOIN formas_pagamento fp ON os.forma_pagamento_id = fp.id
            WHERE 1=1
        '''
        params = []
        
        if cliente_id:
            query += ' AND os.cliente_id = %s'
            params.append(cliente_id)
        
        if status:
            query += ' AND os.status = %s'
            params.append(status)
        
        query += ' ORDER BY os.id DESC'
        cursor.execute(query, params)
        ordens = cursor.fetchall()
        
        # Carregar clientes para filtro (mesma conexão)
        cursor.execute('SELECT id, nome FROM clientes ORDER BY nome')
        clientes = cursor.fetchall()
        conn.close()
        
        return render_template('ordens/listar.html', ordens=ordens, clientes=clientes, 
                             cliente_id=cliente_id, status=status)
    except Exception as e:
        flash(f'Erro ao carregar ordens: {e}', 'danger')
        return render_template('ordens/listar.html', ordens=[], clientes=[])

@bp.route('/nova', methods=['GET', 'POST'])
@login_required
def nova():
    """Criar nova ordem de serviço"""
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            cliente_id = data.get('cliente_id')
            data_ordem_str = data.get('data')
            endereco_origem = data.get('endereco_origem', '').strip()
            endereco_destino = data.get('endereco_destino', '').strip()
            servicos = data.get('servicos', [])
            materiais = data.get('materiais', [])
            adicionais = data.get('adicionais', [])
            forma_pagamento_id = data.get('forma_pagamento_id')
            assinatura_id = data.get('assinatura_id')
            parcelas = data.get('parcelas', 1)
            distance_data = data.get('distance_data', {})
            
            if not cliente_id:
                return jsonify({'success': False, 'error': 'Cliente é obrigatório!'}), 400
            
            # Validar: precisa ter endereços OU distance_data com KM
            has_distance_data = distance_data and distance_data.get('distance_km')
            if (not endereco_origem or not endereco_destino) and not has_distance_data:
                return jsonify({'success': False, 'error': 'Preencha os endereços ou informe os KM manualmente!'}), 400
            
            # Se não tem endereços mas tem KM, usar valores padrão
            if not endereco_origem:
                endereco_origem = 'Não informado'
            if not endereco_destino:
                endereco_destino = 'Não informado'
            
            if not servicos and not materiais:
                return jsonify({'success': False, 'error': 'Adicione pelo menos um serviço ou material!'}), 400
            
            # Converter data
            try:
                data_ordem = datetime.strptime(data_ordem_str, "%d/%m/%Y").date()
            except:
                data_ordem = datetime.now().date()
            
            # Calcular totais
            servicos_total = sum(s.get('total', 0) for s in servicos)
            materiais_total = sum(m.get('total', 0) for m in materiais)
            impostos_total = sum(a.get('valor', 0) for a in adicionais if a.get('tipo') == 'imposto')
            bdi_total = sum(a.get('valor', 0) for a in adicionais if a.get('tipo') == 'bdi')
            descontos_total = sum(a.get('valor', 0) for a in adicionais if a.get('tipo') == 'desconto')
            deslocamento_total = distance_data.get('displacement_cost', 0) or 0
            
            total_geral = (servicos_total + materiais_total + deslocamento_total + 
                          impostos_total + bdi_total - descontos_total)
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Inserir ordem
            cursor.execute('''
                INSERT INTO ordens_servico (cliente_id, data, endereco_origem, endereco_destino,
                                          km, valor_deslocamento, total, status, forma_pagamento_id, parcelas, assinatura_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (cliente_id, data_ordem, endereco_origem, endereco_destino,
                  distance_data.get('distance_km', 0), deslocamento_total, total_geral, 
                  'Nova', forma_pagamento_id, parcelas, assinatura_id))
            
            ordem_id = cursor.fetchone()[0]
            
            # Migração automática: adicionar colunas 'local' e 'data' na tabela itens_servico se não existirem
            cursor.execute('''
                DO $$ 
                BEGIN 
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='itens_servico' AND column_name='local'
                    ) THEN
                        ALTER TABLE itens_servico ADD COLUMN local VARCHAR(255);
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='itens_servico' AND column_name='data'
                    ) THEN
                        ALTER TABLE itens_servico ADD COLUMN data DATE;
                    END IF;
                END $$;
            ''')
            
            # Migração automática: adicionar coluna 'data' na tabela itens_material se não existir
            cursor.execute('''
                DO $$ 
                BEGIN 
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='itens_material' AND column_name='data'
                    ) THEN
                        ALTER TABLE itens_material ADD COLUMN data DATE;
                    END IF;
                END $$;
            ''')
            conn.commit()
            
            # Inserir serviços
            for servico in servicos:
                descricao = servico.get('nome', '')
                if servico.get('tempo') and servico.get('taxa'):
                    descricao += f" - Tempo: {servico['tempo']}h x Taxa: R$ {servico['taxa']:.2f}/h"
                
                # Tratar local de forma segura (pode ser None ou string vazia)
                local = servico.get('local')
                if local:
                    local = str(local).strip() or None
                else:
                    local = None
                
                # Tratar data de forma segura
                data_servico = servico.get('data')
                if data_servico:
                    try:
                        if isinstance(data_servico, str):
                            data_servico = datetime.strptime(data_servico, "%Y-%m-%d").date()
                    except:
                        data_servico = None
                else:
                    data_servico = None
                
                cursor.execute('''
                    INSERT INTO itens_servico (ordem_id, servico_id, descricao, qtd, valor_unit, valor_total, local, data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (ordem_id, servico.get('id'), descricao, servico.get('qtd', 1),
                      servico.get('preco_unit', 0), servico.get('total', 0), local, data_servico))
            
            # Inserir materiais
            for material in materiais:
                descricao = material.get('nome', '')
                if material.get('marca'):
                    descricao += f" - {material['marca']}"
                
                # Converter data se fornecida
                data_material = None
                if material.get('data'):
                    try:
                        data_material = datetime.strptime(material.get('data'), '%Y-%m-%d').date()
                    except:
                        pass
                
                cursor.execute('''
                    INSERT INTO itens_material (ordem_id, material_id, descricao, qtd, valor_unit, valor_total, data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (ordem_id, material.get('id'), descricao, material.get('qtd', 1),
                      material.get('preco_unit', 0), material.get('total', 0), data_material))
            
            # Inserir adicionais
            for adicional in adicionais:
                cursor.execute('''
                    INSERT INTO adicionais (ordem_id, tipo, descricao, valor)
                    VALUES (%s, %s, %s, %s)
                ''', (ordem_id, adicional.get('tipo'), adicional.get('descricao'), adicional.get('valor', 0)))
            
            conn.commit()
            conn.close()
            
            return jsonify({'success': True, 'ordem_id': ordem_id, 'message': 'Ordem de serviço salva com sucesso!'})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    # GET - mostrar formulário
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Otimizar: fazer todas as consultas na mesma conexão
        cursor.execute('SELECT id, nome FROM clientes ORDER BY nome')
        clientes = cursor.fetchall()
        
        cursor.execute('SELECT id, nome, tipo, parcelas_max FROM formas_pagamento WHERE ativo = true ORDER BY nome')
        formas_pagamento = cursor.fetchall()
        
        # Adicionar coluna cargo se não existir (migração) - apenas uma vez
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
        
        cursor.execute('SELECT id, nome, cargo, caminho_imagem, ativo, padrao FROM assinaturas WHERE ativo = true ORDER BY padrao DESC, nome')
        assinaturas = cursor.fetchall()
        
        # Carregar listas para seleção (otimizado: apenas campos necessários) - apenas ativos
        cursor.execute('SELECT id, nome, preco_unit FROM servicos WHERE ativo = true ORDER BY nome')
        servicos = cursor.fetchall()
        
        cursor.execute('SELECT id, nome, marca, preco_unit FROM materiais WHERE ativo = true ORDER BY nome')
        materiais = cursor.fetchall()
        
        cursor.execute("SELECT id, descricao, valor FROM impostos_bdi WHERE tipo = 'imposto' AND ativo = true ORDER BY descricao")
        impostos = cursor.fetchall()
        
        cursor.execute("SELECT id, descricao, valor FROM impostos_bdi WHERE tipo = 'bdi' AND ativo = true ORDER BY descricao")
        bdi_list = cursor.fetchall()
        
        conn.close()
        
        return render_template('ordens/form.html', ordem=None,
                             clientes=clientes, 
                             formas_pagamento=formas_pagamento,
                             servicos=servicos, materiais=materiais,
                             impostos=impostos, bdi_list=bdi_list,
                             assinaturas=assinaturas)
    except Exception as e:
        flash(f'Erro ao carregar formulário: {e}', 'danger')
        return redirect(url_for('ordens.listar'))

@bp.route('/calcular_distancia', methods=['POST'])
@login_required
def calcular_distancia():
    """Calcular distância entre endereços"""
    try:
        data = request.get_json()
        origem = data.get('origem', '').strip()
        destino = data.get('destino', '').strip()
        taxa_km = float(data.get('taxa_km', 5.0))
        
        if not origem or not destino:
            return jsonify({'success': False, 'error': 'Preencha ambos os endereços!'}), 400
        
        result = mapbox.process_addresses(origem, destino)
        
        if result['success']:
            # Recalcular com taxa personalizada
            if taxa_km and taxa_km > 0:
                result['displacement_cost'] = round(result['distance_km'] * taxa_km, 2)
            
            return jsonify({'success': True, 'data': result})
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Erro ao calcular distância')}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Editar ordem de serviço"""
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            cliente_id = data.get('cliente_id')
            data_ordem_str = data.get('data')
            endereco_origem = data.get('endereco_origem', '').strip()
            endereco_destino = data.get('endereco_destino', '').strip()
            servicos = data.get('servicos', [])
            materiais = data.get('materiais', [])
            adicionais = data.get('adicionais', [])
            forma_pagamento_id = data.get('forma_pagamento_id')
            assinatura_id = data.get('assinatura_id')
            parcelas = data.get('parcelas', 1)
            distance_data = data.get('distance_data', {})
            
            if not cliente_id:
                return jsonify({'success': False, 'error': 'Cliente é obrigatório!'}), 400
            
            # Converter data
            try:
                data_ordem = datetime.strptime(data_ordem_str, "%d/%m/%Y").date()
            except:
                data_ordem = datetime.now().date()
            
            # Calcular totais
            servicos_total = sum(s.get('total', 0) for s in servicos)
            materiais_total = sum(m.get('total', 0) for m in materiais)
            impostos_total = sum(a.get('valor', 0) for a in adicionais if a.get('tipo') == 'imposto')
            bdi_total = sum(a.get('valor', 0) for a in adicionais if a.get('tipo') == 'bdi')
            descontos_total = sum(a.get('valor', 0) for a in adicionais if a.get('tipo') == 'desconto')
            deslocamento_total = distance_data.get('displacement_cost', 0) or 0
            
            total_geral = (servicos_total + materiais_total + deslocamento_total + 
                          impostos_total + bdi_total - descontos_total)
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Atualizar ordem
            cursor.execute('''
                UPDATE ordens_servico 
                SET cliente_id=%s, data=%s, endereco_origem=%s, endereco_destino=%s,
                    km=%s, valor_deslocamento=%s, total=%s, forma_pagamento_id=%s, parcelas=%s, assinatura_id=%s
                WHERE id=%s
            ''', (cliente_id, data_ordem, endereco_origem, endereco_destino,
                  distance_data.get('distance_km', 0), deslocamento_total, total_geral, 
                  forma_pagamento_id, parcelas, assinatura_id, id))
            
            # Migração automática: adicionar coluna 'local' na tabela itens_servico se não existir
            cursor.execute('''
                DO $$ 
                BEGIN 
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='itens_servico' AND column_name='local'
                    ) THEN
                        ALTER TABLE itens_servico ADD COLUMN local VARCHAR(255);
                    END IF;
                END $$;
            ''')
            conn.commit()
            
            # Migração automática: adicionar colunas 'local' e 'data' na tabela itens_servico se não existirem
            cursor.execute('''
                DO $$ 
                BEGIN 
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'itens_servico' AND column_name = 'local'
                    ) THEN
                        ALTER TABLE itens_servico ADD COLUMN local VARCHAR(255);
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'itens_servico' AND column_name = 'data'
                    ) THEN
                        ALTER TABLE itens_servico ADD COLUMN data DATE;
                    END IF;
                END $$;
            ''')
            
            # Migração automática: adicionar coluna 'data' na tabela itens_material se não existir
            cursor.execute('''
                DO $$ 
                BEGIN 
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'itens_material' AND column_name = 'data'
                    ) THEN
                        ALTER TABLE itens_material ADD COLUMN data DATE;
                    END IF;
                END $$;
            ''')
            
            # Limpar itens antigos para recriar
            cursor.execute('DELETE FROM itens_servico WHERE ordem_id=%s', (id,))
            cursor.execute('DELETE FROM itens_material WHERE ordem_id=%s', (id,))
            cursor.execute('DELETE FROM adicionais WHERE ordem_id=%s', (id,))
            
            # Inserir serviços
            for servico in servicos:
                descricao = servico.get('nome', '')
                if servico.get('tempo') and servico.get('taxa'):
                    descricao += f" - Tempo: {servico['tempo']}h x Taxa: R$ {servico['taxa']:.2f}/h"
                
                # Tratar local de forma segura (pode ser None ou string vazia)
                local = servico.get('local')
                if local:
                    local = str(local).strip() or None
                else:
                    local = None
                
                # Tratar data de forma segura
                data_servico = servico.get('data')
                if data_servico:
                    try:
                        if isinstance(data_servico, str):
                            data_servico = datetime.strptime(data_servico, "%Y-%m-%d").date()
                    except:
                        data_servico = None
                else:
                    data_servico = None
                
                cursor.execute('''
                    INSERT INTO itens_servico (ordem_id, servico_id, descricao, qtd, valor_unit, valor_total, local, data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (id, servico.get('id'), descricao, servico.get('qtd', 1),
                      servico.get('preco_unit', 0), servico.get('total', 0), local, data_servico))
            
            # Inserir materiais
            for material in materiais:
                descricao = material.get('nome', '')
                if material.get('marca'):
                    descricao += f" - {material['marca']}"
                
                # Converter data se fornecida
                data_material = None
                if material.get('data'):
                    try:
                        data_material = datetime.strptime(material.get('data'), '%Y-%m-%d').date()
                    except:
                        pass
                
                cursor.execute('''
                    INSERT INTO itens_material (ordem_id, material_id, descricao, qtd, valor_unit, valor_total, data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (id, material.get('id'), descricao, material.get('qtd', 1),
                      material.get('preco_unit', 0), material.get('total', 0), data_material))
            
            # Inserir adicionais
            for adicional in adicionais:
                cursor.execute('''
                    INSERT INTO adicionais (ordem_id, tipo, descricao, valor)
                    VALUES (%s, %s, %s, %s)
                ''', (id, adicional.get('tipo'), adicional.get('descricao'), adicional.get('valor', 0)))
            
            conn.commit()
            conn.close()
            
            return jsonify({'success': True, 'ordem_id': id, 'message': 'Ordem de serviço atualizada com sucesso!'})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    # GET - Carregar dados para edição
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Buscar Ordem
        cursor.execute('SELECT * FROM ordens_servico WHERE id = %s', (id,))
        ordem = cursor.fetchone()
        
        if not ordem:
            flash('Ordem não encontrada!', 'danger')
            return redirect(url_for('ordens.listar'))
            
        # Buscar Itens
        cursor.execute('SELECT * FROM itens_servico WHERE ordem_id = %s', (id,))
        db_servicos = cursor.fetchall()
        
        cursor.execute('SELECT * FROM itens_material WHERE ordem_id = %s', (id,))
        db_materiais = cursor.fetchall()
        
        cursor.execute('SELECT * FROM adicionais WHERE ordem_id = %s', (id,))
        db_adicionais = cursor.fetchall()
        
        # Preparar JSON para o frontend
        servicos_js = []
        for s in db_servicos:
            servicos_js.append({
                'id': s['servico_id'],
                'nome': s['descricao'].split(' - ')[0],
                'preco_unit': float(s['valor_unit']),
                'qtd': s['qtd'],
                'total': float(s['valor_total']),
                'tempo': 0, 'taxa': 0, # Simplificado
                'local': s.get('local') or None,
                'data': s.get('data').strftime('%Y-%m-%d') if s.get('data') else None
            })
            
        materiais_js = []
        for m in db_materiais:
            # Calcular adicional a partir dos valores salvos
            # Se total != preco_unit * qtd, então há um adicional aplicado
            preco_unit = float(m['valor_unit'])
            qtd = m['qtd']
            total = float(m['valor_total'])
            
            # Calcular adicional: preco_com_adicional = total / qtd
            # adicional = ((preco_com_adicional / preco_unit) - 1) * 100
            adicional = 0.0
            if preco_unit > 0 and qtd > 0:
                preco_com_adicional = total / qtd
                adicional = ((preco_com_adicional / preco_unit) - 1) * 100
                # Arredondar para evitar problemas de precisão
                adicional = round(adicional, 2)
            
            materiais_js.append({
                'id': m['material_id'],
                'nome': m['descricao'].split(' - ')[0],
                'preco_unit': preco_unit,
                'adicional': adicional,
                'qtd': qtd,
                'total': total,
                'data': m['data'].strftime('%Y-%m-%d') if m.get('data') else None
            })
            
        adicionais_js = []
        for a in db_adicionais:
            adicionais_js.append({
                'tipo': a['tipo'],
                'descricao': a['descricao'],
                'valor': float(a['valor'])
            })
            
        # Carregar listas auxiliares (otimizado: apenas campos necessários)
        cursor.execute('SELECT id, nome FROM clientes WHERE ativo = true ORDER BY nome')
        clientes = cursor.fetchall()
        cursor.execute('SELECT id, nome, tipo, parcelas_max FROM formas_pagamento WHERE ativo = true ORDER BY nome')
        formas_pagamento = cursor.fetchall()
        
        # Adicionar coluna cargo se não existir (migração) - apenas uma vez
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
        
        cursor.execute('SELECT id, nome, cargo, caminho_imagem, ativo, padrao FROM assinaturas WHERE ativo = true ORDER BY padrao DESC, nome')
        assinaturas = cursor.fetchall()
        cursor.execute('SELECT id, nome, preco_unit FROM servicos WHERE ativo = true ORDER BY nome')
        servicos_list = cursor.fetchall()
        cursor.execute('SELECT id, nome, marca, preco_unit FROM materiais WHERE ativo = true ORDER BY nome')
        materiais_list = cursor.fetchall()
        cursor.execute("SELECT id, descricao, valor FROM impostos_bdi WHERE tipo = 'imposto' AND ativo = true ORDER BY descricao")
        impostos = cursor.fetchall()
        cursor.execute("SELECT id, descricao, valor FROM impostos_bdi WHERE tipo = 'bdi' AND ativo = true ORDER BY descricao")
        bdi_list = cursor.fetchall()
        
        conn.close()
        
        return render_template('ordens/form.html', 
                             ordem=ordem,
                             servicos_json=json.dumps(servicos_js),
                             materiais_json=json.dumps(materiais_js),
                             adicionais_json=json.dumps(adicionais_js),
                             clientes=clientes, 
                             formas_pagamento=formas_pagamento, 
                             servicos=servicos_list, 
                             materiais=materiais_list,
                             impostos=impostos, 
                             bdi_list=bdi_list,
                             assinaturas=assinaturas)
                             
    except Exception as e:
        flash(f'Erro ao carregar edição: {e}', 'danger')
        return redirect(url_for('ordens.listar'))

@bp.route('/gerar_pdf/<int:id>')
@login_required
def gerar_pdf(id):
    """Gerar PDF da ordem de serviço"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Buscar dados da ordem
        cursor.execute('''
            SELECT os.*, c.id as cliente_id, c.nome as cliente_nome,
                   ass.nome as assinatura_nome
            FROM ordens_servico os
            JOIN clientes c ON os.cliente_id = c.id
            LEFT JOIN assinaturas ass ON os.assinatura_id = ass.id
            WHERE os.id = %s
        ''', (id,))
        ordem = cursor.fetchone()
        
        if not ordem:
            flash('Ordem de serviço não encontrada!', 'danger')
            return redirect(url_for('ordens.listar'))
        
        # Buscar serviços, materiais e adicionais
        cursor.execute('SELECT * FROM itens_servico WHERE ordem_id = %s', (id,))
        servicos = cursor.fetchall()
        
        cursor.execute('SELECT * FROM itens_material WHERE ordem_id = %s', (id,))
        materiais = cursor.fetchall()
        
        cursor.execute('SELECT * FROM adicionais WHERE ordem_id = %s', (id,))
        adicionais = cursor.fetchall()
        
        conn.close()
        
        # Preparar dados para PDF
        order_data = {
            'ordem_id': ordem['id'],
            'cliente_id': ordem['cliente_id'],
            'data_emissao': ordem['data'].strftime("%d/%m/%Y") if ordem['data'] else datetime.now().strftime("%d/%m/%Y"),
            'servicos': [{'id': s['servico_id'], 'nome': s['descricao'], 'qtd': s['qtd'], 
                         'preco_unit': float(s['valor_unit']), 'total': float(s['valor_total']),
                         'local': s.get('local') or None,
                         'data': s.get('data').strftime('%Y-%m-%d') if s.get('data') else None} 
                        for s in servicos],
            'materiais': [{'id': m['material_id'], 'nome': m['descricao'].split(' - ')[0] if ' - ' in m['descricao'] else m['descricao'],
                          'marca': m['descricao'].split(' - ')[1] if ' - ' in m['descricao'] and len(m['descricao'].split(' - ')) > 1 else '',
                          'qtd': m['qtd'], 'preco_unit': float(m['valor_unit']), 'total': float(m['valor_total']),
                          'data': m.get('data').strftime('%d/%m/%Y') if m.get('data') else None} 
                         for m in materiais],
            'adicionais': [{'tipo': a['tipo'], 'descricao': a['descricao'], 'valor': float(a['valor'])} 
                          for a in adicionais],
            'distance_data': {'distance_km': float(ordem['km'] or 0), 
                            'displacement_cost': float(ordem['valor_deslocamento'] or 0)},
            'forma_pagamento_id': ordem['forma_pagamento_id']
        }
        
        if ordem['assinatura_nome']:
            order_data['assinatura'] = {
                'nome': ordem['assinatura_nome']
            }
        
        pdf_path = pdf_generator.generate_pdf(order_data)
        
        return send_file(pdf_path, as_attachment=True, 
                        download_name=f"OrdemDeServico_{id}.pdf", mimetype='application/pdf')
        
    except Exception as e:
        flash(f'Erro ao gerar PDF: {e}', 'danger')
        return redirect(url_for('ordens.listar'))

@bp.route('/alterar_status/<int:id>', methods=['POST'])
@login_required
def alterar_status(id):
    """Alterar status da ordem"""
    try:
        novo_status = request.form.get('status', '').strip()
        
        if not novo_status:
            flash('Status é obrigatório!', 'danger')
            return redirect(url_for('ordens.listar'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE ordens_servico SET status = %s WHERE id = %s', (novo_status, id))
        conn.commit()
        conn.close()
        
        flash('Status atualizado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao atualizar status: {e}', 'danger')
    
    return redirect(url_for('ordens.listar'))

@bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    """Excluir ordem de serviço"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Excluir itens relacionados primeiro
        cursor.execute('DELETE FROM itens_servico WHERE ordem_id = %s', (id,))
        cursor.execute('DELETE FROM itens_material WHERE ordem_id = %s', (id,))
        cursor.execute('DELETE FROM adicionais WHERE ordem_id = %s', (id,))
        
        # Excluir a ordem
        cursor.execute('DELETE FROM ordens_servico WHERE id = %s', (id,))
        
        conn.commit()
        conn.close()
        
        flash('Ordem de serviço excluída com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir ordem: {e}', 'danger')
    
    return redirect(url_for('ordens.listar'))
