import streamlit as st
import pandas as pd
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection

def show():
    """Exibe a página de gerenciamento de materiais"""
    
    st.markdown('<h1 class="section-title">🔧 Materiais</h1>', unsafe_allow_html=True)
    
    # Tabs para diferentes operações
    tab1, tab2, tab3 = st.tabs(["📋 Listar Materiais", "➕ Novo Material", "✏️ Editar Material"])
    
    with tab1:
        show_materiais_list()
    
    with tab2:
        show_novo_material()
    
    with tab3:
        show_editar_material()

def show_materiais_list():
    """Exibe a lista de materiais"""
    
    # Filtros
    col1, col2, col3 = st.columns(3)
    
    with col1:
        search_term = st.text_input("🔍 Buscar por nome ou marca:")
    
    with col2:
        sort_by = st.selectbox("Ordenar por:", ["Nome", "Marca", "Preço", "Estoque"])
    
    with col3:
        if st.button("🔄 Atualizar Lista"):
            st.rerun()
    
    # Buscar materiais
    conn = get_db_connection()
    
    query = "SELECT * FROM materiais"
    params = []
    
    if search_term:
        query += " WHERE nome LIKE  OR marca LIKE "
        params.extend([f"%{search_term}%", f"%{search_term}%"])
    
    if sort_by == "Nome":
        query += " ORDER BY nome"
    elif sort_by == "Marca":
        query += " ORDER BY marca, nome"
    elif sort_by == "Preço":
        query += " ORDER BY preco_unit DESC"
    else:
        query += " ORDER BY quantidade DESC"
    
    materiais_df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    if materiais_df.empty:
        st.info("Nenhum material encontrado.")
        return
    
    # Exibir estatísticas
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total de Materiais", len(materiais_df))
    
    with col2:
        total_estoque = materiais_df['quantidade'].sum()
        st.metric("Total em Estoque", total_estoque)
    
    with col3:
        valor_total_estoque = (materiais_df['quantidade'] * materiais_df['preco_unit']).sum()
        st.metric("Valor Total Estoque", f"R$ {valor_total_estoque:,.2f}")
    
    with col4:
        materiais_sem_estoque = len(materiais_df[materiais_df['quantidade'] == 0])
        st.metric("Sem Estoque", materiais_sem_estoque)
    
    st.markdown("---")
    
    # Alertas de estoque baixo
    estoque_baixo = materiais_df[materiais_df['quantidade'] <= 5]
    if not estoque_baixo.empty:
        st.warning(f"⚠️ {len(estoque_baixo)} material(is) com estoque baixo (≤ 5 unidades)")
        
        with st.expander("Ver Materiais com Estoque Baixo"):
            for _, material in estoque_baixo.iterrows():
                st.write(f"• {material['nome']} - {material['marca']}: {material['quantidade']} unidades")
    
    # Tabela de materiais
    st.markdown("### 📋 Lista de Materiais")
    
    # Configurar exibição da tabela
    display_columns = ['id', 'nome', 'marca', 'quantidade', 'preco_unit']
    column_names = ['ID', 'Nome', 'Marca', 'Estoque', 'Preço Unit.']
    
    # Adicionar coluna de valor total
    materiais_df['valor_total'] = materiais_df['quantidade'] * materiais_df['preco_unit']
    
    # Adicionar coluna de ações
    if not materiais_df.empty:
        materiais_df['Ações'] = 'Editar | Excluir'
    
    # Exibir tabela
    st.dataframe(
        materiais_df[display_columns + ['valor_total', 'Ações']] if not materiais_df.empty else pd.DataFrame(),
        column_config={
            'id': 'ID',
            'nome': 'Nome',
            'marca': 'Marca',
            'quantidade': st.column_config.NumberColumn('Estoque', format="%d"),
            'preco_unit': st.column_config.NumberColumn('Preço Unit.', format="R$ %.2f"),
            'valor_total': st.column_config.NumberColumn('Valor Total', format="R$ %.2f")
        },
        use_container_width=True,
        hide_index=True
    )
    
    # Botões de ação em massa
    if not materiais_df.empty:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📊 Relatório de Materiais"):
                generate_materiais_report(materiais_df)
        
        with col2:
            if st.button("📥 Exportar para Excel"):
                export_materiais_excel(materiais_df)
        
        with col3:
            if st.button("🗑️ Limpar Filtros"):
                st.rerun()

