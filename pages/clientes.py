import streamlit as st
import pandas as pd
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection

def show():
    """Exibe a página de gerenciamento de clientes"""
    
    st.markdown('<h1 class="section-title">👥 Clientes</h1>', unsafe_allow_html=True)
    
    # Tabs para diferentes operações
    tab1, tab2, tab3 = st.tabs(["📋 Listar Clientes", "➕ Novo Cliente", "✏️ Editar Cliente"])
    
    with tab1:
        show_clientes_list()
    
    with tab2:
        show_novo_cliente()
    
    with tab3:
        show_editar_cliente()

def show_clientes_list():
    """Exibe a lista de clientes"""
    
    # Filtros
    col1, col2, col3 = st.columns(3)
    
    with col1:
        search_term = st.text_input("🔍 Buscar por nome ou CNPJ/CPF:")
    
    with col2:
        sort_by = st.selectbox("Ordenar por:", ["Nome", "CNPJ/CPF", "Data de Cadastro"])
    
    with col3:
        if st.button("🔄 Atualizar Lista"):
            st.rerun()
    
    # Buscar clientes
    conn = get_db_connection()
    
    query = "SELECT * FROM clientes"
    params = []
    
    if search_term:
        query += " WHERE nome LIKE  OR cnpj_cpf LIKE "
        params.extend([f"%{search_term}%", f"%{search_term}%"])
    
    if sort_by == "Nome":
        query += " ORDER BY nome"
    elif sort_by == "CNPJ/CPF":
        query += " ORDER BY cnpj_cpf"
    else:
        query += " ORDER BY id DESC"
    
    clientes_df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    if clientes_df.empty:
        st.info("Nenhum cliente encontrado.")
        return
    
    # Exibir estatísticas
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total de Clientes", len(clientes_df))
    
    with col2:
        clientes_com_email = len(clientes_df[clientes_df['email'].notna() & (clientes_df['email'] != '')])
        st.metric("Com E-mail", clientes_com_email)
    
    with col3:
        clientes_com_cnpj = len(clientes_df[clientes_df['cnpj_cpf'].notna() & (clientes_df['cnpj_cpf'] != '')])
        st.metric("Com CNPJ/CPF", clientes_com_cnpj)
    
    st.markdown("---")
    
    # Tabela de clientes
    st.markdown("### 📋 Lista de Clientes")
    
    # Configurar exibição da tabela
    display_columns = ['id', 'nome', 'cnpj_cpf', 'telefone', 'email']
    column_names = ['ID', 'Nome/Razão Social', 'CNPJ/CPF', 'Telefone', 'E-mail']
    
    # Adicionar coluna de ações
    if not clientes_df.empty:
        clientes_df['Ações'] = 'Editar | Excluir'
    
    # Exibir tabela
    st.dataframe(
        clientes_df[display_columns + ['Ações']] if not clientes_df.empty else pd.DataFrame(),
        column_config={
            'id': 'ID',
            'nome': 'Nome/Razão Social',
            'cnpj_cpf': 'CNPJ/CPF',
            'telefone': 'Telefone',
            'email': 'E-mail'
        },
        use_container_width=True,
        hide_index=True
    )
    
    # Botões de ação em massa
    if not clientes_df.empty:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📊 Relatório de Clientes"):
                generate_clientes_report(clientes_df)
        
        with col2:
            if st.button("📥 Exportar para Excel"):
                export_clientes_excel(clientes_df)
        
        with col3:
            if st.button("🗑️ Limpar Filtros"):
                st.rerun()

