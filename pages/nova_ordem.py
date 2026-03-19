import streamlit as st
import pandas as pd
from datetime import datetime
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection
from utilities.pdf_generator import generate_pdf_report

def show():
    """Exibe a página de Nova Ordem de Serviço"""
    
    st.markdown('<h1 class="section-title">🏠 Nova Ordem de Serviço</h1>', unsafe_allow_html=True)
    
    # Inicializar estado da sessão
    if 'servicos_selecionados' not in st.session_state:
        st.session_state.servicos_selecionados = []
    if 'materiais_selecionados' not in st.session_state:
        st.session_state.materiais_selecionados = []
    if 'adicionais' not in st.session_state:
        st.session_state.adicionais = []
    
    # Formulário principal
    with st.form("nova_ordem_form"):
        
        # Seção Cliente
        st.markdown("### 👥 Dados do Cliente")
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Buscar clientes existentes
            conn = get_db_connection()
            clientes_df = pd.read_sql_query("SELECT id, nome, cnpj_cpf FROM clientes ORDER BY nome", conn)
            
            if not clientes_df.empty:
                cliente_options = {f"{row['nome']} - {row['cnpj_cpf']}": row['id'] 
                                 for _, row in clientes_df.iterrows()}
                cliente_selecionado = st.selectbox(
                    "Selecionar Cliente Existente:",
                    options=[""] + list(cliente_options.keys())
                )
                
                if cliente_selecionado:
                    cliente_id = cliente_options[cliente_selecionado]
                    cliente_data = pd.read_sql_query(
                        f"SELECT * FROM clientes WHERE id = {cliente_id}", conn
                    ).iloc[0]
                    
                    st.info(f"""
                    **Cliente Selecionado:**
                    - Nome: {cliente_data['nome']}
                    - CNPJ/CPF: {cliente_data['cnpj_cpf']}
                    - Endereço: {cliente_data['endereco']}
                    - Telefone: {cliente_data['telefone']}
                    """)
                else:
                    cliente_id = None
            else:
                st.warning("Nenhum cliente cadastrado. Cadastre um cliente primeiro.")
                cliente_id = None
            
            conn.close()
        
        with col2:
            if st.form_submit_button("➕ Novo Cliente", type="secondary"):
                st.session_state.show_novo_cliente = True
        
        # Formulário de novo cliente
        if st.session_state.get('show_novo_cliente', False):
            with st.expander("📝 Cadastrar Novo Cliente", expanded=True):
                novo_nome = st.text_input("Nome/Razão Social *")
                novo_cnpj_cpf = st.text_input("CNPJ/CPF")
                novo_endereco = st.text_area("Endereço")
                novo_telefone = st.text_input("Telefone")
                novo_email = st.text_input("E-mail")
                
                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.form_submit_button("💾 Salvar Cliente", type="primary"):
                        if novo_nome:
                            conn = get_db_connection()
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT INTO clientes (nome, cnpj_cpf, endereco, telefone, email)
                                VALUES (, , , , )
                            """, (novo_nome, novo_cnpj_cpf, novo_endereco, novo_telefone, novo_email))
                            conn.commit()
                            conn.close()
                            st.success("Cliente cadastrado com sucesso!")
                            st.session_state.show_novo_cliente = False
                            st.rerun()
                        else:
                            st.error("Nome é obrigatório!")
                
                with col_cancel:
                    if st.form_submit_button("❌ Cancelar"):
                        st.session_state.show_novo_cliente = False
                        st.rerun()
        
        st.markdown("---")
        
        # Seção Serviços
        st.markdown("### ⚡ Serviços")
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            conn = get_db_connection()
            servicos_df = pd.read_sql_query("SELECT id, nome, preco_unit FROM servicos ORDER BY nome", conn)
            
            if not servicos_df.empty:
                servico_options = {f"{row['nome']} - R$ {row['preco_unit']:.2f}": row['id'] 
                                 for _, row in servicos_df.iterrows()}
                servico_selecionado = st.selectbox(
                    "Selecionar Serviço:",
                    options=[""] + list(servico_options.keys())
                )
            else:
                servico_selecionado = None
                st.warning("Nenhum serviço cadastrado.")
            
            conn.close()
        
        with col2:
            quantidade_servico = st.number_input("Quantidade", min_value=1, value=1)
        
        with col3:
            # Campo de preço editável
            if servico_selecionado:
                # Extrair preço do serviço selecionado
                preco_original = None
                for _, row in servicos_df.iterrows():
                    servico_text = f"{row['nome']} - R$ {row['preco_unit']:.2f}"
                    if servico_text == servico_selecionado:
                        preco_original = row['preco_unit']
                        break
                
                if preco_original is not None:
                    preco_servico = st.number_input(
                        "Preço Unitário (R$)", 
                        min_value=0.0, 
                        value=float(preco_original), 
                        step=0.01,
                        key="preco_servico"
                    )
                else:
                    preco_servico = st.number_input(
                        "Preço Unitário (R$)", 
                        min_value=0.0, 
                        value=0.0, 
                        step=0.01,
                        key="preco_servico"
                    )
            else:
                preco_servico = st.number_input(
                    "Preço Unitário (R$)", 
                    min_value=0.0, 
                    value=0.0, 
                    step=0.01,
                    key="preco_servico"
                )
        
        if servico_selecionado and st.form_submit_button("➕ Adicionar Serviço"):
            servico_id = servico_options[servico_selecionado]
            conn = get_db_connection()
            servico_data = pd.read_sql_query(f"SELECT * FROM servicos WHERE id = {servico_id}", conn).iloc[0]
            conn.close()
            
            valor_total = preco_servico * quantidade_servico
            
            novo_servico = {
                'servico_id': servico_id,
                'descricao': servico_data['nome'],
                'qtd': quantidade_servico,
                'valor_unit': preco_servico,
                'valor_total': valor_total
            }
            
            st.session_state.servicos_selecionados.append(novo_servico)
            st.success(f"Serviço '{servico_data['nome']}' adicionado!")
            st.rerun()
        
        # Exibir serviços selecionados
        if st.session_state.servicos_selecionados:
            st.markdown("**Serviços Selecionados:**")
            for i, servico in enumerate(st.session_state.servicos_selecionados):
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                with col1:
                    st.write(f"• {servico['descricao']}")
                with col2:
                    st.write(f"Qtd: {servico['qtd']}")
                with col3:
                    st.write(f"R$ {servico['valor_unit']:.2f}")
                with col4:
                    if st.form_submit_button("🗑️", key=f"del_servico_{i}"):
                        st.session_state.servicos_selecionados.pop(i)
                        st.rerun()
        
        st.markdown("---")
        
        # Seção Materiais
        st.markdown("### 🔧 Materiais")
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            conn = get_db_connection()
            materiais_df = pd.read_sql_query("SELECT id, nome, marca, preco_unit FROM materiais ORDER BY nome", conn)
            
            if not materiais_df.empty:
                material_options = {f"{row['nome']} - {row['marca']} - R$ {row['preco_unit']:.2f}": row['id'] 
                                  for _, row in materiais_df.iterrows()}
                material_selecionado = st.selectbox(
                    "Selecionar Material:",
                    options=[""] + list(material_options.keys())
                )
            else:
                material_selecionado = None
                st.warning("Nenhum material cadastrado.")
            
            conn.close()
        
        with col2:
            quantidade_material = st.number_input("Quantidade", min_value=1, value=1, key="qtd_material")
        
        with col3:
            # Campo de preço editável
            if material_selecionado:
                # Extrair preço do material selecionado
                preco_original = None
                for _, row in materiais_df.iterrows():
                    material_text = f"{row['nome']} - {row['marca']} - R$ {row['preco_unit']:.2f}"
                    if material_text == material_selecionado:
                        preco_original = row['preco_unit']
                        break
                
                if preco_original is not None:
                    preco_material = st.number_input(
                        "Preço Unitário (R$)", 
                        min_value=0.0, 
                        value=float(preco_original), 
                        step=0.01,
                        key="preco_material"
                    )
                else:
                    preco_material = st.number_input(
                        "Preço Unitário (R$)", 
                        min_value=0.0, 
                        value=0.0, 
                        step=0.01,
                        key="preco_material"
                    )
            else:
                preco_material = st.number_input(
                    "Preço Unitário (R$)", 
                    min_value=0.0, 
                    value=0.0, 
                    step=0.01,
                    key="preco_material"
                )
        
        if material_selecionado and st.form_submit_button("➕ Adicionar Material"):
            material_id = material_options[material_selecionado]
            conn = get_db_connection()
            material_data = pd.read_sql_query(f"SELECT * FROM materiais WHERE id = {material_id}", conn).iloc[0]
            conn.close()
            
            valor_total = preco_material * quantidade_material
            
            novo_material = {
                'material_id': material_id,
                'descricao': f"{material_data['nome']} - {material_data['marca']}",
                'qtd': quantidade_material,
                'valor_unit': preco_material,
                'valor_total': valor_total
            }
            
            st.session_state.materiais_selecionados.append(novo_material)
            st.success(f"Material '{material_data['nome']}' adicionado!")
            st.rerun()
        
        # Exibir materiais selecionados
        if st.session_state.materiais_selecionados:
            st.markdown("**Materiais Selecionados:**")
            for i, material in enumerate(st.session_state.materiais_selecionados):
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                with col1:
                    st.write(f"• {material['descricao']}")
                with col2:
                    st.write(f"Qtd: {material['qtd']}")
                with col3:
                    st.write(f"R$ {material['valor_unit']:.2f}")
                with col4:
                    if st.form_submit_button("🗑️", key=f"del_material_{i}"):
                        st.session_state.materiais_selecionados.pop(i)
                        st.rerun()
        
        st.markdown("---")
        
        # Seção Deslocamento
        st.markdown("### 🚚 Deslocamento")
        col1, col2 = st.columns(2)
        
        with col1:
            endereco_origem = st.text_input("Endereço de Origem")
        
        with col2:
            endereco_destino = st.text_input("Endereço de Destino")
        
        col1, col2 = st.columns(2)
        with col1:
            km = st.number_input("Distância (km)", min_value=0.0, value=0.0, step=0.1)
        
        with col2:
            valor_km = 5.00
            valor_deslocamento = km * valor_km
            st.metric("Valor do Deslocamento", f"R$ {valor_deslocamento:.2f}")
        
        st.markdown("---")
        
        # Seção Adicionais
        st.markdown("### 💰 Impostos, BDI e Descontos")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Impostos
            st.markdown("**Impostos:**")
            st.markdown("*Selecionar descrição já cadastrada, apenas valor será manual*")
            conn = get_db_connection()
            impostos_df = pd.read_sql_query("SELECT id, descricao FROM impostos_bdi WHERE tipo = 'imposto'", conn)
            
            if not impostos_df.empty:
                imposto_desc = st.selectbox("Selecionar Imposto:", [""] + impostos_df['descricao'].tolist())
                if imposto_desc:
                    valor_imposto = st.number_input("Valor:", min_value=0.0, value=0.0, key="valor_imposto")
                    if st.form_submit_button("➕ Adicionar Imposto"):
                        novo_imposto = {
                            'tipo': 'imposto',
                            'descricao': imposto_desc,
                            'valor': valor_imposto
                        }
                        st.session_state.adicionais.append(novo_imposto)
                        st.success(f"Imposto '{imposto_desc}' adicionado!")
                        st.rerun()
            
            conn.close()
        
        with col2:
            # BDI
            st.markdown("**BDI:**")
            st.markdown("*Selecionar descrição já cadastrada, apenas valor será manual*")
            conn = get_db_connection()
            bdi_df = pd.read_sql_query("SELECT id, descricao FROM impostos_bdi WHERE tipo = 'bdi'", conn)
            
            if not bdi_df.empty:
                bdi_desc = st.selectbox("Selecionar BDI:", [""] + bdi_df['descricao'].tolist())
                if bdi_desc:
                    valor_bdi = st.number_input("Valor:", min_value=0.0, value=0.0, key="valor_bdi")
                    if st.form_submit_button("➕ Adicionar BDI"):
                        novo_bdi = {
                            'tipo': 'bdi',
                            'descricao': bdi_desc,
                            'valor': valor_bdi
                        }
                        st.session_state.adicionais.append(novo_bdi)
                        st.success(f"BDI '{bdi_desc}' adicionado!")
                        st.rerun()
            
            conn.close()
        
        with col3:
            # Descontos
            st.markdown("**Descontos:**")
            st.markdown("*Apenas valor, sem quantidade nem descrição*")
            valor_desconto = st.number_input("Valor do Desconto:", min_value=0.0, value=0.0, key="valor_desconto")
            if st.form_submit_button("➕ Adicionar Desconto"):
                if valor_desconto > 0:
                    novo_desconto = {
                        'tipo': 'desconto',
                        'descricao': 'Desconto',
                        'valor': valor_desconto
                    }
                    st.session_state.adicionais.append(novo_desconto)
                    st.success(f"Desconto de R$ {valor_desconto:.2f} adicionado!")
                    st.rerun()
        
        # Exibir adicionais
        if st.session_state.adicionais:
            st.markdown("**Adicionais:**")
            for i, adicional in enumerate(st.session_state.adicionais):
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    st.write(f"• {adicional['descricao']} ({adicional['tipo']})")
                with col2:
                    st.write(f"R$ {adicional['valor']:.2f}")
                with col3:
                    if st.form_submit_button("🗑️", key=f"del_adicional_{i}"):
                        st.session_state.adicionais.pop(i)
                        st.rerun()
        
        st.markdown("---")
        
        # Seção Forma de Pagamento
        st.markdown("### 💳 Forma de Pagamento")
        st.markdown("*Opções: PIX, Boleto, Dinheiro ou Parcelado (1x a 12x)*")
        
        conn = get_db_connection()
        formas_df = pd.read_sql_query("SELECT id, nome, tipo, parcelas_max FROM formas_pagamento", conn)
        
        forma_pagamento_options = {f"{row['nome']}": row['id'] 
                                 for _, row in formas_df.iterrows()}
        forma_pagamento_selecionada = st.selectbox(
            "Forma de Pagamento:",
            options=list(forma_pagamento_options.keys())
        )
        
        # Verificar se é parcelado
        forma_data = formas_df[formas_df['nome'] == forma_pagamento_selecionada].iloc[0]
        parcelas = 1
        if forma_data['tipo'] == 'Parcelado':
            st.markdown("*Se parcelado, permitir selecionar número de parcelas*")
            parcelas = st.number_input("Número de Parcelas:", min_value=1, max_value=forma_data['parcelas_max'], value=1)
        
        conn.close()
        
        st.markdown("---")
        
        # Resumo Financeiro
        st.markdown("### 💰 Resumo Financeiro")
        st.markdown("#### 💰 Resumo Financeiro (exibido automaticamente):")
        
        # Calcular totais
        total_servicos = sum(s['valor_total'] for s in st.session_state.servicos_selecionados)
        total_materiais = sum(m['valor_total'] for m in st.session_state.materiais_selecionados)
        total_impostos = sum(a['valor'] for a in st.session_state.adicionais if a['tipo'] == 'imposto')
        total_bdi = sum(a['valor'] for a in st.session_state.adicionais if a['tipo'] == 'bdi')
        total_descontos = sum(a['valor'] for a in st.session_state.adicionais if a['tipo'] == 'desconto')
        
        total_final = total_servicos + total_materiais + valor_deslocamento + total_impostos + total_bdi - total_descontos
        
        # Exibir resumo no formato solicitado
        st.markdown(f"""
        (+ ) Materiais .................. R$ {total_materiais:.2f}  
        (+ ) Serviços .................. R$ {total_servicos:.2f}  
        (+ ) Deslocamento .............. R$ {valor_deslocamento:.2f}  
        (+ ) Impostos .................. R$ {total_impostos:.2f}  
        (+ ) BDI ....................... R$ {total_bdi:.2f}  
        (- ) Descontos ................. R$ {total_descontos:.2f}  
        **Total Final:** R$ {total_final:.2f}
        """)
        
        # Informações de pagamento
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"**Forma de Pagamento:** {forma_pagamento_selecionada}")
        
        with col2:
            if forma_data['tipo'] == 'Parcelado':
                valor_parcela = total_final / parcelas
                st.markdown(f"**Valor da Parcela:** R$ {valor_parcela:.2f}")
        
        # Botões de ação
        col1, col2 = st.columns(2)
        
        with col1:
            salvar_os = st.form_submit_button("💾 Salvar Ordem de Serviço", type="primary")
        
        with col2:
            if st.session_state.get('os_salva', False):
                gerar_pdf = st.form_submit_button("📄 Gerar Relatório PDF")
        
        # Salvar OS
        if salvar_os:
            if cliente_id is None:
                st.error("Selecione um cliente!")
            elif not st.session_state.servicos_selecionados and not st.session_state.materiais_selecionados:
                st.error("Adicione pelo menos um serviço ou material!")
            else:
                # Salvar no banco
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Inserir ordem de serviço
                cursor.execute("""
                    INSERT INTO ordens_servico 
                    (cliente_id, data, endereco_origem, endereco_destino, km, valor_deslocamento, 
                     forma_pagamento_id, total, status)
                    VALUES (, , , , , , , , )
                """, (cliente_id, datetime.now().strftime('%Y-%m-%d'), 
                     endereco_origem, endereco_destino, km, valor_deslocamento,
                     forma_pagamento_options[forma_pagamento_selecionada], total_final, 'Nova'))
                
                ordem_id = cursor.lastrowid
                
                # Inserir itens de serviço
                for servico in st.session_state.servicos_selecionados:
                    cursor.execute("""
                        INSERT INTO itens_servico 
                        (ordem_id, servico_id, descricao, qtd, valor_unit, valor_total)
                        VALUES (, , , , , )
                    """, (ordem_id, servico['servico_id'], servico['descricao'], 
                         servico['qtd'], servico['valor_unit'], servico['valor_total']))
                
                # Inserir itens de material
                for material in st.session_state.materiais_selecionados:
                    cursor.execute("""
                        INSERT INTO itens_material 
                        (ordem_id, material_id, descricao, qtd, valor_unit, valor_total)
                        VALUES (, , , , , )
                    """, (ordem_id, material['material_id'], material['descricao'], 
                         material['qtd'], material['valor_unit'], material['valor_total']))
                
                # Inserir adicionais
                for adicional in st.session_state.adicionais:
                    cursor.execute("""
                        INSERT INTO adicionais (ordem_id, tipo, descricao, valor)
                        VALUES (, , , )
                    """, (ordem_id, adicional['tipo'], adicional['descricao'], adicional['valor']))
                
                conn.commit()
                conn.close()
                
                st.session_state.os_salva = True
                st.session_state.ultima_os_id = ordem_id
                st.success(f"Ordem de Serviço #{ordem_id} salva com sucesso!")
                st.rerun()
        
        # Gerar PDF
        if st.session_state.get('os_salva', False) and 'gerar_pdf' in locals() and gerar_pdf:
            # Preparar dados para o PDF
            conn = get_db_connection()
            
            # Dados da ordem
            ordem_data = {
                'numero_os': st.session_state.ultima_os_id,
                'data': datetime.now().strftime('%d/%m/%Y'),
                'cliente': pd.read_sql_query(f"""
                    SELECT c.* FROM clientes c 
                    JOIN ordens_servico os ON c.id = os.cliente_id 
                    WHERE os.id = {st.session_state.ultima_os_id}
                """, conn).iloc[0].to_dict(),
                'servicos': st.session_state.servicos_selecionados,
                'materiais': st.session_state.materiais_selecionados,
                'km': km,
                'valor_deslocamento': valor_deslocamento,
                'adicionais': st.session_state.adicionais,
                'total': total_final,
                'forma_pagamento': forma_pagamento_selecionada
            }
            
            conn.close()
            
            # Gerar PDF
            pdf_path = f"pdfs/relatorio_os_{st.session_state.ultima_os_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            generate_pdf_report(ordem_data, pdf_path)
            
            # Download do PDF
            with open(pdf_path, "rb") as pdf_file:
                st.download_button(
                    label="📥 Baixar Relatório PDF",
                    data=pdf_file.read(),
                    file_name=pdf_path,
                    mime="application/pdf"
                )
            
            st.success("Relatório PDF gerado com sucesso!")
