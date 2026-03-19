import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection

def show():
    """Exibe o painel financeiro de atendimentos"""
    
    st.markdown('<h1 class="section-title">📊 Painel Financeiro de Atendimentos</h1>', unsafe_allow_html=True)
    
    # Tabs para diferentes visualizações
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Ordens de Serviço", "👥 Análise por Cliente", "💰 Estratificação de Lucro", "📈 Relatórios"])
    
    with tab1:
        show_ordens_servico()
    
    with tab2:
        show_analise_cliente()
    
    with tab3:
        show_estratificacao_lucro()
    
    with tab4:
        show_relatorios()

def show_ordens_servico():
    """Exibe lista de ordens de serviço"""
    
    # Filtros
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        cliente_filter = st.selectbox("Filtrar por Cliente:", ["Todos"] + get_clientes_list())
    
    with col2:
        status_filter = st.selectbox("Filtrar por Status:", ["Todos", "Nova", "Em Andamento", "Aguardando Pagamento", "Paga"])
    
    with col3:
        data_inicio = st.date_input("Data Início:", value=datetime.now() - timedelta(days=30))
    
    with col4:
        data_fim = st.date_input("Data Fim:", value=datetime.now())
    
    # Buscar ordens de serviço
    conn = get_db_connection()
    
    query = """
        SELECT os.*, c.nome as cliente_nome, fp.nome as forma_pagamento_nome
        FROM ordens_servico os
        JOIN clientes c ON os.cliente_id = c.id
        LEFT JOIN formas_pagamento fp ON os.forma_pagamento_id = fp.id
        WHERE os.data BETWEEN  AND 
    """
    params = [data_inicio.strftime('%Y-%m-%d'), data_fim.strftime('%Y-%m-%d')]
    
    if cliente_filter != "Todos":
        query += " AND c.nome = "
        params.append(cliente_filter)
    
    if status_filter != "Todos":
        query += " AND os.status = "
        params.append(status_filter)
    
    query += " ORDER BY os.data DESC"
    
    ordens_df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    if ordens_df.empty:
        st.info("Nenhuma ordem de serviço encontrada no período selecionado.")
        return
    
    # Estatísticas gerais
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total de OS", len(ordens_df))
    
    with col2:
        total_faturado = ordens_df['total'].sum()
        st.metric("Total Faturado", f"R$ {total_faturado:,.2f}")
    
    with col3:
        os_pagas = ordens_df[ordens_df['status'] == 'Paga']
        st.metric("OS Pagas", len(os_pagas))
    
    with col4:
        total_pago = os_pagas['total'].sum()
        st.metric("Total Pago", f"R$ {total_pago:,.2f}")
    
    st.markdown("---")
    
    # Tabela de ordens de serviço
    st.markdown("### 📋 Ordens de Serviço")
    
    # Exibir cada ordem com ações
    for _, ordem in ordens_df.iterrows():
        with st.expander(f"OS #{ordem['id']} - {ordem['cliente_nome']} - R$ {ordem['total']:.2f} - {ordem['status']}"):
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.write(f"**Cliente:** {ordem['cliente_nome']}")
                st.write(f"**Data:** {ordem['data'].strftime('%d/%m/%Y')}")
            
            with col2:
                st.write(f"**Forma Pagamento:** {ordem['forma_pagamento_nome']}")
                st.write(f"**Valor Total:** R$ {ordem['total']:.2f}")
            
            with col3:
                # Mudança de status
                st.write("**Alterar Status:**")
                novo_status = st.selectbox(
                    "Status:",
                    ["Em Andamento", "Aguardando Pagamento", "Paga"],
                    index=["Em Andamento", "Aguardando Pagamento", "Paga"].index(ordem['status']) if ordem['status'] in ["Em Andamento", "Aguardando Pagamento", "Paga"] else 0,
                    key=f"status_{ordem['id']}"
                )
                
                if st.button("🔄 Atualizar Status", key=f"update_status_{ordem['id']}"):
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE ordens_servico SET status = %s WHERE id = %s", (novo_status, ordem['id']))
                    conn.commit()
                    conn.close()
                    st.success(f"Status da OS #{ordem['id']} atualizado para '{novo_status}'!")
                    st.rerun()
            
            with col4:
                # Botões de ação
                col_btn1, col_btn2 = st.columns(2)
                
                with col_btn1:
                    if st.button("📄 Gerar PDF", key=f"pdf_{ordem['id']}"):
                        generate_order_pdf(ordem['id'])
                
                with col_btn2:
                    if st.button("💰 Custos", key=f"custos_{ordem['id']}"):
                        st.session_state[f"show_custos_{ordem['id']}"] = True
            
            # Modal para inserir custos
            if st.session_state.get(f"show_custos_{ordem['id']}", False):
                st.markdown("---")
                st.markdown("#### 💰 Inserir Custos para Cálculo de Lucratividade")
                
                with st.form(f"custos_form_{ordem['id']}"):
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        custo_materiais = st.number_input("Custo de Materiais (R$):", min_value=0.0, value=0.0, key=f"custo_mat_{ordem['id']}")
                    
                    with col2:
                        custo_servicos = st.number_input("Custo de Serviços (R$):", min_value=0.0, value=0.0, key=f"custo_serv_{ordem['id']}")
                    
                    with col3:
                        custo_deslocamento = st.number_input("Custo de Deslocamento (R$):", min_value=0.0, value=0.0, key=f"custo_desl_{ordem['id']}")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if st.form_submit_button("💾 Salvar Custos"):
                            # Salvar custos no banco (criar tabela se necessário)
                            conn = get_db_connection()
                            cursor = conn.cursor()
                            
                            # Verificar se já existe registro de custos para esta OS
                            cursor.execute("SELECT id FROM custos_ordem WHERE ordem_id = %s", (ordem['id'],))
                            if cursor.fetchone():
                                cursor.execute("""
                                    UPDATE custos_ordem 
                                    SET custo_materiais = %s, custo_servicos = %s, custo_deslocamento = %s
                                    WHERE ordem_id = %s
                                """, (custo_materiais, custo_servicos, custo_deslocamento, ordem['id']))
                            else:
                                cursor.execute("""
                                    INSERT INTO custos_ordem (ordem_id, custo_materiais, custo_servicos, custo_deslocamento)
                                    VALUES (%s, %s, %s, %s)
                                """, (ordem['id'], custo_materiais, custo_servicos, custo_deslocamento))
                            
                            conn.commit()
                            conn.close()
                            st.success("Custos salvos com sucesso!")
                            st.session_state[f"show_custos_{ordem['id']}"] = False
                            st.rerun()
                    
                    with col2:
                        if st.form_submit_button("❌ Cancelar"):
                            st.session_state[f"show_custos_{ordem['id']}"] = False
                            st.rerun()
    
    # Gráficos
    col1, col2 = st.columns(2)
    
    with col1:
        # Gráfico de status
        status_counts = ordens_df['status'].value_counts()
        fig1 = px.pie(
            values=status_counts.values,
            names=status_counts.index,
            title="Distribuição por Status",
            color_discrete_sequence=['#004A8D', '#28A745', '#FFC107', '#DC3545']
        )
        st.plotly_chart(fig1, use_container_width=True)
    
    with col2:
        # Gráfico de formas de pagamento
        fp_counts = ordens_df['forma_pagamento_nome'].value_counts()
        fig2 = px.bar(
            x=fp_counts.index,
            y=fp_counts.values,
            title="Formas de Pagamento",
            color=fp_counts.values,
            color_continuous_scale='Blues'
        )
        st.plotly_chart(fig2, use_container_width=True)