def show_novo_cliente():
    """Formulário para novo cliente"""
    
    st.markdown("### ➕ Cadastrar Novo Cliente")
    
    with st.form("novo_cliente_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            nome = st.text_input("Nome/Razão Social *", placeholder="Digite o nome completo")
            cnpj_cpf = st.text_input("CNPJ/CPF", placeholder="00.000.000/0000-00 ou 000.000.000-00")
            telefone = st.text_input("Telefone", placeholder="(11) 99999-9999")
        
        with col2:
            email = st.text_input("E-mail", placeholder="cliente@email.com")
            endereco = st.text_area("Endereço", placeholder="Rua, Número, Bairro, Cidade, Estado, CEP")
        
        col1, col2 = st.columns(2)
        
        with col1:
            salvar = st.form_submit_button("💾 Salvar Cliente", type="primary")
        
        with col2:
            limpar = st.form_submit_button("🗑️ Limpar Formulário")
        
        if salvar:
            if not nome:
                st.error("Nome é obrigatório!")
            else:
                # Validar CNPJ/CPF único
                conn = get_db_connection()
                cursor = conn.cursor()
                
                if cnpj_cpf:
                    cursor.execute("SELECT id FROM clientes WHERE cnpj_cpf = ", (cnpj_cpf,))
                    if cursor.fetchone():
                        st.error("CNPJ/CPF já cadastrado!")
                        conn.close()
                        return
                
                # Inserir cliente
                cursor.execute("""
                    INSERT INTO clientes (nome, cnpj_cpf, endereco, telefone, email)
                    VALUES (, , , , )
                """, (nome, cnpj_cpf, endereco, telefone, email))
                
                conn.commit()
                conn.close()
                
                st.success(f"Cliente '{nome}' cadastrado com sucesso!")
                st.rerun()
        
        if limpar:
            st.rerun()

def show_editar_cliente():
    """Formulário para editar cliente"""
    
    st.markdown("### ✏️ Editar Cliente")
    
    # Selecionar cliente para editar
    conn = get_db_connection()
    clientes_df = pd.read_sql_query("SELECT id, nome, cnpj_cpf FROM clientes ORDER BY nome", conn)
    conn.close()
    
    if clientes_df.empty:
        st.warning("Nenhum cliente cadastrado.")
        return
    
    cliente_options = {f"{row['nome']} - {row['cnpj_cpf']}": row['id'] 
                     for _, row in clientes_df.iterrows()}
    
    cliente_selecionado = st.selectbox(
        "Selecionar Cliente para Editar:",
        options=[""] + list(cliente_options.keys())
    )
    
    if not cliente_selecionado:
        return
    
    cliente_id = cliente_options[cliente_selecionado]
    
    # Carregar dados do cliente
    conn = get_db_connection()
    cliente_data = pd.read_sql_query(f"SELECT * FROM clientes WHERE id = {cliente_id}", conn).iloc[0]
    conn.close()
    
    # Formulário de edição
    with st.form("editar_cliente_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            nome = st.text_input("Nome/Razão Social *", value=cliente_data['nome'])
            cnpj_cpf = st.text_input("CNPJ/CPF", value=cliente_data['cnpj_cpf'] or "")
            telefone = st.text_input("Telefone", value=cliente_data['telefone'] or "")
        
        with col2:
            email = st.text_input("E-mail", value=cliente_data['email'] or "")
            endereco = st.text_area("Endereço", value=cliente_data['endereco'] or "")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            salvar = st.form_submit_button("💾 Salvar Alterações", type="primary")
        
        with col2:
            excluir = st.form_submit_button("🗑️ Excluir Cliente", type="secondary")
        
        with col3:
            cancelar = st.form_submit_button("❌ Cancelar")
        
        if salvar:
            if not nome:
                st.error("Nome é obrigatório!")
            else:
                # Validar CNPJ/CPF único (exceto para o próprio cliente)
                conn = get_db_connection()
                cursor = conn.cursor()
                
                if cnpj_cpf:
                    cursor.execute("SELECT id FROM clientes WHERE cnpj_cpf =  AND id != ", (cnpj_cpf, cliente_id))
                    if cursor.fetchone():
                        st.error("CNPJ/CPF já cadastrado para outro cliente!")
                        conn.close()
                        return
                
                # Atualizar cliente
                cursor.execute("""
                    UPDATE clientes 
                    SET nome = , cnpj_cpf = , endereco = , telefone = , email = 
                    WHERE id = 
                """, (nome, cnpj_cpf, endereco, telefone, email, cliente_id))
                
                conn.commit()
                conn.close()
                
                st.success(f"Cliente '{nome}' atualizado com sucesso!")
                st.rerun()
        
        if excluir:
            # Verificar se o cliente tem ordens de serviço
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM ordens_servico WHERE cliente_id = ", (cliente_id,))
            count_os = cursor.fetchone()[0]
            
            if count_os > 0:
                st.error(f"Não é possível excluir o cliente pois ele possui {count_os} ordem(ns) de serviço associada(s).")
            else:
                # Excluir cliente
                cursor.execute("DELETE FROM clientes WHERE id = ", (cliente_id,))
                conn.commit()
                conn.close()
                
                st.success(f"Cliente '{nome}' excluído com sucesso!")
                st.rerun()
        
        if cancelar:
            st.rerun()

def generate_clientes_report(clientes_df):
    """Gera relatório dos clientes"""
    
    st.markdown("### 📊 Relatório de Clientes")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("Total de Clientes", len(clientes_df))
        st.metric("Com E-mail", len(clientes_df[clientes_df['email'].notna() & (clientes_df['email'] != '')]))
    
    with col2:
        st.metric("Com CNPJ/CPF", len(clientes_df[clientes_df['cnpj_cpf'].notna() & (clientes_df['cnpj_cpf'] != '')]))
        st.metric("Com Telefone", len(clientes_df[clientes_df['telefone'].notna() & (clientes_df['telefone'] != '')]))
    
    # Gráfico de distribuição
    import plotly.express as px
    
    # Clientes por status de dados
    status_data = {
        'Completo': len(clientes_df[
            (clientes_df['nome'].notna()) & 
            (clientes_df['cnpj_cpf'].notna()) & 
            (clientes_df['telefone'].notna()) & 
            (clientes_df['email'].notna())
        ]),
        'Parcial': len(clientes_df) - len(clientes_df[
            (clientes_df['nome'].notna()) & 
            (clientes_df['cnpj_cpf'].notna()) & 
            (clientes_df['telefone'].notna()) & 
            (clientes_df['email'].notna())
        ])
    }
    
    fig = px.pie(
        values=list(status_data.values()),
        names=list(status_data.keys()),
        title="Distribuição de Dados dos Clientes",
        color_discrete_sequence=['#004A8D', '#002B5B']
    )
    
    st.plotly_chart(fig, use_container_width=True)

def export_clientes_excel(clientes_df):
    """Exporta clientes para Excel"""
    
    # Preparar dados para exportação
    export_df = clientes_df[['nome', 'cnpj_cpf', 'endereco', 'telefone', 'email']].copy()
    export_df.columns = ['Nome/Razão Social', 'CNPJ/CPF', 'Endereço', 'Telefone', 'E-mail']
    
    # Converter para Excel
    import io
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        export_df.to_excel(writer, sheet_name='Clientes', index=False)
    
    # Download
    st.download_button(
        label="📥 Baixar Arquivo Excel",
        data=output.getvalue(),
        file_name=f"clientes_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
