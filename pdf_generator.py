from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import psycopg2.extras
from reportlab.lib.units import cm, inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from datetime import date, datetime
import os
import re
try:
    from database_web import get_db_connection
except ImportError:
    from database import get_db_connection

def formatar_cpf_cnpj(value):
    """Formata CPF ou CNPJ"""
    if not value:
        return ''
    # Remove caracteres não numéricos
    digits = re.sub(r'\D', '', str(value))
    
    if len(digits) == 11:  # CPF
        return f"{digits[0:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:11]}"
    elif len(digits) == 14:  # CNPJ
        return f"{digits[0:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:14]}"
    else:
        return value  # Retorna sem formatação se não for CPF nem CNPJ

def formatar_telefone(value):
    """Formata telefone"""
    if not value:
        return ''
    # Remove caracteres não numéricos
    digits = re.sub(r'\D', '', str(value))
    
    if len(digits) == 10:  # Telefone fixo
        return f"({digits[0:2]}) {digits[2:6]}-{digits[6:10]}"
    elif len(digits) == 11:  # Celular
        return f"({digits[0:2]}) {digits[2:7]}-{digits[7:11]}"
    else:
        return value  # Retorna sem formatação se não tiver 10 ou 11 dígitos

class OrderPDFGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        # Cor azul marinho
        self.dark_blue = colors.Color(red=(0/255), green=(43/255), blue=(91/255))
        self.setup_custom_styles()
        
    def setup_custom_styles(self):
        """Configurar estilos customizados"""        
        # Estilo do subtítulo
        self.styles.add(ParagraphStyle(
            name='CustomHeading2',
            parent=self.styles['Heading2'],
            fontName='Helvetica-Bold', # Arial não é padrão, usando Helvetica
            fontSize=12,
            spaceAfter=12,
            textColor=self.dark_blue
        ))
        
        # Estilo do título de local
        self.styles.add(ParagraphStyle(
            name='CustomHeading3',
            parent=self.styles['Heading3'],
            fontName='Helvetica-Bold',
            fontSize=11,
            spaceAfter=8,
            textColor=self.dark_blue
        ))
        
        # Estilo do texto normal
        self.styles.add(ParagraphStyle(
            name='CustomNormal',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=6
        ))
        
        # Estilo para cabeçalhos de tabela (texto branco)
        self.styles.add(ParagraphStyle(
            name='TableHeader',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.white,
            fontName='Helvetica-Bold',
            alignment=TA_CENTER
        ))
        
    def generate_pdf(self, order_data, output_path=None):
        """Gerar PDF da ordem de serviço"""
        order_id = order_data['ordem_id']
        today_str = date.today().strftime("%d_%m_%Y")

        if output_path is None:
            # Criar pasta pdfs se não existir
            pdf_dir = "pdfs"
            if not os.path.exists(pdf_dir):
                os.makedirs(pdf_dir)
            output_path = os.path.join(pdf_dir, f"OrdemDeServico_{today_str}_{order_id}.pdf")
            
        # Ajustar margens conforme solicitado (2.1cm)
        doc = SimpleDocTemplate(
            output_path, 
            pagesize=A4,
            leftMargin=2.1*cm,
            rightMargin=2.1*cm,
            topMargin=2.1*cm,
            bottomMargin=2.1*cm)
        story = []
        
        # Cabeçalho e Dados do Cliente
        story.extend(self.create_header(order_data))
        story.append(Spacer(1, 20))
        story.extend(self.create_client_section(order_data))
        story.append(Spacer(1, 15))
        
        # Serviços
        story.extend(self.create_services_section(order_data))
        story.append(Spacer(1, 15))

        # Impostos
        story.extend(self.create_impostos_section(order_data))
        story.append(Spacer(1, 15))

        # BDI
        story.extend(self.create_bdi_section(order_data))
        story.append(Spacer(1, 15))

        # Materiais (só adicionar se houver materiais)
        materials_section = self.create_materials_section(order_data)
        if materials_section:  # Só adicionar seção e espaçamento se houver materiais
            story.extend(materials_section)
            story.append(Spacer(1, 15))
                
        # Composição do Faturamento
        story.extend(self.create_billing_composition(order_data))
        story.append(Spacer(1, 15))
        
        # Forma de Pagamento e Assinatura
        story.extend(self.create_payment_signature_section(order_data))
        
        # Construir PDF
        doc.build(story)
        return output_path
        
    def create_header(self, order_data):
        """Criar cabeçalho com logo e informações da OS"""
        elements = []
        
        # Buscar imagem de capa configurada
        capa_path = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Criar tabela configuracoes se não existir (migração)
            try:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS configuracoes (
                        id SERIAL PRIMARY KEY,
                        chave VARCHAR(255) NOT NULL UNIQUE,
                        valor TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                conn.commit()
            except:
                pass  # Tabela pode já existir
            
            cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'imagem_capa_relatorio'")
            result = cursor.fetchone()
            if result and result[0]:
                capa_path = result[0]
                # Verificar se o arquivo existe
                if not os.path.exists(capa_path):
                    capa_path = None
            conn.close()
        except Exception as e:
            print(f"Erro ao buscar imagem de capa: {e}")
        
        # Se tiver imagem de capa configurada, usar ela
        if capa_path and os.path.exists(capa_path):
            try:
                # Carregar imagem e redimensionar mantendo proporção
                img = Image(capa_path)
                original_width = img.imageWidth
                original_height = img.imageHeight
                
                # Largura máxima disponível na página (considerando margens)
                max_width = 18*cm  # Largura útil da página A4
                max_height = 25*cm  # Altura útil da página A4
                
                # Calcular proporção para manter aspecto
                width_ratio = max_width / original_width
                height_ratio = max_height / original_height
                ratio = min(width_ratio, height_ratio)  # Usar o menor para caber na página
                
                new_width = original_width * ratio
                new_height = original_height * ratio
                
                capa = Image(capa_path, width=new_width, height=new_height)
                capa.hAlign = 'CENTER'
                elements.append(capa)
                elements.append(Spacer(1, 10))
            except Exception as e:
                print(f"Erro ao carregar imagem de capa: {e}")
                # Fallback para logo padrão
                logo_path = "img/logo.png"
                if os.path.exists(logo_path):
                    try:
                        logo = Image(logo_path, width=16.8*cm, height=2.81*cm)
                        logo.hAlign = 'CENTER'
                        elements.append(logo)
                        elements.append(Spacer(1, 15))
                    except:
                        pass
        else:
            # Logo padrão (img/logo.png) - usar como logo menor
            logo_path = "img/logo.png"
            if os.path.exists(logo_path):
                try:
                    # Usar como logo menor (não como capa completa)
                    logo = Image(logo_path, width=16.8*cm, height=2.81*cm)
                    logo.hAlign = 'CENTER'
                    elements.append(logo)
                    elements.append(Spacer(1, 15))
                except Exception as e:
                    print(f"Erro ao carregar logo: {e}")
                    pass  # Se não conseguir carregar, continua sem ela
        
        # Título do relatório
        ordem_id = order_data.get('ordem_id', '')
        report_title_style = ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=12,
            alignment=TA_CENTER,
            textColor=self.dark_blue
        )
        elements.append(Paragraph(f"Relatório - Ordem de Serviço - {ordem_id}", report_title_style))
        return elements
        
    def create_client_section(self, order_data):
        """Criar seção de dados do cliente"""
        elements = []
        
        # Buscar dados completos do cliente
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT nome, cnpj_cpf, endereco, telefone, email 
                FROM clientes WHERE id = %s
            ''', (order_data['cliente_id'],))
            
            cliente = cursor.fetchone()
            conn.close()
            
            if cliente:
                # Criar tabela com duas colunas: campos e dados
                client_data = [
                    # Cabeçalho azul
                    [Paragraph("<b>Cliente</b>", ParagraphStyle(
                        name='ClientHeader',
                        parent=self.styles['Normal'],
                        fontSize=12,
                        textColor=colors.white,
                        alignment=TA_CENTER
                    )), ''],
                    # Dados do cliente em duas colunas
                    ["Nome/Razão Social:", cliente[0] or ""],
                    ["CPF/CNPJ:", formatar_cpf_cnpj(cliente[1]) if cliente[1] else ""],
                    ["Endereço:", cliente[2] or ""],
                    ["Telefone:", formatar_telefone(cliente[3]) if cliente[3] else ""],
                    ["E-mail:", cliente[4] or ""]
                ]
                
                client_table = Table(client_data, colWidths=[6*cm, 10*cm])
                client_table.setStyle(TableStyle([
                    # Cabeçalho azul
                    ('SPAN', (0, 0), (1, 0)),
                    ('BACKGROUND', (0, 0), (1, 0), self.dark_blue),
                    ('ALIGN', (0, 0), (1, 0), 'CENTER'),
                    ('FONTNAME', (0, 0), (1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (1, 0), 12),
                    ('BOTTOMPADDING', (0, 0), (1, 0), 8),
                    ('TOPPADDING', (0, 0), (1, 0), 8),
                    # Dados do cliente
                    ('ALIGN', (0, 1), (0, -1), 'LEFT'),
                    ('ALIGN', (1, 1), (1, -1), 'LEFT'),
                    ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
                    ('FONTNAME', (1, 1), (1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 10),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                    ('TOPPADDING', (0, 1), (-1, -1), 4),
                    # Bordas
                    ('BOX', (0, 0), (-1, -1), 1, colors.black),
                    ('INNERGRID', (0, 1), (-1, -1), 0.5, colors.grey),
                ]))
                
                elements.append(KeepTogether(client_table))
        except Exception as e:
            elements.append(Paragraph(f"Erro ao carregar dados: {e}", self.styles['CustomNormal']))
            
        return elements
        
    def create_services_section(self, order_data):
        """Criar seção de serviços"""
        elements = []
        total_servicos = 0.0
        
        title_style = self.styles['CustomHeading2']
        title_style.alignment = TA_CENTER
        elements.append(Paragraph("Serviços", title_style)) # Título da seção
        
        if order_data.get('servicos'):
            servicos = order_data['servicos']
            
            # Verificar se há serviços com local ou data
            servicos_com_local = [s for s in servicos if s.get('local')]
            servicos_sem_local = [s for s in servicos if not s.get('local')]
            servicos_com_data = [s for s in servicos if s.get('data')]
            tem_data = len(servicos_com_data) > 0
            
            # Obter locais únicos
            locais_unicos = list(set([s['local'] for s in servicos_com_local if s.get('local')]))
            
            # Se houver múltiplos locais, separar em tabelas diferentes
            if len(locais_unicos) > 1:
                # Definir larguras fixas para todas as tabelas (se tem_data, todas terão coluna Data)
                if tem_data:
                    col_widths = [0.8*cm, 4.5*cm, 1.8*cm, 1.8*cm, 1.5*cm, 2.5*cm, 2.5*cm]
                else:
                    col_widths = [0.8*cm, 5*cm, 2*cm, 2*cm, 3*cm, 3*cm]
                
                # Agrupar serviços por local
                for local in sorted(locais_unicos):
                    servicos_do_local = [s for s in servicos_com_local if s.get('local') == local]
                    total_local = sum(s['total'] for s in servicos_do_local)
                    total_servicos += total_local
                    
                    # Criar tabela para este local - sempre com a mesma estrutura se tem_data
                    if tem_data:
                        services_data = [
                            ["Item", 
                             Paragraph("Descrição", self.styles['TableHeader']), 
                             "Local", 
                             "Data", 
                             "Qtde", 
                             Paragraph("Valor Unit.", self.styles['TableHeader']), 
                             Paragraph("Valor Total (R$)", self.styles['TableHeader'])]
                        ]
                    else:
                        services_data = [
                            ["Item", 
                             Paragraph("Descrição", self.styles['TableHeader']), 
                             "Local", 
                             "Qtde", 
                             Paragraph("Valor Unit.", self.styles['TableHeader']), 
                             Paragraph("Valor Total (R$)", self.styles['TableHeader'])]
                        ]
                    
                    for i, servico in enumerate(servicos_do_local, 1):
                        desc_text = servico['nome']
                        if servico.get('tempo') and servico.get('taxa'):
                            t_val = float(servico['tempo'])
                            t_str = f"{int(t_val)}" if t_val.is_integer() else f"{t_val}"
                            desc_text += f" - Tempo: {t_str}h x Taxa: R$ {servico['taxa']:.2f}/h"
                        
                        # Formatar data se existir
                        data_formatada = ''
                        if servico.get('data'):
                            try:
                                from datetime import datetime
                                if isinstance(servico['data'], str):
                                    data_obj = datetime.strptime(servico['data'], "%Y-%m-%d").date()
                                else:
                                    data_obj = servico['data']
                                data_formatada = data_obj.strftime("%d/%m/%Y")
                            except:
                                data_formatada = ''
                        
                        local_text = servico.get('local', '') or ''
                        if tem_data:
                            services_data.append([
                                str(i),
                                Paragraph(desc_text, self.styles['CustomNormal']),
                                Paragraph(local_text, self.styles['CustomNormal']),
                                data_formatada,
                                str(servico['qtd']),
                                f"R$ {servico['preco_unit']:.2f}",
                                f"R$ {servico['total']:.2f}"
                            ])
                        else:
                            services_data.append([
                                str(i),
                                Paragraph(desc_text, self.styles['CustomNormal']),
                                Paragraph(local_text, self.styles['CustomNormal']),
                                str(servico['qtd']),
                                f"R$ {servico['preco_unit']:.2f}",
                                f"R$ {servico['total']:.2f}"
                            ])
                    
                    # Linha de total do local
                    if tem_data:
                        services_data.append(['', '', '', '', '', 'Total', f"R$ {total_local:.2f}"])
                        span_cols = (0, -1), (4, -1)  # Mesclar até a coluna de quantidade
                    else:
                        services_data.append(['', '', '', '', 'Total', f"R$ {total_local:.2f}"])
                        span_cols = (0, -1), (3, -1)  # Mesclar até a coluna de quantidade
                    
                    # Ajustar larguras das colunas para acomodar os cabeçalhos completos
                    services_table = Table(services_data, colWidths=col_widths)
                    services_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), self.dark_blue),
                        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
                        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                        ('ALIGN', (len(col_widths)-2, -1), (len(col_widths)-1, -1), 'RIGHT'),
                        ('SPAN', span_cols[0], span_cols[1]), # Mesclar células do total
                        ('ALIGN', span_cols[0], span_cols[1], 'RIGHT'),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 9),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ]))
                    
                    # Título do local
                    local_title = Paragraph(f"<b>Local: {local}</b>", self.styles['CustomHeading3'])
                    local_title.alignment = TA_CENTER
                    elements.append(KeepTogether([
                        local_title,
                        Spacer(1, 0.2*cm),
                        services_table
                    ]))
                    elements.append(Spacer(1, 0.5*cm))
                
                # Adicionar serviços sem local (se houver)
                if servicos_sem_local:
                    total_sem_local = sum(s['total'] for s in servicos_sem_local)
                    total_servicos += total_sem_local
                    
                    # Usar a mesma estrutura das outras tabelas
                    if tem_data:
                        services_data = [
                            ["Item", 
                             Paragraph("Descrição", self.styles['TableHeader']), 
                             "Local", 
                             "Data", 
                             "Qtde", 
                             Paragraph("Valor Unit.", self.styles['TableHeader']), 
                             Paragraph("Valor Total (R$)", self.styles['TableHeader'])]
                        ]
                    else:
                        services_data = [
                            ["Item", 
                             Paragraph("Descrição", self.styles['TableHeader']), 
                             "Local", 
                             "Qtde", 
                             Paragraph("Valor Unit.", self.styles['TableHeader']), 
                             Paragraph("Valor Total (R$)", self.styles['TableHeader'])]
                        ]
                    
                    for i, servico in enumerate(servicos_sem_local, 1):
                        desc_text = servico['nome']
                        if servico.get('tempo') and servico.get('taxa'):
                            t_val = float(servico['tempo'])
                            t_str = f"{int(t_val)}" if t_val.is_integer() else f"{t_val}"
                            desc_text += f" - Tempo: {t_str}h x Taxa: R$ {servico['taxa']:.2f}/h"
                        
                        # Formatar data se existir
                        data_formatada = ''
                        if servico.get('data'):
                            try:
                                from datetime import datetime
                                if isinstance(servico['data'], str):
                                    data_obj = datetime.strptime(servico['data'], "%Y-%m-%d").date()
                                else:
                                    data_obj = servico['data']
                                data_formatada = data_obj.strftime("%d/%m/%Y")
                            except:
                                data_formatada = ''
                        
                        if tem_data:
                            services_data.append([
                                str(i),
                                Paragraph(desc_text, self.styles['CustomNormal']),
                                '',  # Local vazio
                                data_formatada,
                                str(servico['qtd']),
                                f"R$ {servico['preco_unit']:.2f}",
                                f"R$ {servico['total']:.2f}"
                            ])
                        else:
                            services_data.append([
                                str(i),
                                Paragraph(desc_text, self.styles['CustomNormal']),
                                '',  # Local vazio
                                str(servico['qtd']),
                                f"R$ {servico['preco_unit']:.2f}",
                                f"R$ {servico['total']:.2f}"
                            ])
                    
                    # Linha de total
                    if tem_data:
                        services_data.append(['', '', '', '', '', 'Total', f"R$ {total_sem_local:.2f}"])
                        span_cols = (0, -1), (4, -1)
                    else:
                        services_data.append(['', '', '', '', 'Total', f"R$ {total_sem_local:.2f}"])
                        span_cols = (0, -1), (3, -1)
                    
                    # Usar as mesmas larguras definidas anteriormente
                    services_table = Table(services_data, colWidths=col_widths)
                    services_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), self.dark_blue),
                        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
                        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                        ('ALIGN', (len(col_widths)-2, -1), (len(col_widths)-1, -1), 'RIGHT'),
                        ('SPAN', span_cols[0], span_cols[1]),
                        ('ALIGN', span_cols[0], span_cols[1], 'RIGHT'),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 9),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ]))
                    
                    elements.append(KeepTogether(services_table))
            else:
                # Um único local ou nenhum local - tabela única
                tem_local = len(servicos_com_local) > 0
                
                # Usar a mesma estrutura das outras tabelas
                if tem_data:
                    col_widths = [0.8*cm, 4.5*cm, 1.8*cm, 1.8*cm, 1.5*cm, 2.5*cm, 2.5*cm]
                else:
                    col_widths = [0.8*cm, 5*cm, 2*cm, 2*cm, 3*cm, 3*cm]
                
                if tem_local:
                    # Se houver data, adicionar coluna Data ao lado de Local
                    if tem_data:
                        services_data = [
                            ["Item", 
                             Paragraph("Descrição", self.styles['TableHeader']), 
                             "Local", 
                             "Data", 
                             "Qtde", 
                             Paragraph("Valor Unit.", self.styles['TableHeader']), 
                             Paragraph("Valor Total (R$)", self.styles['TableHeader'])]
                        ]
                    else:
                        services_data = [
                            ["Item", 
                             Paragraph("Descrição", self.styles['TableHeader']), 
                             "Local", 
                             "Qtde", 
                             Paragraph("Valor Unit.", self.styles['TableHeader']), 
                             Paragraph("Valor Total (R$)", self.styles['TableHeader'])]
                        ]
                else:
                    # Sem local, mas usar a mesma estrutura se tem_data
                    if tem_data:
                        services_data = [
                            ["Item", 
                             Paragraph("Descrição", self.styles['TableHeader']), 
                             "Local", 
                             "Data", 
                             "Qtde", 
                             Paragraph("Valor Unit.", self.styles['TableHeader']), 
                             Paragraph("Valor Total (R$)", self.styles['TableHeader'])]
                        ]
                    else:
                        services_data = [
                            ["Item", 
                             Paragraph("Descrição", self.styles['TableHeader']), 
                             "Local", 
                             "Qtde", 
                             Paragraph("Valor Unit.", self.styles['TableHeader']), 
                             Paragraph("Valor Total (R$)", self.styles['TableHeader'])]
                        ]
                
                for i, servico in enumerate(servicos, 1):
                    desc_text = servico['nome']
                    if servico.get('tempo') and servico.get('taxa'):
                        t_val = float(servico['tempo'])
                        t_str = f"{int(t_val)}" if t_val.is_integer() else f"{t_val}"
                        desc_text += f" - Tempo: {t_str}h x Taxa: R$ {servico['taxa']:.2f}/h"
                    
                    # Formatar data se existir
                    data_formatada = ''
                    if servico.get('data'):
                        try:
                            from datetime import datetime
                            if isinstance(servico['data'], str):
                                data_obj = datetime.strptime(servico['data'], "%Y-%m-%d").date()
                            else:
                                data_obj = servico['data']
                            data_formatada = data_obj.strftime("%d/%m/%Y")
                        except:
                            data_formatada = ''
                    
                    local_text = servico.get('local', '') or ''
                    if tem_local:
                        if tem_data:
                            services_data.append([
                                str(i),
                                Paragraph(desc_text, self.styles['CustomNormal']),
                                Paragraph(local_text, self.styles['CustomNormal']),
                                data_formatada,
                                str(servico['qtd']),
                                f"R$ {servico['preco_unit']:.2f}",
                                f"R$ {servico['total']:.2f}"
                            ])
                        else:
                            services_data.append([
                                str(i),
                                Paragraph(desc_text, self.styles['CustomNormal']),
                                Paragraph(local_text, self.styles['CustomNormal']),
                                str(servico['qtd']),
                                f"R$ {servico['preco_unit']:.2f}",
                                f"R$ {servico['total']:.2f}"
                            ])
                    else:
                        # Sem local, mas usar a mesma estrutura
                        if tem_data:
                            services_data.append([
                                str(i),
                                Paragraph(desc_text, self.styles['CustomNormal']),
                                '',  # Local vazio
                                data_formatada,
                                str(servico['qtd']),
                                f"R$ {servico['preco_unit']:.2f}",
                                f"R$ {servico['total']:.2f}"
                            ])
                        else:
                            services_data.append([
                                str(i),
                                Paragraph(desc_text, self.styles['CustomNormal']),
                                '',  # Local vazio
                                str(servico['qtd']),
                                f"R$ {servico['preco_unit']:.2f}",
                                f"R$ {servico['total']:.2f}"
                            ])
                    total_servicos += servico['total']

                # Linha de total
                if tem_data:
                    services_data.append(['', '', '', '', '', 'Total', f"R$ {total_servicos:.2f}"])
                    span_cols = (0, -1), (4, -1)
                else:
                    services_data.append(['', '', '', '', 'Total', f"R$ {total_servicos:.2f}"])
                    span_cols = (0, -1), (3, -1)
                
                services_table = Table(services_data, colWidths=col_widths)
                services_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), self.dark_blue),
                    ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
                    ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                    ('ALIGN', (len(col_widths)-2, -1), (len(col_widths)-1, -1), 'RIGHT'),
                    ('SPAN', span_cols[0], span_cols[1]), # Mesclar células do total
                    ('ALIGN', span_cols[0], span_cols[1], 'RIGHT'),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                
                elements.append(KeepTogether(services_table))
        else:
            elements.append(Paragraph("Nenhum serviço cadastrado.", self.styles['CustomNormal']))
            
        return elements
        
    def create_materials_section(self, order_data):
        """Criar seção de materiais"""
        elements = []
        total_materiais = 0.0
        
        # Se não houver materiais, retornar lista vazia (não exibir a seção)
        if not order_data.get('materiais'):
            return elements
        
        title_style = self.styles['CustomHeading2']
        title_style.alignment = TA_CENTER
        elements.append(Paragraph("Materiais", title_style)) # Título da seção
        
        # Verificar se algum material tem data
        tem_data = any(m.get('data') for m in order_data['materiais'])
        
        if tem_data:
            materials_data = [["Item", "Descrição", "Data", "Qtde", "Valor Unit.", "Valor Total (R$)"]]
        else:
            materials_data = [["Item", "Descrição", "Qtde", "Valor Unit.", "Valor Total (R$)"]]
        
        for i, material in enumerate(order_data['materiais'], 1):
            nome_completo = f"{material['nome']} - {material['marca']}" if material.get('marca') else material['nome']
            
            if tem_data:
                data_material = material.get('data', '') or ''
                materials_data.append([
                    str(i),
                    Paragraph(nome_completo, self.styles['CustomNormal']),
                    data_material,
                    str(material['qtd']),
                    f"R$ {material['preco_unit']:.2f}",
                    f"R$ {material['total']:.2f}"
                ])
            else:
                materials_data.append([
                    str(i),
                    Paragraph(nome_completo, self.styles['CustomNormal']),
                    str(material['qtd']),
                    f"R$ {material['preco_unit']:.2f}",
                    f"R$ {material['total']:.2f}"
                ])
            total_materiais += material['total']

        # Linha de total
        if tem_data:
            materials_data.append(['', '', '', '', 'Total', f"R$ {total_materiais:.2f}"])
            col_widths = [1*cm, 4.5*cm, 2.5*cm, 1.5*cm, 2.5*cm, 3*cm]
            span_cols = (0, -1), (3, -1)  # Mesclar Item até Qtde
        else:
            materials_data.append(['', '', '', 'Total', f"R$ {total_materiais:.2f}"])
            col_widths = [1*cm, 5.5*cm, 2.5*cm, 3.5*cm, 3.5*cm]
            span_cols = (0, -1), (2, -1)  # Mesclar Item até Qtde
        
        materials_table = Table(materials_data, colWidths=col_widths)
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), self.dark_blue),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('SPAN', span_cols[0], span_cols[1]), # Mesclar células do total
            ('ALIGN', span_cols[0], span_cols[1], 'RIGHT'),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]
        
        table_style.append(('ALIGN', (len(col_widths)-2, -1), (len(col_widths)-1, -1), 'RIGHT'))
        
        materials_table.setStyle(TableStyle(table_style))
        
        elements.append(KeepTogether(materials_table))
            
        return elements
        
    def create_impostos_section(self, order_data):
        """Criar seção de impostos"""
        elements = []
        impostos = [a for a in order_data.get('adicionais', []) if a['tipo'] == 'imposto']
        
        if impostos:
            title_style = self.styles['CustomHeading2']
            title_style.alignment = TA_CENTER
            elements.append(Paragraph("Impostos", title_style))
            
            impostos_data = [["Item", "Descrição", "Valor (R$)"]]
            total_impostos = 0.0
            
            for i, imposto in enumerate(impostos, 1):
                impostos_data.append([
                    str(i),
                    imposto['descricao'],
                    f"R$ {imposto['valor']:.2f}"
                ])
                total_impostos += imposto['valor']

            impostos_data.append(['', 'Total de Impostos', f"R$ {total_impostos:.2f}"])
            
            impostos_table = Table(impostos_data, colWidths=[2*cm, 11*cm, 3.5*cm])
            impostos_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), self.dark_blue),
                ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('ALIGN', (2, -1), (2, -1), 'RIGHT'),
                ('SPAN', (0, -1), (1, -1)),
                ('ALIGN', (0, -1), (1, -1), 'RIGHT'),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(KeepTogether(impostos_table))
        return elements

    def create_bdi_section(self, order_data):
        """Criar seção de BDI"""
        elements = []
        bdi_list = [a for a in order_data.get('adicionais', []) if a['tipo'] == 'bdi']
        
        if bdi_list:
            title_style = self.styles['CustomHeading2']
            title_style.alignment = TA_CENTER
            elements.append(Paragraph("BDI (Benefícios e Despesas Indiretas)", title_style))
            
            bdi_data = [["Item", "Descrição", "Valor (R$)"]]
            total_bdi = 0.0
            
            for i, bdi_item in enumerate(bdi_list, 1):
                bdi_data.append([str(i), bdi_item['descricao'], f"R$ {bdi_item['valor']:.2f}"])
                total_bdi += bdi_item['valor']

            bdi_data.append(['', 'Total BDI', f"R$ {total_bdi:.2f}"])
            
            bdi_table = Table(bdi_data, colWidths=[2*cm, 11*cm, 3.5*cm])
            bdi_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), self.dark_blue),
                ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('ALIGN', (2, -1), (2, -1), 'RIGHT'),
                ('SPAN', (0, -1), (1, -1)),
                ('ALIGN', (0, -1), (1, -1), 'RIGHT'),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(KeepTogether(bdi_table))
        return elements

    def create_billing_composition(self, order_data):
        """Criar composição do faturamento"""
        elements = []
        
        title_style = self.styles['CustomHeading2']
        title_style.alignment = TA_CENTER
        elements.append(Paragraph("Resumo Financeiro", title_style)) # Título da seção
        
        # Calcular totais
        servicos_total = sum(servico['total'] for servico in order_data.get('servicos', []))
        materiais_total = sum(material['total'] for material in order_data.get('materiais', []))
        distance_data = order_data.get('distance_data', {})
        deslocamento_total = distance_data.get('displacement_cost', 0) if distance_data else 0
        distance_km = distance_data.get('distance_km', 0) if distance_data else 0
        
        adicionais = order_data.get('adicionais', [])
        impostos_total = sum(a['valor'] for a in adicionais if a['tipo'] == 'imposto')
        bdi_total = sum(a['valor'] for a in adicionais if a['tipo'] == 'bdi')
        descontos_total = sum(a['valor'] for a in adicionais if a['tipo'] == 'desconto')

        total_geral = (servicos_total + materiais_total + deslocamento_total + 
                       impostos_total + bdi_total - descontos_total)
        
        # Formatar texto de deslocamento com KM
        deslocamento_texto = "(+) Frete/Deslocamento"
        if distance_km and distance_km > 0:
            deslocamento_texto = f"(+) Frete/Deslocamento ({distance_km:.2f} KM)"
        
        composition_data = [
            ["(+) Materiais", f"R$ {materiais_total:.2f}"],
            ["(+) Serviços", f"R$ {servicos_total:.2f}"],
            [deslocamento_texto, f"R$ {deslocamento_total:.2f}"],            
            ["(-) Descontos", f"R$ {descontos_total:.2f}"],
            ["", ""],
            ["TOTAL FINAL:", f"R$ {total_geral:.2f}"]
        ]
        
        # Criar uma lista de estilos para adicionar dinamicamente
        style_commands = [
            # Adicionar impostos e bdi se existirem
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -2), 10),
            ('FONTSIZE', (0, -1), (-1, -1), 12), # Tamanho da fonte do total final ajustado
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LINEBELOW', (0, -2), (-1, -2), 1, colors.black),
            ('LINEBELOW', (0, -1), (-1, -1), 2, colors.black),
        ]
        
        # Inserir Impostos e BDI dinamicamente se existirem
        if bdi_total > 0:
            composition_data.insert(-3, ["(+) BDI", f"R$ {bdi_total:.2f}"])
            style_commands.append(('LINEABOVE', (0, -3), (-1, -3), 0.5, colors.grey))
        
        if impostos_total > 0:
            composition_data.insert(-3, ["(+) Impostos", f"R$ {impostos_total:.2f}"])
            style_commands.append(('LINEABOVE', (0, -3), (-1, -3), 0.5, colors.grey))

        composition_table = Table(composition_data, colWidths=[12*cm, 4*cm])
        composition_table.setStyle(TableStyle(style_commands))
        elements.append(KeepTogether(composition_table))
        return elements

    def create_payment_signature_section(self, order_data):
        """Criar seção de forma de pagamento e assinatura"""
        elements = []
        elements.append(Spacer(1, 15))
        
        # Buscar forma de pagamento pelo ID da OS
        forma_pagamento_str = "Não especificada"
        try:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute('''
                SELECT fp.nome, fp.tipo, os.parcelas
                FROM formas_pagamento fp
                JOIN ordens_servico os ON os.forma_pagamento_id = fp.id
                WHERE os.id = %s
            ''', (order_data['ordem_id'],))
            result = cursor.fetchone()
            if result:
                forma_pagamento_str = result['nome']
                elements.append(Paragraph(f"<b>Forma de Pagamento:</b> {forma_pagamento_str}", self.styles['CustomNormal']))
                if result['tipo'] == 'Parcelado' and result['parcelas'] and result['parcelas'] > 1:
                    elements.append(Paragraph(f"<b>Número de Parcelas:</b> {result['parcelas']}x", self.styles['CustomNormal'])) # Adicionado 'x'
            else:
                elements.append(Paragraph(f"<b>Forma de Pagamento:</b> {forma_pagamento_str}", self.styles['CustomNormal']))
            conn.close()
        except Exception as e:
            print(f"Erro ao buscar forma de pagamento: {e}")
            elements.append(Paragraph(f"<b>Forma de Pagamento:</b> {forma_pagamento_str}", self.styles['CustomNormal']))
        
        # Data
        data_emissao = order_data.get('data_emissao', datetime.now().strftime("%d/%m/%Y"))
        elements.append(Paragraph(f"<b>Data:</b> {data_emissao}", self.styles['CustomNormal']))
        elements.append(Spacer(1, 20)) # Espaço extra depois da data
        
        elements.append(Spacer(1, 20))
        
        # Buscar e exibir assinatura
        assinatura_path = None
        assinatura_nome = None
        assinatura_cargo = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Tentar obter assinatura_id do order_data primeiro
            assinatura_id = order_data.get('assinatura_id')
            if assinatura_id is None:
                # Se não estiver no order_data, buscar do banco
                cursor.execute('''
                    SELECT assinatura_id FROM ordens_servico WHERE id = %s
                ''', (order_data['ordem_id'],))
                result = cursor.fetchone()
                if result and result['assinatura_id']:
                    assinatura_id = result['assinatura_id']
            
            # Se assinatura_id for None ou string vazia, não buscar assinatura (permite assinatura manual)
            if assinatura_id and str(assinatura_id).strip():
                # Adicionar coluna cargo se não existir (migração)
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
                except:
                    pass
                
                cursor.execute('''
                    SELECT caminho_imagem, nome, cargo FROM assinaturas WHERE id = %s AND ativo = true
                ''', (assinatura_id,))
                result = cursor.fetchone()
                if result:
                    assinatura_path = result['caminho_imagem']
                    assinatura_nome = result['nome']
                    assinatura_cargo = result.get('cargo') if 'cargo' in result else 'Técnico Eletricista Industrial/Residencial'
            
            conn.close()
        except Exception as e:
            print(f"Erro ao buscar assinatura: {e}")
        
        # Se não encontrou assinatura específica E assinatura_id não foi explicitamente None/vazio, tentar usar assinatura padrão
        # Se assinatura_id for None/vazio, não buscar padrão (permite assinatura manual)
        # IMPORTANTE: Se assinatura_id for None ou vazio, não buscar assinatura padrão
        if not assinatura_path and assinatura_id and str(assinatura_id).strip():
            try:
                conn = get_db_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                
                # Adicionar coluna cargo se não existir (migração)
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
                except:
                    pass
                
                cursor.execute('''
                    SELECT caminho_imagem, nome, cargo FROM assinaturas WHERE padrao = true AND ativo = true LIMIT 1
                ''')
                result = cursor.fetchone()
                if result:
                    assinatura_path = result['caminho_imagem']
                    assinatura_nome = result['nome']
                    assinatura_cargo = result.get('cargo') if 'cargo' in result else 'Técnico Eletricista Industrial/Residencial'
                conn.close()
            except Exception as e:
                print(f"Erro ao buscar assinatura padrão: {e}")
        
        # Se ainda não encontrou, tentar usar assinatura.png na pasta assinaturas ou raiz
        if not assinatura_path or not os.path.exists(assinatura_path):
            # Verificar se o caminho está na pasta assinaturas (legado)
            if assinatura_path and ('assinaturas/' in assinatura_path or '/' not in assinatura_path):
                # Tentar encontrar na pasta assinaturas
                filename = assinatura_path.replace('assinaturas/', '') if 'assinaturas/' in assinatura_path else assinatura_path
                if os.path.exists(os.path.join('assinaturas', filename)):
                    assinatura_path = os.path.join('assinaturas', filename)
            
            # NÃO fazer fallback para assinatura.png se assinatura_id for None/vazio
            # Se assinatura_id for None/vazio, deixar assinatura_path como None para não mostrar nada
        
        # Ajustar caminho se estiver na pasta assinaturas (legado) mas não existir
        if assinatura_path and not os.path.exists(assinatura_path):
            # Tentar encontrar na pasta assinaturas
            if 'assinaturas/' in assinatura_path or ('/' not in assinatura_path and not assinatura_path.startswith('uploads/')):
                filename = assinatura_path.replace('assinaturas/', '') if 'assinaturas/' in assinatura_path else assinatura_path
                if os.path.exists(os.path.join('assinaturas', filename)):
                    assinatura_path = os.path.join('assinaturas', filename)
        
        # Exibir assinatura se encontrada E se assinatura_id não for None/vazio
        # Se assinatura_id for None/vazio, não exibir nada (permite assinatura manual)
        if assinatura_path and os.path.exists(assinatura_path) and assinatura_id and str(assinatura_id).strip():
            try:
                # Carregar e redimensionar imagem mantendo proporção
                # Largura útil ~16.8cm. Solicitado 30-40%. Usando 6cm (~35%).
                target_width = 8.0 * cm
                
                img = Image(assinatura_path)
                original_width = img.imageWidth
                original_height = img.imageHeight
                
                # Calcular proporção para manter aspecto
                ratio = target_width / original_width
                new_height = original_height * ratio
                
                img = Image(assinatura_path, width=target_width, height=new_height)
                img.hAlign = 'CENTER'
                
                # Adicionar imagem com espaçamento reduzido
                elements.append(Spacer(1, 5))
                elements.append(img)
                elements.append(Spacer(1, -5)) # Ajuste para aproximar assinatura da linha

                # Texto abaixo da assinatura com nome e cargo
                nome_texto = assinatura_nome if assinatura_nome else "Gabriela R. S. P. Bernard"
                cargo_texto = assinatura_cargo if assinatura_cargo else 'Técnico Eletricista Industrial/Residencial'
                
                nome_style = ParagraphStyle(
                    name='SignatureText',
                    parent=self.styles['Normal'],
                    fontSize=10,
                    alignment=TA_CENTER,
                    leading=12
                )
                
                # Tabela para linha e texto (compacto)
                # Linha de 7cm
                line_width = 8 * cm
                p_text = Paragraph(f"<b>{nome_texto}</b><br/>{cargo_texto}", nome_style)
                
                sig_table = Table([[p_text]], colWidths=[line_width])
                sig_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('LINEABOVE', (0, 0), (-1, 0), 0.5, colors.black), # Linha fina acima
                    ('TOPPADDING', (0, 0), (-1, -1), 3), # Espaço entre linha e texto
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ]))
                sig_table.hAlign = 'CENTER'
                elements.append(KeepTogether(sig_table))
                
            except Exception as e:
                print(f"Erro ao carregar imagem de assinatura: {e}")
                # Se falhar, usar linha de assinatura padrão
                assinatura_style = ParagraphStyle(
                    name='SignatureLine',
                    parent=self.styles['Normal'],
                    fontSize=10,
                    alignment=TA_CENTER
                )
                assinatura_p = Paragraph("_" * 50, assinatura_style)
                elements.append(assinatura_p)
                
                # Texto abaixo da linha
                nome_style = ParagraphStyle(
                    name='SignatureText',
                    parent=self.styles['Normal'],
                    fontSize=10,
                    alignment=TA_CENTER
                )
                nome_texto = assinatura_nome if assinatura_nome else "Nome"
                cargo_texto = assinatura_cargo if assinatura_cargo else 'Técnico Eletricista Industrial/Residencial'
                nome_p = Paragraph(f"{nome_texto}<br/>{cargo_texto}", nome_style)
                elements.append(nome_p)
        # Se não houver assinatura selecionada (assinatura_id None/vazio), não mostrar nada
        # Apenas adicionar espaço para assinatura manual
        elif not assinatura_id or not str(assinatura_id).strip():
            # Apenas espaço para assinatura manual - sem linha, sem texto
            elements.append(Spacer(1, 30))
        
        return elements
    
    def generate_relatorio_mensal_cliente(self, report_data, output_path=None):
        """Gerar relatório mensal consolidado do cliente"""
        cliente = report_data['cliente']
        mes_ano = report_data['mes_ano']
        numeros_os = report_data['numeros_os']
        
        # Criar nome do arquivo
        if output_path is None:
            pdf_dir = "pdfs"
            if not os.path.exists(pdf_dir):
                os.makedirs(pdf_dir)
            nome_arquivo = f"Relatorio_Mensal_{cliente['nome'].replace(' ', '_')}_{mes_ano.replace('/', '_')}.pdf"
            output_path = os.path.join(pdf_dir, nome_arquivo)
        
        # Configurar documento
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=2.1*cm,
            rightMargin=2.1*cm,
            topMargin=2.1*cm,
            bottomMargin=2.1*cm
        )
        story = []
        
        # Cabeçalho
        story.extend(self.create_header_relatorio_mensal(cliente, mes_ano, numeros_os))
        story.append(Spacer(1, 20))
        
        # Dados do cliente
        story.extend(self.create_client_section_relatorio_mensal(cliente))
        story.append(Spacer(1, 15))
        
        # Serviços (agrupados por local)
        story.extend(self.create_services_section_relatorio_mensal(report_data))
        story.append(Spacer(1, 15))
        
        # Materiais (se houver)
        if report_data.get('materiais'):
            story.extend(self.create_materials_section_relatorio_mensal(report_data))
            story.append(Spacer(1, 15))
        
        # Frete/Deslocamento (se houver)
        if report_data.get('fretes_deslocamentos'):
            story.extend(self.create_frete_deslocamento_section_relatorio_mensal(report_data))
            story.append(Spacer(1, 15))
        
        # Resumo financeiro
        story.extend(self.create_resumo_financeiro_relatorio_mensal(report_data))
        story.append(Spacer(1, 20))
        
        # Assinatura padrão
        story.extend(self.create_assinatura_padrao_relatorio_mensal())
        
        # Construir PDF
        doc.build(story)
        return output_path
    
    def create_header_relatorio_mensal(self, cliente, mes_ano, numeros_os):
        """Criar cabeçalho do relatório mensal"""
        elements = []
        
        # Logo
        logo_path = "img/logo.png"
        if os.path.exists(logo_path):
            try:
                logo = Image(logo_path, width=16.8*cm, height=2.81*cm)
                logo.hAlign = 'CENTER'
                elements.append(logo)
                elements.append(Spacer(1, 15))
            except:
                pass
        
        # Título
        title_style = ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=14,
            alignment=TA_CENTER,
            textColor=self.dark_blue
        )
        elements.append(Paragraph(f"Relatório Mensal - {mes_ano}", title_style))
        elements.append(Spacer(1, 5))
        
        # Subtítulo com números das OS
        subtitle_style = ParagraphStyle(
            name='ReportSubtitle',
            parent=self.styles['Normal'],
            fontSize=10,
            alignment=TA_CENTER,
            textColor=colors.grey
        )
        elements.append(Paragraph(f"Ordens de Serviço: {numeros_os}", subtitle_style))
        
        return elements
    
    def create_client_section_relatorio_mensal(self, cliente):
        """Criar seção de dados do cliente"""
        elements = []
        
        title_style = self.styles['CustomHeading2']
        title_style.alignment = TA_LEFT
        elements.append(Paragraph("Dados do Cliente", title_style))
        
        client_data = [
            ["Nome/Razão Social:", cliente['nome']],
            ["CNPJ/CPF:", formatar_cpf_cnpj(cliente.get('cnpj_cpf', '')) or '-'],
            ["Endereço:", cliente.get('endereco', '') or '-'],
            ["Telefone:", formatar_telefone(cliente.get('telefone', '')) or '-'],
            ["E-mail:", cliente.get('email', '') or '-']
        ]
        
        client_table = Table(client_data, colWidths=[6*cm, 10*cm])
        client_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        
        elements.append(KeepTogether(client_table))
        return elements
    
    def create_services_section_relatorio_mensal(self, report_data):
        """Criar seção de serviços agrupados por local"""
        elements = []
        
        title_style = self.styles['CustomHeading2']
        title_style.alignment = TA_LEFT
        elements.append(Paragraph("Serviços Prestados", title_style))
        
        servicos = report_data.get('servicos', [])
        if not servicos:
            elements.append(Paragraph("Nenhum serviço encontrado.", self.styles['CustomNormal']))
            return elements
        
        # Agrupar serviços por local
        servicos_por_local = {}
        servicos_sem_local = []
        
        for servico in servicos:
            local = servico.get('local')
            if local:
                if local not in servicos_por_local:
                    servicos_por_local[local] = []
                servicos_por_local[local].append(servico)
            else:
                servicos_sem_local.append(servico)
        
        # Verificar se ALGUM serviço tem data (para garantir que todas as tabelas tenham a mesma estrutura)
        tem_data_global = any(s.get('data') for s in servicos)
        
        # Definir larguras fixas para todas as tabelas
        if tem_data_global:
            col_widths = [0.7*cm, 4.5*cm, 1.5*cm, 1.8*cm, 1.5*cm, 2.5*cm, 2.5*cm]
        else:
            col_widths = [0.8*cm, 5*cm, 2*cm, 2*cm, 3*cm, 3*cm]
        
        # Criar tabela para cada local
        for local in sorted(servicos_por_local.keys()):
            servicos_local = servicos_por_local[local]
            
            # Título do local
            local_title = Paragraph(f"<b>Local: {local}</b>", self.styles['CustomHeading3'])
            local_title.alignment = TA_CENTER
            
            # Criar tabela - sempre com a mesma estrutura se tem_data_global
            if tem_data_global:
                services_data = [
                    ["Item", Paragraph("Descrição", self.styles['TableHeader']), 
                     "Local", "Data", "Qtde", 
                     Paragraph("Valor Unit.", self.styles['TableHeader']), 
                     Paragraph("Valor Total (R$)", self.styles['TableHeader'])]
                ]
            else:
                services_data = [
                    ["Item", Paragraph("Descrição", self.styles['TableHeader']), 
                     "Local", "Qtde", 
                     Paragraph("Valor Unit.", self.styles['TableHeader']), 
                     Paragraph("Valor Total (R$)", self.styles['TableHeader'])]
                ]
            
            total_local = 0
            for i, servico in enumerate(servicos_local, 1):
                total_local += servico['total']
                
                local_text = servico.get('local', '') or ''
                if tem_data_global:
                    services_data.append([
                        str(i),
                        Paragraph(servico['nome'], self.styles['CustomNormal']),
                        Paragraph(local_text, self.styles['CustomNormal']),
                        servico.get('data', ''),
                        str(servico['qtd']),
                        f"R$ {servico['preco_unit']:.2f}",
                        f"R$ {servico['total']:.2f}"
                    ])
                else:
                    services_data.append([
                        str(i),
                        Paragraph(servico['nome'], self.styles['CustomNormal']),
                        Paragraph(local_text, self.styles['CustomNormal']),
                        str(servico['qtd']),
                        f"R$ {servico['preco_unit']:.2f}",
                        f"R$ {servico['total']:.2f}"
                    ])
            
            # Linha de total
            if tem_data_global:
                services_data.append(['', '', '', '', '', 'Total', f"R$ {total_local:.2f}"])
                span_cols = (0, -1), (4, -1)
            else:
                services_data.append(['', '', '', '', 'Total', f"R$ {total_local:.2f}"])
                span_cols = (0, -1), (3, -1)
            
            services_table = Table(services_data, colWidths=col_widths)
            services_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), self.dark_blue),
                ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('ALIGN', (len(col_widths)-2, -1), (len(col_widths)-1, -1), 'RIGHT'),
                ('SPAN', span_cols[0], span_cols[1]),
                ('ALIGN', span_cols[0], span_cols[1], 'RIGHT'),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            elements.append(KeepTogether([
                local_title,
                Spacer(1, 0.2*cm),
                services_table
            ]))
            elements.append(Spacer(1, 0.5*cm))
        
        # Serviços sem local (se houver)
        if servicos_sem_local:
            # Usar a mesma estrutura das outras tabelas
            if tem_data_global:
                services_data = [
                    ["Item", Paragraph("Descrição", self.styles['TableHeader']), 
                     "Local", "Data", "Qtde", 
                     Paragraph("Valor Unit.", self.styles['TableHeader']), 
                     Paragraph("Valor Total (R$)", self.styles['TableHeader'])]
                ]
            else:
                services_data = [
                    ["Item", Paragraph("Descrição", self.styles['TableHeader']), 
                     "Local", "Qtde", 
                     Paragraph("Valor Unit.", self.styles['TableHeader']), 
                     Paragraph("Valor Total (R$)", self.styles['TableHeader'])]
                ]
            
            total_sem_local = 0
            for i, servico in enumerate(servicos_sem_local, 1):
                total_sem_local += servico['total']
                
                if tem_data_global:
                    services_data.append([
                        str(i),
                        Paragraph(servico['nome'], self.styles['CustomNormal']),
                        '',  # Local vazio
                        servico.get('data', ''),
                        str(servico['qtd']),
                        f"R$ {servico['preco_unit']:.2f}",
                        f"R$ {servico['total']:.2f}"
                    ])
                else:
                    services_data.append([
                        str(i),
                        Paragraph(servico['nome'], self.styles['CustomNormal']),
                        '',  # Local vazio
                        str(servico['qtd']),
                        f"R$ {servico['preco_unit']:.2f}",
                        f"R$ {servico['total']:.2f}"
                    ])
            
            # Linha de total
            if tem_data_global:
                services_data.append(['', '', '', '', '', 'Total', f"R$ {total_sem_local:.2f}"])
                span_cols = (0, -1), (4, -1)
            else:
                services_data.append(['', '', '', '', 'Total', f"R$ {total_sem_local:.2f}"])
                span_cols = (0, -1), (3, -1)
            
            # Usar as mesmas larguras definidas anteriormente
            services_table = Table(services_data, colWidths=col_widths)
            services_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), self.dark_blue),
                ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('ALIGN', (len(col_widths)-2, -1), (len(col_widths)-1, -1), 'RIGHT'),
                ('SPAN', span_cols[0], span_cols[1]),
                ('ALIGN', span_cols[0], span_cols[1], 'RIGHT'),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            elements.append(KeepTogether(services_table))
        
        return elements
    
    def create_materials_section_relatorio_mensal(self, report_data):
        """Criar seção de materiais"""
        elements = []
        
        title_style = self.styles['CustomHeading2']
        title_style.alignment = TA_LEFT
        elements.append(Paragraph("Materiais Utilizados", title_style))
        
        materiais = report_data.get('materiais', [])
        if not materiais:
            return elements
        
        # Verificar se algum material tem data
        tem_data = any(m.get('data') for m in materiais)
        
        if tem_data:
            materials_data = [
                [Paragraph("Item", self.styles['TableHeader']), 
                 Paragraph("Descrição", self.styles['TableHeader']), 
                 "Data",
                 "Qtde", 
                 Paragraph("Valor Unit.", self.styles['TableHeader']), 
                 Paragraph("Valor Total (R$)", self.styles['TableHeader'])]
            ]
        else:
            materials_data = [
                [Paragraph("Item", self.styles['TableHeader']), 
                 Paragraph("Descrição", self.styles['TableHeader']), 
                 "Qtde", 
                 Paragraph("Valor Unit.", self.styles['TableHeader']), 
                 Paragraph("Valor Total (R$)", self.styles['TableHeader'])]
            ]
        
        total_materiais = 0
        for i, material in enumerate(materiais, 1):
            total_materiais += material['total']
            nome_completo = f"{material['nome']} - {material['marca']}" if material.get('marca') else material['nome']
            
            if tem_data:
                data_material = material.get('data', '') or ''
                materials_data.append([
                    str(i),
                    Paragraph(nome_completo, self.styles['CustomNormal']),
                    data_material,
                    str(material['qtd']),
                    f"R$ {material['preco_unit']:.2f}",
                    f"R$ {material['total']:.2f}"
                ])
            else:
                materials_data.append([
                    str(i),
                    Paragraph(nome_completo, self.styles['CustomNormal']),
                    str(material['qtd']),
                    f"R$ {material['preco_unit']:.2f}",
                    f"R$ {material['total']:.2f}"
                ])
        
        if tem_data:
            materials_data.append(['', '', '', '', 'Total', f"R$ {total_materiais:.2f}"])
            col_widths = [1*cm, 4.5*cm, 2.5*cm, 1.5*cm, 2.5*cm, 3*cm]
            span_cols = (0, -1), (3, -1)  # Mesclar Item até Qtde
        else:
            materials_data.append(['', '', '', 'Total', f"R$ {total_materiais:.2f}"])
            col_widths = [1*cm, 6*cm, 2.5*cm, 3.5*cm, 3.5*cm]
            span_cols = (0, -1), (2, -1)  # Mesclar Item até Qtde
        
        materials_table = Table(materials_data, colWidths=col_widths)
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), self.dark_blue),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('SPAN', span_cols[0], span_cols[1]),
            ('ALIGN', span_cols[0], span_cols[1], 'RIGHT'),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]
        
        table_style.append(('ALIGN', (len(col_widths)-2, -1), (len(col_widths)-1, -1), 'RIGHT'))
        
        materials_table.setStyle(TableStyle(table_style))
        
        elements.append(KeepTogether(materials_table))
        return elements
    
    def create_frete_deslocamento_section_relatorio_mensal(self, report_data):
        """Criar seção de frete/deslocamento em formato de tabela"""
        elements = []
        
        title_style = self.styles['CustomHeading2']
        title_style.alignment = TA_LEFT
        elements.append(Paragraph("Frete/Deslocamento", title_style))
        
        fretes = report_data.get('fretes_deslocamentos', [])
        if not fretes:
            return elements
        
        frete_data = [
            ["Item", 
             Paragraph("Data", self.styles['TableHeader']), 
             "KM", 
             Paragraph("Valor Total (R$)", self.styles['TableHeader'])]
        ]
        
        total_frete = 0
        for i, frete in enumerate(fretes, 1):
            total_frete += frete['valor']
            frete_data.append([
                str(i),
                frete.get('data', ''),
                f"{frete.get('km', 0):.2f}",
                f"R$ {frete['valor']:.2f}"
            ])
        
        frete_data.append(['', '', 'Total', f"R$ {total_frete:.2f}"])
        
        frete_table = Table(frete_data, colWidths=[1*cm, 4*cm, 3*cm, 4*cm])
        frete_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.dark_blue),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('ALIGN', (2, -1), (3, -1), 'CENTER'),
            ('SPAN', (0, -1), (1, -1)),
            ('ALIGN', (0, -1), (1, -1), 'RIGHT'),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (2, 0), (2, -2), 'CENTER'),
            ('ALIGN', (3, 0), (3, -2), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        
        elements.append(KeepTogether(frete_table))
        return elements
    
    def create_resumo_financeiro_relatorio_mensal(self, report_data):
        """Criar resumo financeiro do relatório mensal"""
        elements = []
        
        title_style = self.styles['CustomHeading2']
        title_style.alignment = TA_CENTER
        elements.append(Paragraph("Resumo Financeiro", title_style))
        
        totais = report_data['totais']
        
        composition_data = [
            ["(+) Serviços", f"R$ {totais['servicos']:.2f}"],
            ["(+) Materiais", f"R$ {totais['materiais']:.2f}"],
        ]
        
        if totais['deslocamento'] > 0:
            composition_data.append(["(+) Frete/Deslocamento", f"R$ {totais['deslocamento']:.2f}"])
        
        if totais['impostos'] > 0:
            composition_data.append(["(+) Impostos", f"R$ {totais['impostos']:.2f}"])
        
        if totais['bdi'] > 0:
            composition_data.append(["(+) BDI", f"R$ {totais['bdi']:.2f}"])
        
        if totais['descontos'] > 0:
            composition_data.append(["(-) Descontos", f"R$ {totais['descontos']:.2f}"])
        
        composition_data.extend([
            ["", ""],
            ["TOTAL GERAL:", f"R$ {totais['geral']:.2f}"]
        ])
        
        composition_table = Table(composition_data, colWidths=[12*cm, 4*cm])
        composition_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -2), 10),
            ('FONTSIZE', (0, -1), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LINEBELOW', (0, -2), (-1, -2), 1, colors.black),
            ('LINEBELOW', (0, -1), (-1, -1), 2, colors.black),
        ]))
        
        elements.append(KeepTogether(composition_table))
        return elements
    
    def create_assinatura_padrao_relatorio_mensal(self):
        """Criar seção de assinatura padrão para o relatório mensal"""
        elements = []
        elements.append(Spacer(1, 20))
        
        # Buscar assinatura padrão
        assinatura_path = None
        assinatura_nome = None
        assinatura_cargo = None
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Adicionar coluna cargo se não existir (migração)
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
            except:
                pass
            
            # Buscar assinatura padrão
            cursor.execute('''
                SELECT caminho_imagem, nome, cargo FROM assinaturas WHERE padrao = true AND ativo = true LIMIT 1
            ''')
            result = cursor.fetchone()
            if result:
                assinatura_path = result['caminho_imagem']
                assinatura_nome = result['nome']
                assinatura_cargo = result.get('cargo') if 'cargo' in result else 'Técnico Eletricista Industrial/Residencial'
            conn.close()
        except Exception as e:
            print(f"Erro ao buscar assinatura padrão: {e}")
        
        # Ajustar caminho da imagem se necessário
        if assinatura_path:
            # Verificar se o caminho está na pasta uploads/assinaturas
            if not os.path.exists(assinatura_path):
                # Tentar ajustar o caminho
                if 'uploads/assinaturas/' in assinatura_path or assinatura_path.startswith('uploads/'):
                    # Tentar encontrar na pasta uploads
                    filename = assinatura_path.replace('uploads/', '')
                    if os.path.exists(os.path.join('uploads', filename)):
                        assinatura_path = os.path.join('uploads', filename)
                elif 'assinaturas/' in assinatura_path or ('/' not in assinatura_path and not assinatura_path.startswith('uploads/')):
                    # Tentar encontrar na pasta assinaturas (legado)
                    filename = assinatura_path.replace('assinaturas/', '') if 'assinaturas/' in assinatura_path else assinatura_path
                    if os.path.exists(os.path.join('assinaturas', filename)):
                        assinatura_path = os.path.join('assinaturas', filename)
        
        # Se encontrou assinatura padrão (nome), exibir
        if assinatura_nome:
            # Texto da assinatura
            nome_texto = assinatura_nome if assinatura_nome else ""
            cargo_texto = assinatura_cargo if assinatura_cargo else 'Técnico Eletricista Industrial/Residencial'
            
            # Se encontrou a imagem, tentar carregar
            if assinatura_path and os.path.exists(assinatura_path):
                try:
                    # Carregar e redimensionar imagem mantendo proporção
                    target_width = 8.0 * cm
                    
                    img = Image(assinatura_path)
                    original_width = img.imageWidth
                    original_height = img.imageHeight
                    
                    # Calcular proporção para manter aspecto
                    ratio = target_width / original_width
                    new_height = original_height * ratio
                    
                    img = Image(assinatura_path, width=target_width, height=new_height)
                    img.hAlign = 'CENTER'
                    
                    # Adicionar imagem
                    elements.append(Spacer(1, 5))
                    elements.append(img)
                    elements.append(Spacer(1, -5))
                    
                except Exception as e:
                    print(f"Erro ao carregar imagem de assinatura: {e}")
                    # Se falhar, usar linha de assinatura padrão
                    assinatura_style = ParagraphStyle(
                        name='SignatureLine',
                        parent=self.styles['Normal'],
                        fontSize=10,
                        alignment=TA_CENTER
                    )
                    assinatura_p = Paragraph("_" * 50, assinatura_style)
                    elements.append(assinatura_p)
            else:
                # Se não tem imagem, usar linha de assinatura padrão
                assinatura_style = ParagraphStyle(
                    name='SignatureLine',
                    parent=self.styles['Normal'],
                    fontSize=10,
                    alignment=TA_CENTER
                )
                assinatura_p = Paragraph("_" * 50, assinatura_style)
                elements.append(assinatura_p)
            
            # Adicionar texto abaixo da assinatura
            nome_style = ParagraphStyle(
                name='SignatureText',
                parent=self.styles['Normal'],
                fontSize=10,
                alignment=TA_CENTER,
                leading=12
            )
            
            line_width = 8 * cm
            p_text = Paragraph(f"<b>{nome_texto}</b><br/>{cargo_texto}", nome_style)
            
            sig_table = Table([[p_text]], colWidths=[line_width])
            sig_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('LINEABOVE', (0, 0), (-1, 0), 0.5, colors.black),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            sig_table.hAlign = 'CENTER'
            elements.append(KeepTogether(sig_table))
        else:
            # Se não encontrou assinatura padrão, apenas adicionar espaço
            elements.append(Spacer(1, 30))
        
        return elements