def show_analise_cliente():
    """Exibe análise por cliente"""
    
    # Buscar dados dos clientes
    conn = get_db_connection()
    
    query = """
        SELECT 
            c.id,
            c.nome,
            COUNT(os.id) as total_os,
            SUM(os.total) as total_contratado,
            SUM(CASE WHEN os.status = 'Paga' THEN os.total ELSE 0 END) as total_pago,
            SUM(CASE WHEN os.status != 'Paga' THEN os.total ELSE 0 END) as total_aberto
        FROM clientes c
        LEFT JOIN ordens_servico os ON c.id = os.cliente_id
        GROUP BY c.id, c.nome
        HAVING total_os > 0
        ORDER BY total_contratado DESC
    """
    
    clientes_df = pd.read_sql_query(query, conn)
    conn.close()
    
    if clientes_df.empty:
        st.info("Nenhum cliente com ordens de serviço encontrado.")
        return
    
    # Estatísticas gerais
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Clientes Ativos", len(clientes_df))
    
    with col2:
        total_contratado = clientes_df['total_contratado'].sum()
        st.metric("Total Contratado", f"R$ {total_contratado:,.2f}")
    
    with col3:
        total_pago = clientes_df['total_pago'].sum()
        st.metric("Total Pago", f"R$ {total_pago:,.2f}")
    
    st.markdown("---")
    
    # Tabela de clientes
    st.markdown("### 👥 Resumo por Cliente")
    
    st.dataframe(
        clientes_df,
        column_config={
            'id': 'ID',
            'nome': 'Cliente',
            'total_os': 'Total OS',
            'total_contratado': st.column_config.NumberColumn('Total Contratado', format="R$ %.2f"),
            'total_pago': st.column_config.NumberColumn('Total Pago', format="R$ %.2f"),
            'total_aberto': st.column_config.NumberColumn('Total em Aberto', format="R$ %.2f")
        },
        use_container_width=True,
        hide_index=True
    )
    
    # Gráficos
    col1, col2 = st.columns(2)
    
    with col1:
        # Top 10 clientes por valor
        top_clientes = clientes_df.head(10)
        fig1 = px.bar(
            top_clientes,
            x='nome',
            y='total_contratado',
            title="Top 10 Clientes por Valor Contratado",
            color='total_contratado',
            color_continuous_scale='Blues'
        )
        fig1.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig1, use_container_width=True)
    
    with col2:
        # Distribuição de pagamentos
        fig2 = px.scatter(
            clientes_df,
            x='total_contratado',
            y='total_pago',
            size='total_os',
            hover_data=['nome'],
            title="Relação Contratado vs Pago",
            color='total_os',
            color_continuous_scale='Blues'
        )
        fig2.update_layout(xaxis_title="Total Contratado", yaxis_title="Total Pago")
        st.plotly_chart(fig2, use_container_width=True)

