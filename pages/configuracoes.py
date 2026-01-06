import streamlit as st
import pandas as pd
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection

def show():
    """Exibe a página de configurações"""
    
    st.markdown('<h1 class="section-title">💰 Formas de Pagamento / Imposto / BDI</h1>', unsafe_allow_html=True)
    
    # Tabs para diferentes configurações
    tab1, tab2, tab3 = st.tabs(["💳 Formas de Pagamento", "📊 Impostos", "📈 BDI"])
    
    with tab1:
        show_formas_pagamento()
    
    with tab2:
        show_impostos()
    
    with tab3:
        show_bdi()

def show_formas_pagamento():
    """Exibe configurações de formas de pagamento"""
    
    st.markdown("### 💳 Formas de Pagamento")
    
    # Buscar formas de pagamento
    conn = get_db_connection()
    formas_df = pd.read_sql_query("SELECT * FROM formas_pagamento ORDER BY nome", conn)
    conn.close()
    
    # Exibir formas existentes
    if not formas_df.empty:
        st.markdown("#### 📋 Formas de Pagamento Cadastradas")
        
        for _, forma in formas_df.iterrows():
            with st.expander(f"💳 {forma['nome']} - {forma['tipo']}"):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.write(f"**Tipo:** {forma['tipo']}")
                
                with col2:
                    st.write(f"**Parcelas Máximas:** {forma['parcelas_max']}")
                
                with col3:
                    if st.button("🗑️ Excluir", key=f"del_forma_{forma['id']}"):
                        # Verificar se a forma de pagamento é usada
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("SELECT COUNT(*) FROM ordens_servico WHERE forma_pagamento_id = ?", (forma['id'],))
                        count_uso = cursor.fetchone()[0]
                        
                        if count_uso > 0:
                            st.error(f"Não é possível excluir pois esta forma de pagamento é usada em {count_uso} ordem(ns) de serviço.")
                        else:
                            cursor.execute("DELETE FROM formas_pagamento WHERE id = ?", (forma['id'],))
                            conn.commit()
                            conn.close()
                            st.success(f"Forma de pagamento '{forma['nome']}' excluída!")
                            st.rerun()
    
    st.markdown("---")
    
    # Formulário para nova forma de pagamento
    st.markdown("#### ➕ Nova Forma de Pagamento")
    
    with st.form("nova_forma_pagamento_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            nome = st.text_input("Nome da Forma de Pagamento *", placeholder="Ex: Cartão de Crédito")
            tipo = st.selectbox("Tipo:", ["PIX", "Boleto", "Dinheiro", "Cartão de Crédito", "Cartão de Débito", "Parcelado"])
        
        with col2:
            parcelas_max = st.number_input("Número Máximo de Parcelas", min_value=1, max_value=24, value=1)
        
        col1, col2 = st.columns(2)
        
        with col1:
            salvar = st.form_submit_button("💾 Salvar Forma de Pagamento", type="primary")
        
        with col2:
            limpar = st.form_submit_button("🗑️ Limpar Formulário")
        
        if salvar:
            if not nome:
                st.error("Nome é obrigatório!")
            else:
                # Verificar se já existe forma com mesmo nome
                conn = get_db_connection()
                cursor = conn.cursor()
                
                cursor.execute("SELECT id FROM formas_pagamento WHERE nome = ?", (nome,))
                if cursor.fetchone():
                    st.error("Forma de pagamento com mesmo nome já cadastrada!")
                    conn.close()
                    return
                
                # Inserir forma de pagamento
                cursor.execute("""
                    INSERT INTO formas_pagamento (nome, tipo, parcelas_max)
                    VALUES (?, ?, ?)
                """, (nome, tipo, parcelas_max))
                
                conn.commit()
                conn.close()
                
                st.success(f"Forma de pagamento '{nome}' cadastrada com sucesso!")
                st.rerun()
        
        if limpar:
            st.rerun()

def show_impostos():
    """Exibe configurações de impostos"""
    
    st.markdown("### 📊 Impostos")
    
    # Buscar impostos
    conn = get_db_connection()
    impostos_df = pd.read_sql_query("SELECT * FROM impostos_bdi WHERE tipo = 'imposto' ORDER BY descricao", conn)
    conn.close()
    
    # Exibir impostos existentes
    if not impostos_df.empty:
        st.markdown("#### 📋 Impostos Cadastrados")
        
        # Tabela de impostos
        st.dataframe(
            impostos_df[['id', 'descricao', 'valor']],
            column_config={
                'id': 'ID',
                'descricao': 'Descrição',
                'valor': st.column_config.NumberColumn('Valor Padrão', format="R$ %.2f")
            },
            use_container_width=True,
            hide_index=True
        )
        
        # Edição inline de impostos
        st.markdown("#### ✏️ Editar Impostos")
        
        for _, imposto in impostos_df.iterrows():
            with st.expander(f"📊 {imposto['descricao']}"):
                col1, col2 = st.columns(2)
                
                with col1:
                    novo_valor = st.number_input(
                        f"Valor para {imposto['descricao']}:",
                        min_value=0.0,
                        value=float(imposto['valor']),
                        step=0.01,
                        format="%.2f",
                        key=f"edit_imposto_{imposto['id']}"
                    )
                
                with col2:
                    if st.button("💾 Atualizar", key=f"update_imposto_{imposto['id']}"):
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("UPDATE impostos_bdi SET valor = ? WHERE id = ?", (novo_valor, imposto['id']))
                        conn.commit()
                        conn.close()
                        st.success(f"Valor do {imposto['descricao']} atualizado!")
                        st.rerun()
    
    st.markdown("---")
    
    # Formulário para novo imposto
    st.markdown("#### ➕ Novo Imposto")
    
    with st.form("novo_imposto_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            descricao = st.text_input("Descrição do Imposto *", placeholder="Ex: ICMS, PIS, COFINS")
        
        with col2:
            valor = st.number_input("Valor Padrão (R$)", min_value=0.0, value=0.0, step=0.01, format="%.2f")
        
        col1, col2 = st.columns(2)
        
        with col1:
            salvar = st.form_submit_button("💾 Salvar Imposto", type="primary")
        
        with col2:
            limpar = st.form_submit_button("🗑️ Limpar Formulário")
        
        if salvar:
            if not descricao:
                st.error("Descrição é obrigatória!")
            else:
                # Verificar se já existe imposto com mesma descrição
                conn = get_db_connection()
                cursor = conn.cursor()
                
                cursor.execute("SELECT id FROM impostos_bdi WHERE tipo = 'imposto' AND descricao = ?", (descricao,))
                if cursor.fetchone():
                    st.error("Imposto com mesma descrição já cadastrado!")
                    conn.close()
                    return
                
                # Inserir imposto
                cursor.execute("""
                    INSERT INTO impostos_bdi (tipo, descricao, valor)
                    VALUES (?, ?, ?)
                """, ('imposto', descricao, valor))
                
                conn.commit()
                conn.close()
                
                st.success(f"Imposto '{descricao}' cadastrado com sucesso!")
                st.rerun()
        
        if limpar:
            st.rerun()

def show_bdi():
    """Exibe configurações de BDI"""
    
    st.markdown("### 📈 BDI (Benefícios e Despesas Indiretas)")
    
    # Buscar BDI
    conn = get_db_connection()
    bdi_df = pd.read_sql_query("SELECT * FROM impostos_bdi WHERE tipo = 'bdi' ORDER BY descricao", conn)
    conn.close()
    
    # Exibir BDI existentes
    if not bdi_df.empty:
        st.markdown("#### 📋 BDI Cadastrados")
        
        # Tabela de BDI
        st.dataframe(
            bdi_df[['id', 'descricao', 'valor']],
            column_config={
                'id': 'ID',
                'descricao': 'Descrição',
                'valor': st.column_config.NumberColumn('Valor Padrão', format="R$ %.2f")
            },
            use_container_width=True,
            hide_index=True
        )
        
        # Calcular total de BDI
        total_bdi = bdi_df['valor'].sum()
        st.info(f"💰 **Total de BDI:** R$ {total_bdi:.2f}")
        
        # Edição inline de BDI
        st.markdown("#### ✏️ Editar BDI")
        
        for _, bdi in bdi_df.iterrows():
            with st.expander(f"📈 {bdi['descricao']}"):
                col1, col2 = st.columns(2)
                
                with col1:
                    novo_valor = st.number_input(
                        f"Valor para {bdi['descricao']}:",
                        min_value=0.0,
                        value=float(bdi['valor']),
                        step=0.01,
                        format="%.2f",
                        key=f"edit_bdi_{bdi['id']}"
                    )
                
                with col2:
                    if st.button("💾 Atualizar", key=f"update_bdi_{bdi['id']}"):
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("UPDATE impostos_bdi SET valor = ? WHERE id = ?", (novo_valor, bdi['id']))
                        conn.commit()
                        conn.close()
                        st.success(f"Valor do {bdi['descricao']} atualizado!")
                        st.rerun()
    
    st.markdown("---")
    
    # Formulário para novo BDI
    st.markdown("#### ➕ Novo BDI")
    
    with st.form("novo_bdi_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            descricao = st.selectbox(
                "Descrição do BDI:",
                ["Administração", "Lucro", "Imprevistos", "Seguro", "Garantia", "Outros"]
            )
            
            if descricao == "Outros":
                descricao = st.text_input("Especificar descrição:", placeholder="Digite a descrição")
        
        with col2:
            valor = st.number_input("Valor Padrão (R$)", min_value=0.0, value=0.0, step=0.01, format="%.2f")
        
        col1, col2 = st.columns(2)
        
        with col1:
            salvar = st.form_submit_button("💾 Salvar BDI", type="primary")
        
        with col2:
            limpar = st.form_submit_button("🗑️ Limpar Formulário")
        
        if salvar:
            if not descricao:
                st.error("Descrição é obrigatória!")
            else:
                # Verificar se já existe BDI com mesma descrição
                conn = get_db_connection()
                cursor = conn.cursor()
                
                cursor.execute("SELECT id FROM impostos_bdi WHERE tipo = 'bdi' AND descricao = ?", (descricao,))
                if cursor.fetchone():
                    st.error("BDI com mesma descrição já cadastrado!")
                    conn.close()
                    return
                
                # Inserir BDI
                cursor.execute("""
                    INSERT INTO impostos_bdi (tipo, descricao, valor)
                    VALUES (?, ?, ?)
                """, ('bdi', descricao, valor))
                
                conn.commit()
                conn.close()
                
                st.success(f"BDI '{descricao}' cadastrado com sucesso!")
                st.rerun()
        
        if limpar:
            st.rerun()
    
    # Informações sobre BDI
    st.markdown("---")
    st.markdown("#### ℹ️ Sobre BDI")
    
    st.info("""
    **BDI (Benefícios e Despesas Indiretas)** são custos que não podem ser diretamente atribuídos 
    a um projeto específico, mas são necessários para a operação da empresa:
    
    - **Administração:** Custos administrativos gerais
    - **Lucro:** Margem de lucro desejada
    - **Imprevistos:** Reserva para contingências
    - **Seguro:** Cobertura de riscos
    - **Garantia:** Custos de garantia e pós-venda
    """)
