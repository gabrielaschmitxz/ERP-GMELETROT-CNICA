import streamlit as st
import pandas as pd
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection

def show():
    """Exibe a página de gerenciamento de serviços"""
    
    st.markdown('<h1 class="section-title">⚡ Serviços</h1>', unsafe_allow_html=True)
    
    # Tabs para diferentes operações
    tab1, tab2, tab3 = st.tabs(["📋 Listar Serviços", "➕ Novo Serviço", "✏️ Editar Serviço"])
    
    with tab1:
        show_servicos_list()
    
    with tab2:
        show_novo_servico()
    
    with tab3:
        show_editar_servico()

def show_servicos_list():
    """Exibe a lista de serviços"""
    
    # Filtros
    col1, col2, col3 = st.columns(3)
    
    with col1:
        search_term = st.text_input("🔍 Buscar por nome do serviço:")
    
    with col2:
        sort_by = st.selectbox("Ordenar por:", ["Nome", "Preço", "Tempo"])
    
    with col3:
        if st.button("🔄 Atualizar Lista"):
            st.rerun()
    
    # Buscar serviços
    conn = get_db_connection()
    
    query = "SELECT * FROM servicos"
    params = []
    
    if search_term:
        query += " WHERE nome LIKE "
        params.append(f"%{search_term}%")
    
    if sort_by == "Nome":
        query += " ORDER BY nome"
    elif sort_by == "Preço":
        query += " ORDER BY preco_unit DESC"
    else:
        query += " ORDER BY tempo_h DESC"
    
    servicos_df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    if servicos_df.empty:
        st.info("Nenhum serviço encontrado.")
        return
    
    # Exibir estatísticas
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total de Serviços", len(servicos_df))
    
    with col2:
        preco_medio = servicos_df['preco_unit'].mean()
        st.metric("Preço Médio", f"R$ {preco_medio:.2f}")
    
    with col3:
        preco_min = servicos_df['preco_unit'].min()
        st.metric("Preço Mínimo", f"R$ {preco_min:.2f}")
    
    with col4:
        preco_max = servicos_df['preco_unit'].max()
        st.metric("Preço Máximo", f"R$ {preco_max:.2f}")
    
    st.markdown("---")
    
    # Tabela de serviços
    st.markdown("### 📋 Lista de Serviços")
    
    # Configurar exibição da tabela
    display_columns = ['id', 'nome', 'preco_unit', 'tempo_h']
    column_names = ['ID', 'Nome do Serviço', 'Preço Unit.', 'Tempo (h)']
    
    # Adicionar coluna de ações
    if not servicos_df.empty:
        servicos_df['Ações'] = 'Editar | Excluir'
    
    # Exibir tabela
    st.dataframe(
        servicos_df[display_columns + ['Ações']] if not servicos_df.empty else pd.DataFrame(),
        column_config={
            'id': 'ID',
            'nome': 'Nome do Serviço',
            'preco_unit': st.column_config.NumberColumn('Preço Unit.', format="R$ %.2f"),
            'tempo_h': st.column_config.NumberColumn('Tempo (h)', format="%.1f")
        },
        use_container_width=True,
        hide_index=True
    )
    
    # Botões de ação em massa
    if not servicos_df.empty:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📊 Relatório de Serviços"):
                generate_servicos_report(servicos_df)
        
        with col2:
            if st.button("📥 Exportar para Excel"):
                export_servicos_excel(servicos_df)
        
        with col3:
            if st.button("🗑️ Limpar Filtros"):
                st.rerun()