def show_estratificacao_lucro():
    """Exibe estratificação de lucro"""
    
    st.markdown("### 💰 Estratificação de Lucro")
    
    # Configurações de margem
    col1, col2 = st.columns(2)
    
    with col1:
        margem_lucro = st.slider("Margem de Lucro Fixa (%)", 0, 100, 60)
    
    with col2:
        periodo_analise = st.selectbox("Período de Análise:", ["Últimos 30 dias", "Últimos 90 dias", "Último ano", "Todos"])
    
    # Buscar dados para análise
    conn = get_db_connection()
    
    # Definir período
    if periodo_analise == "Últimos 30 dias":
        data_inicio = datetime.now() - timedelta(days=30)
    elif periodo_analise == "Últimos 90 dias":
        data_inicio = datetime.now() - timedelta(days=90)
    elif periodo_analise == "Último ano":
        data_inicio = datetime.now() - timedelta(days=365)
    else:
        data_inicio = datetime(2020, 1, 1)
    
    # Query para análise de lucro
    query = """
        SELECT 
            os.id,
            os.data,
            os.total as receita_bruta,
            COALESCE(SUM(im.valor_total), 0) as custo_materiais,
            COALESCE(SUM(is_val.valor_total), 0) as custo_servicos,
            os.valor_deslocamento as custo_deslocamento
        FROM ordens_servico os
        LEFT JOIN itens_material im ON os.id = im.ordem_id
        LEFT JOIN itens_servico is_val ON os.id = is_val.ordem_id
        WHERE os.data >=  AND os.status = 'Paga'
        GROUP BY os.id
    """
    
    lucro_df = pd.read_sql_query(query, conn, params=[data_inicio.strftime('%Y-%m-%d')])
    conn.close()
    
    if lucro_df.empty:
        st.info("Nenhuma ordem de serviço paga encontrada no período selecionado.")
        return
    
    # Calcular métricas de lucro
    lucro_df['custo_total'] = lucro_df['custo_materiais'] + lucro_df['custo_servicos'] + lucro_df['custo_deslocamento']
    lucro_df['lucro_bruto'] = lucro_df['receita_bruta'] - lucro_df['custo_total']
    lucro_df['lucro_estimado'] = lucro_df['receita_bruta'] * (margem_lucro / 100)
    lucro_df['margem_real'] = (lucro_df['lucro_bruto'] / lucro_df['receita_bruta']) * 100
    
    # Estatísticas gerais
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        receita_total = lucro_df['receita_bruta'].sum()
        st.metric("Receita Bruta", f"R$ {receita_total:,.2f}")
    
    with col2:
        custo_total = lucro_df['custo_total'].sum()
        st.metric("Custo Total", f"R$ {custo_total:,.2f}")
    
    with col3:
        lucro_bruto = lucro_df['lucro_bruto'].sum()
        st.metric("Lucro Bruto", f"R$ {lucro_bruto:,.2f}")
    
    with col4:
        margem_real = (lucro_bruto / receita_total) * 100 if receita_total > 0 else 0
        st.metric("Margem Real", f"{margem_real:.1f}%")
    
    st.markdown("---")
    
    # Análise detalhada
    col1, col2 = st.columns(2)
    
    with col1:
        # Composição de custos
        custos = {
            'Materiais': lucro_df['custo_materiais'].sum(),
            'Serviços': lucro_df['custo_servicos'].sum(),
            'Deslocamento': lucro_df['custo_deslocamento'].sum()
        }
        
        fig1 = px.pie(
            values=list(custos.values()),
            names=list(custos.keys()),
            title="Composição de Custos",
            color_discrete_sequence=['#004A8D', '#002B5B', '#EAF0F6']
        )
        st.plotly_chart(fig1, use_container_width=True)
    
    with col2:
        # Comparação de lucros
        lucros = {
            'Lucro Real': lucro_df['lucro_bruto'].sum(),
            'Lucro Estimado': lucro_df['lucro_estimado'].sum()
        }
        
        fig2 = px.bar(
            x=list(lucros.keys()),
            y=list(lucros.values()),
            title="Comparação de Lucros",
            color=list(lucros.values()),
            color_continuous_scale='Blues'
        )
        st.plotly_chart(fig2, use_container_width=True)
    
    # Tabela detalhada
    st.markdown("### 📊 Análise Detalhada por OS")
    
    # Selecionar colunas para exibição
    display_df = lucro_df[['id', 'data', 'receita_bruta', 'custo_total', 'lucro_bruto', 'margem_real']].copy()
    display_df.columns = ['OS', 'Data', 'Receita Bruta', 'Custo Total', 'Lucro Bruto', 'Margem Real (%)']
    
    st.dataframe(
        display_df,
        column_config={
            'OS': 'OS',
            'Data': 'Data',
            'Receita Bruta': st.column_config.NumberColumn('Receita Bruta', format="R$ %.2f"),
            'Custo Total': st.column_config.NumberColumn('Custo Total', format="R$ %.2f"),
            'Lucro Bruto': st.column_config.NumberColumn('Lucro Bruto', format="R$ %.2f"),
            'Margem Real (%)': st.column_config.NumberColumn('Margem Real (%)', format="%.1f")
        },
        use_container_width=True,
        hide_index=True
    )

