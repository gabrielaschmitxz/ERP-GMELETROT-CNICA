from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import psycopg2.extras
from reportlab.lib.units import cm, inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
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
        
        # Estilo do texto normal
        self.styles.add(ParagraphStyle(
            name='CustomNormal',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=6
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

        # Materiais
        story.extend(self.create_materials_section(order_data))
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
        report_title_style = ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=12,
            alignment=TA_CENTER,
            textColor=self.dark_blue
        )
        elements.append(Paragraph("Relatório - Ordem de Serviço", report_title_style))
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
                
                elements.append(client_table)
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
            services_data = [["Item", "Descrição do Serviço", "Quantidade", "Valor Unitário (R$)", "Valor Total (R$)"]]
            
            for i, servico in enumerate(order_data['servicos'], 1):
                # Formatar descrição para incluir horas e taxa se existirem
                desc_text = servico['nome']
                if servico.get('tempo') and servico.get('taxa'):
                    t_val = float(servico['tempo'])
                    t_str = f"{int(t_val)}" if t_val.is_integer() else f"{t_val}"
                    desc_text += f" - Tempo: {t_str}h x Taxa: R$ {servico['taxa']:.2f}/h"
                
                # Usar Paragraph para permitir quebra de linha se o texto for longo
                services_data.append([
                    str(i),
                    Paragraph(desc_text, self.styles['CustomNormal']),
                    str(servico['qtd']),
                    f"R$ {servico['preco_unit']:.2f}",
                    f"R$ {servico['total']:.2f}"
                ])
                total_servicos += servico['total']

            # Linha de total
            services_data.append(['', '', '', 'Total de Serviços', f"R$ {total_servicos:.2f}"])
            
            services_table = Table(services_data, colWidths=[1*cm, 6*cm, 2.5*cm, 3.5*cm, 3.5*cm])
            services_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), self.dark_blue),
                ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('ALIGN', (3, -1), (4, -1), 'RIGHT'),
                ('SPAN', (0, -1), (2, -1)), # Mesclar células do total
                ('ALIGN', (0, -1), (2, -1), 'RIGHT'),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            elements.append(services_table)
        else:
            elements.append(Paragraph("Nenhum serviço cadastrado.", self.styles['CustomNormal']))
            
        return elements
        
    def create_materials_section(self, order_data):
        """Criar seção de materiais"""
        elements = []
        total_materiais = 0.0
        
        title_style = self.styles['CustomHeading2']
        title_style.alignment = TA_CENTER
        elements.append(Paragraph("Materiais", title_style)) # Título da seção
        
        if order_data.get('materiais'):
            materials_data = [["Item", "Descrição do Material", "Quantidade", "Valor Unitário (R$)", "Valor Total (R$)"]]
            
            for i, material in enumerate(order_data['materiais'], 1):
                nome_completo = f"{material['nome']} - {material['marca']}" if material['marca'] else material['nome']
                materials_data.append([
                    str(i),
                    nome_completo,
                    str(material['qtd']),
                    f"R$ {material['preco_unit']:.2f}",
                    f"R$ {material['total']:.2f}"
                ])
                total_materiais += material['total']

            # Linha de total
            materials_data.append(['', '', '', 'Total de Materiais', f"R$ {total_materiais:.2f}"])
            
            materials_table = Table(materials_data, colWidths=[1*cm, 6*cm, 2.5*cm, 3.5*cm, 3.5*cm])
            materials_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), self.dark_blue),
                ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('ALIGN', (3, -1), (4, -1), 'RIGHT'),
                ('SPAN', (0, -1), (2, -1)), # Mesclar células do total
                ('ALIGN', (0, -1), (2, -1), 'RIGHT'),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            elements.append(materials_table)
        else:
            elements.append(Paragraph("Nenhum material cadastrado.", self.styles['CustomNormal']))
            
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
            elements.append(impostos_table)
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
            elements.append(bdi_table)
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
        deslocamento_total = order_data.get('distance_data', {}).get('displacement_cost', 0) if order_data.get('distance_data') else 0
        
        adicionais = order_data.get('adicionais', [])
        impostos_total = sum(a['valor'] for a in adicionais if a['tipo'] == 'imposto')
        bdi_total = sum(a['valor'] for a in adicionais if a['tipo'] == 'bdi')
        descontos_total = sum(a['valor'] for a in adicionais if a['tipo'] == 'desconto')

        total_geral = (servicos_total + materiais_total + deslocamento_total + 
                       impostos_total + bdi_total - descontos_total)
        
        composition_data = [
            ["(+) Materiais", f"R$ {materiais_total:.2f}"],
            ["(+) Serviços", f"R$ {servicos_total:.2f}"],
            ["(+) Deslocamento", f"R$ {deslocamento_total:.2f}"],            
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
        elements.append(composition_table)
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
                elements.append(sig_table)
                
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