def show_novo_servico():
    """Formulário para novo serviço"""
    
    st.markdown("### ➕ Cadastrar Novo Serviço")
    
    with st.form("novo_servico_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            nome = st.text_input("Nome do Serviço *", placeholder="Ex: Instalação de Tomada")
            preco_unit = st.number_input("Preço Unitário (R$)", min_value=0.0, value=0.0, step=0.01, format="%.2f")
        
        with col2:
            tempo_h = st.number_input("Tempo de Produção (horas)", min_value=0.0, value=0.0, step=0.1, format="%.1f")
        
        # Informações adicionais
        if preco_unit > 0 and tempo_h > 0:
            valor_hora = preco_unit / tempo_h
            st.info(f"💰 Valor por hora: R$ {valor_hora:.2f}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            salvar = st.form_submit_button("💾 Salvar Serviço", type="primary")
        
        with col2:
            limpar = st.form_submit_button("🗑️ Limpar Formulário")
        
        if salvar:
            if not nome:
                st.error("Nome é obrigatório!")
            else:
                # Verificar se já existe serviço com mesmo nome
                conn = get_db_connection()
                cursor = conn.cursor()
                
                cursor.execute("SELECT id FROM servicos WHERE nome = ", (nome,))
                if cursor.fetchone():
                    st.error("Serviço com mesmo nome já cadastrado!")
                    conn.close()
                    return
                
                # Inserir serviço
                cursor.execute("""
                    INSERT INTO servicos (nome, preco_unit, tempo_h)
                    VALUES (, , )
                """, (nome, preco_unit, tempo_h))
                
                conn.commit()
                conn.close()
                
                st.success(f"Serviço '{nome}' cadastrado com sucesso!")
                st.rerun()
        
        if limpar:
            st.rerun()

def show_editar_servico():
    """Formulário para editar serviço"""
    
    st.markdown("### ✏️ Editar Serviço")
    
    # Selecionar serviço para editar
    conn = get_db_connection()
    servicos_df = pd.read_sql_query("SELECT id, nome, preco_unit FROM servicos ORDER BY nome", conn)
    conn.close()
    
    if servicos_df.empty:
        st.warning("Nenhum serviço cadastrado.")
        return
    
    servico_options = {f"{row['nome']} - R$ {row['preco_unit']:.2f}": row['id'] 
                     for _, row in servicos_df.iterrows()}
    
    servico_selecionado = st.selectbox(
        "Selecionar Serviço para Editar:",
        options=[""] + list(servico_options.keys())
    )
    
    if not servico_selecionado:
        return
    
    servico_id = servico_options[servico_selecionado]
    
    # Carregar dados do serviço
    conn = get_db_connection()
    servico_data = pd.read_sql_query(f"SELECT * FROM servicos WHERE id = {servico_id}", conn).iloc[0]
    conn.close()
    
    # Formulário de edição
    with st.form("editar_servico_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            nome = st.text_input("Nome do Serviço *", value=servico_data['nome'])
            preco_unit = st.number_input("Preço Unitário (R$)", min_value=0.0, value=float(servico_data['preco_unit']), 
                                       step=0.01, format="%.2f")
        
        with col2:
            tempo_h = st.number_input("Tempo de Produção (horas)", min_value=0.0, value=float(servico_data['tempo_h']), 
                                    step=0.1, format="%.1f")
        
        # Informações adicionais
        if preco_unit > 0 and tempo_h > 0:
            valor_hora = preco_unit / tempo_h
            st.info(f"💰 Valor por hora: R$ {valor_hora:.2f}")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            salvar = st.form_submit_button("💾 Salvar Alterações", type="primary")
        
        with col2:
            excluir = st.form_submit_button("🗑️ Excluir Serviço", type="secondary")
        
        with col3:
            cancelar = st.form_submit_button("❌ Cancelar")
        
        if salvar:
            if not nome:
                st.error("Nome é obrigatório!")
            else:
                # Verificar se já existe serviço com mesmo nome (exceto o próprio)
                conn = get_db_connection()
                cursor = conn.cursor()
                
                cursor.execute("SELECT id FROM servicos WHERE nome =  AND id != ", (nome, servico_id))
                if cursor.fetchone():
                    st.error("Serviço com mesmo nome já cadastrado!")
                    conn.close()
                    return
                
                # Atualizar serviço
                cursor.execute("""
                    UPDATE servicos 
                    SET nome = , preco_unit = , tempo_h = 
                    WHERE id = 
                """, (nome, preco_unit, tempo_h, servico_id))
                
                conn.commit()
                conn.close()
                
                st.success(f"Serviço '{nome}' atualizado com sucesso!")
                st.rerun()
        
        if excluir:
            # Verificar se o serviço é usado em ordens de serviço
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM itens_servico WHERE servico_id = ", (servico_id,))
            count_uso = cursor.fetchone()[0]
            
            if count_uso > 0:
                st.error(f"Não é possível excluir o serviço pois ele é usado em {count_uso} ordem(ns) de serviço.")
            else:
                # Excluir serviço
                cursor.execute("DELETE FROM servicos WHERE id = ", (servico_id,))
                conn.commit()
                conn.close()
                
                st.success(f"Serviço '{nome}' excluído com sucesso!")
                st.rerun()
        
        if cancelar:
            st.rerun()

def generate_servicos_report(servicos_df):
    """Gera relatório dos serviços"""
    
    st.markdown("### 📊 Relatório de Serviços")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("Total de Serviços", len(servicos_df))
        st.metric("Preço Médio", f"R$ {servicos_df['preco_unit'].mean():.2f}")
        st.metric("Tempo Médio", f"{servicos_df['tempo_h'].mean():.1f} horas")
    
    with col2:
        st.metric("Preço Mínimo", f"R$ {servicos_df['preco_unit'].min():.2f}")
        st.metric("Preço Máximo", f"R$ {servicos_df['preco_unit'].max():.2f}")
        st.metric("Tempo Total", f"{servicos_df['tempo_h'].sum():.1f} horas")
    
    # Gráficos
    import plotly.express as px
    
    # Distribuição de preços
    fig1 = px.histogram(
        servicos_df,
        x='preco_unit',
        title="Distribuição de Preços dos Serviços",
        nbins=10,
        color_discrete_sequence=['#004A8D']
    )
    fig1.update_layout(xaxis_title="Preço (R$)", yaxis_title="Quantidade")
    st.plotly_chart(fig1, use_container_width=True)
    
    # Top 10 serviços por preço
    top_preco = servicos_df.nlargest(10, 'preco_unit')
    
    fig2 = px.bar(
        top_preco,
        x='nome',
        y='preco_unit',
        title="Top 10 Serviços por Preço",
        color='preco_unit',
        color_continuous_scale='Blues'
    )
    fig2.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig2, use_container_width=True)
    
    # Relação preço vs tempo
    fig3 = px.scatter(
        servicos_df,
        x='tempo_h',
        y='preco_unit',
        title="Relação entre Tempo e Preço",
        hover_data=['nome'],
        color='preco_unit',
        color_continuous_scale='Blues'
    )
    fig3.update_layout(xaxis_title="Tempo (horas)", yaxis_title="Preço (R$)")
    st.plotly_chart(fig3, use_container_width=True)

def export_servicos_excel(servicos_df):
    """Exporta serviços para Excel"""
    
    # Preparar dados para exportação
    export_df = servicos_df[['nome', 'preco_unit', 'tempo_h']].copy()
    export_df['valor_hora'] = export_df['preco_unit'] / export_df['tempo_h']
    export_df.columns = ['Nome do Serviço', 'Preço Unitário', 'Tempo (horas)', 'Valor por Hora']
    
    # Converter para Excel
    import io
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        export_df.to_excel(writer, sheet_name='Serviços', index=False)
    
    # Download
    st.download_button(
        label="📥 Baixar Arquivo Excel",
        data=output.getvalue(),
        file_name=f"servicos_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