def show_relatorios():
    """Exibe relatórios financeiros"""
    
    st.markdown("### 📈 Relatórios Financeiros")
    
    col1, col2 = st.columns(2)
    
    with col1:
        periodo_relatorio = st.selectbox("Período do Relatório:", ["Últimos 30 dias", "Últimos 90 dias", "Último ano"])
        
        tipo_relatorio = st.selectbox("Tipo de Relatório:", ["Completo", "Resumido", "Por Cliente", "Análise de Lucro"])
    
    with col2:
        formato_export = st.selectbox("Formato de Exportação:", ["PDF", "Excel", "CSV"])
        
        if st.button("📊 Gerar Relatório"):
            generate_financial_report(periodo_relatorio, tipo_relatorio, formato_export)
    
    # Relatório rápido
    st.markdown("---")
    st.markdown("### 📋 Relatório Rápido")
    
    # Definir período
    if periodo_relatorio == "Últimos 30 dias":
        data_inicio = datetime.now() - timedelta(days=30)
    elif periodo_relatorio == "Últimos 90 dias":
        data_inicio = datetime.now() - timedelta(days=90)
    else:
        data_inicio = datetime.now() - timedelta(days=365)
    
    # Buscar dados
    conn = get_db_connection()
    
    query = """
        SELECT 
            os.id,
            os.data,
            c.nome as cliente,
            os.total,
            os.status,
            fp.nome as forma_pagamento
        FROM ordens_servico os
        JOIN clientes c ON os.cliente_id = c.id
        LEFT JOIN formas_pagamento fp ON os.forma_pagamento_id = fp.id
        WHERE os.data >= 
        ORDER BY os.data DESC
    """
    
    relatorio_df = pd.read_sql_query(query, conn, params=[data_inicio.strftime('%Y-%m-%d')])
    conn.close()
    
    if not relatorio_df.empty:
        # Resumo executivo
        st.markdown("#### 📊 Resumo Executivo")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total de OS", len(relatorio_df))
        
        with col2:
            total_faturamento = relatorio_df['total'].sum()
            st.metric("Faturamento Total", f"R$ {total_faturamento:,.2f}")
        
        with col3:
            os_pagas = relatorio_df[relatorio_df['status'] == 'Paga']
            st.metric("OS Pagas", len(os_pagas))
        
        with col4:
            total_pago = os_pagas['total'].sum()
            st.metric("Valor Pago", f"R$ {total_pago:,.2f}")
        
        # Gráfico de evolução
        relatorio_df['data'] = pd.to_datetime(relatorio_df['data'])
        relatorio_diario = relatorio_df.groupby(relatorio_df['data'].dt.date)['total'].sum().reset_index()
        
        fig = px.line(
            relatorio_diario,
            x='data',
            y='total',
            title="Evolução do Faturamento Diário",
            color_discrete_sequence=['#004A8D']
        )
        st.plotly_chart(fig, use_container_width=True)