def show_novo_material():
    """Formulário para novo material"""
    
    st.markdown("### ➕ Cadastrar Novo Material")
    
    with st.form("novo_material_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            nome = st.text_input("Nome do Material *", placeholder="Ex: Cabo Elétrico")
            marca = st.text_input("Marca", placeholder="Ex: Tigre, Cobrecom")
            quantidade = st.number_input("Quantidade em Estoque", min_value=0, value=0)
        
        with col2:
            preco_unit = st.number_input("Preço Unitário (R$)", min_value=0.0, value=0.0, step=0.01, format="%.2f")
        
        # Validações
        if preco_unit > 0:
            valor_total_estoque = quantidade * preco_unit
            st.info(f"💰 Valor total do estoque: R$ {valor_total_estoque:,.2f}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            salvar = st.form_submit_button("💾 Salvar Material", type="primary")
        
        with col2:
            limpar = st.form_submit_button("🗑️ Limpar Formulário")
        
        if salvar:
            if not nome:
                st.error("Nome é obrigatório!")
            else:
                # Verificar se já existe material com mesmo nome e marca
                conn = get_db_connection()
                cursor = conn.cursor()
                
                cursor.execute("SELECT id FROM materiais WHERE nome =  AND marca = ", (nome, marca))
                if cursor.fetchone():
                    st.error("Material com mesmo nome e marca já cadastrado!")
                    conn.close()
                    return
                
                # Inserir material
                cursor.execute("""
                    INSERT INTO materiais (nome, marca, quantidade, preco_unit)
                    VALUES (, , , )
                """, (nome, marca, quantidade, preco_unit))
                
                conn.commit()
                conn.close()
                
                st.success(f"Material '{nome}' cadastrado com sucesso!")
                st.rerun()
        
        if limpar:
            st.rerun()

def show_editar_material():
    """Formulário para editar material"""
    
    st.markdown("### ✏️ Editar Material")
    
    # Selecionar material para editar
    conn = get_db_connection()
    materiais_df = pd.read_sql_query("SELECT id, nome, marca, quantidade FROM materiais ORDER BY nome", conn)
    conn.close()
    
    if materiais_df.empty:
        st.warning("Nenhum material cadastrado.")
        return
    
    material_options = {f"{row['nome']} - {row['marca']} (Estoque: {row['quantidade']})": row['id'] 
                     for _, row in materiais_df.iterrows()}
    
    material_selecionado = st.selectbox(
        "Selecionar Material para Editar:",
        options=[""] + list(material_options.keys())
    )
    
    if not material_selecionado:
        return
    
    material_id = material_options[material_selecionado]
    
    # Carregar dados do material
    conn = get_db_connection()
    material_data = pd.read_sql_query(f"SELECT * FROM materiais WHERE id = {material_id}", conn).iloc[0]
    conn.close()
    
    # Formulário de edição
    with st.form("editar_material_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            nome = st.text_input("Nome do Material *", value=material_data['nome'])
            marca = st.text_input("Marca", value=material_data['marca'] or "")
            quantidade = st.number_input("Quantidade em Estoque", min_value=0, value=material_data['quantidade'])
        
        with col2:
            preco_unit = st.number_input("Preço Unitário (R$)", min_value=0.0, value=float(material_data['preco_unit']), 
                                       step=0.01, format="%.2f")
        
        # Validações
        if preco_unit > 0:
            valor_total_estoque = quantidade * preco_unit
            st.info(f"💰 Valor total do estoque: R$ {valor_total_estoque:,.2f}")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            salvar = st.form_submit_button("💾 Salvar Alterações", type="primary")
        
        with col2:
            excluir = st.form_submit_button("🗑️ Excluir Material", type="secondary")
        
        with col3:
            cancelar = st.form_submit_button("❌ Cancelar")
        
        if salvar:
            if not nome:
                st.error("Nome é obrigatório!")
            else:
                # Verificar se já existe material com mesmo nome e marca (exceto o próprio)
                conn = get_db_connection()
                cursor = conn.cursor()
                
                cursor.execute("SELECT id FROM materiais WHERE nome =  AND marca =  AND id != ", 
                             (nome, marca, material_id))
                if cursor.fetchone():
                    st.error("Material com mesmo nome e marca já cadastrado!")
                    conn.close()
                    return
                
                # Atualizar material
                cursor.execute("""
                    UPDATE materiais 
                    SET nome = , marca = , quantidade = , preco_unit = 
                    WHERE id = 
                """, (nome, marca, quantidade, preco_unit, material_id))
                
                conn.commit()
                conn.close()
                
                st.success(f"Material '{nome}' atualizado com sucesso!")
                st.rerun()
        
        if excluir:
            # Verificar se o material é usado em ordens de serviço
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM itens_material WHERE material_id = ", (material_id,))
            count_uso = cursor.fetchone()[0]
            
            if count_uso > 0:
                st.error(f"Não é possível excluir o material pois ele é usado em {count_uso} ordem(ns) de serviço.")
            else:
                # Excluir material
                cursor.execute("DELETE FROM materiais WHERE id = ", (material_id,))
                conn.commit()
                conn.close()
                
                st.success(f"Material '{nome}' excluído com sucesso!")
                st.rerun()
        
        if cancelar:
            st.rerun()

def generate_materiais_report(materiais_df):
    """Gera relatório dos materiais"""
    
    st.markdown("### 📊 Relatório de Materiais")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("Total de Materiais", len(materiais_df))
        st.metric("Total em Estoque", materiais_df['quantidade'].sum())
        st.metric("Valor Total Estoque", f"R$ {(materiais_df['quantidade'] * materiais_df['preco_unit']).sum():,.2f}")
    
    with col2:
        st.metric("Sem Estoque", len(materiais_df[materiais_df['quantidade'] == 0]))
        st.metric("Estoque Baixo (≤5)", len(materiais_df[materiais_df['quantidade'] <= 5]))
        st.metric("Preço Médio", f"R$ {materiais_df['preco_unit'].mean():.2f}")
    
    # Gráficos
    import plotly.express as px
    
    # Top 10 materiais por valor
    top_valor = materiais_df.nlargest(10, 'valor_total')
    
    fig1 = px.bar(
        top_valor,
        x='nome',
        y='valor_total',
        title="Top 10 Materiais por Valor Total",
        color='valor_total',
        color_continuous_scale='Blues'
    )
    fig1.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig1, use_container_width=True)
    
    # Distribuição de estoque
    estoque_status = {
        'Sem Estoque': len(materiais_df[materiais_df['quantidade'] == 0]),
        'Estoque Baixo (1-5)': len(materiais_df[(materiais_df['quantidade'] >= 1) & (materiais_df['quantidade'] <= 5)]),
        'Estoque Normal (>5)': len(materiais_df[materiais_df['quantidade'] > 5])
    }
    
    fig2 = px.pie(
        values=list(estoque_status.values()),
        names=list(estoque_status.keys()),
        title="Distribuição do Estoque",
        color_discrete_sequence=['#DC3545', '#FFC107', '#28A745']
    )
    st.plotly_chart(fig2, use_container_width=True)

def export_materiais_excel(materiais_df):
    """Exporta materiais para Excel"""
    
    # Preparar dados para exportação
    export_df = materiais_df[['nome', 'marca', 'quantidade', 'preco_unit']].copy()
    export_df['valor_total'] = export_df['quantidade'] * export_df['preco_unit']
    export_df.columns = ['Nome', 'Marca', 'Estoque', 'Preço Unitário', 'Valor Total']
    
    # Converter para Excel
    import io
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        export_df.to_excel(writer, sheet_name='Materiais', index=False)
    
    # Download
    st.download_button(
        label="📥 Baixar Arquivo Excel",
        data=output.getvalue(),
        file_name=f"materiais_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