def get_clientes_list():
    """Retorna lista de clientes"""
    conn = get_db_connection()
    clientes_df = pd.read_sql_query("SELECT nome FROM clientes ORDER BY nome", conn)
    conn.close()
    return clientes_df['nome'].tolist()

def generate_financial_report(periodo, tipo, formato):
    """Gera relatório financeiro"""
    st.success(f"Relatório {tipo} para {periodo} em formato {formato} será gerado em breve!")
    # Implementar geração de relatório aqui

def generate_order_pdf(ordem_id):
    """Gera PDF para uma ordem de serviço específica"""
    try:
        conn = get_db_connection()
        
        # Buscar dados da ordem
        ordem_query = """
            SELECT os.*, c.nome as cliente_nome, c.cnpj_cpf, c.endereco as cliente_endereco, 
                   c.telefone, c.email, fp.nome as forma_pagamento_nome
            FROM ordens_servico os
            JOIN clientes c ON os.cliente_id = c.id
            LEFT JOIN formas_pagamento fp ON os.forma_pagamento_id = fp.id
            WHERE os.id = %s
        """
        
        ordem_df = pd.read_sql_query(ordem_query, conn, params=[ordem_id])
        
        if ordem_df.empty:
            st.error("Ordem de serviço não encontrada!")
            conn.close()
            return
        
        ordem = ordem_df.iloc[0]
        
        # Buscar itens de serviço
        servicos_query = """
            SELECT * FROM itens_servico WHERE ordem_id = %s
        """
        servicos_df = pd.read_sql_query(servicos_query, conn, params=[ordem_id])
        
        # Buscar itens de material
        materiais_query = """
            SELECT * FROM itens_material WHERE ordem_id = %s
        """
        materiais_df = pd.read_sql_query(materiais_query, conn, params=[ordem_id])
        
        # Buscar adicionais (impostos, BDI, descontos)
        adicionais_query = """
            SELECT * FROM adicionais WHERE ordem_id = %s
        """
        adicionais_df = pd.read_sql_query(adicionais_query, conn, params=[ordem_id])
        
        conn.close()
        
        # Preparar dados para o PDF
        pdf_data = {
            'numero_os': ordem_id,
            'data': ordem['data'].strftime('%d/%m/%Y'),
            'cliente': {
                'nome': ordem['cliente_nome'],
                'cnpj_cpf': ordem['cnpj_cpf'],
                'endereco': ordem['cliente_endereco'],
                'telefone': ordem['telefone'],
                'email': ordem['email']
            },
            'servicos': servicos_df.to_dict('records'),
            'materiais': materiais_df.to_dict('records'),
            'km': ordem['km'],
            'valor_deslocamento': ordem['valor_deslocamento'],
            'adicionais': adicionais_df.to_dict('records'),
            'total': ordem['total'],
            'forma_pagamento': ordem['forma_pagamento_nome']
        }
        
        # Gerar PDF
        from utilities.pdf_generator import generate_pdf_report
        pdf_path = f"pdfs/relatorio_os_{ordem_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        generate_pdf_report(pdf_data, pdf_path)
        
        # Download do PDF
        with open(pdf_path, "rb") as pdf_file:
            st.download_button(
                label=f"📥 Baixar Relatório OS #{ordem_id}",
                data=pdf_file.read(),
                file_name=f"relatorio_os_{ordem_id}.pdf",
                mime="application/pdf",
                key=f"download_pdf_{ordem_id}"
            )
        
        st.success(f"PDF da OS #{ordem_id} gerado com sucesso!")
        
    except Exception as e:
        st.error(f"Erro ao gerar PDF: {e}")
