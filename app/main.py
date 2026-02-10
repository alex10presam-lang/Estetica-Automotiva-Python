# 1. Bibliotecas padrão do Python
import os
import io
import shutil
from datetime import datetime
from typing import Optional, List

# FastAPI e Respostas
from fastapi import FastAPI, Request, Depends, Form, Response, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# Banco de Dados
from sqlalchemy.orm import Session
from app.database import engine, get_db
from app import models

# ReportLab (Geração de PDF)
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.colors import HexColor

# Cria as tabelas no banco se não existirem
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Configuração de Pastas
templates = Jinja2Templates(directory="app/templates")

# Garante que a pasta de uploads existe
if not os.path.exists("app/static/uploads"):
    os.makedirs("app/static/uploads")

app.mount("/static", StaticFiles(directory="app/static"), name="static")



# --- ROTA DO DASHBOARD (HOME) ---
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    # Busca lavagens em aberto e concluídas
    lavagens = db.query(models.Lavagem).order_by(models.Lavagem.id.desc()).all()

    # Busca produtos para o formulário antigo (se ainda usar)
    produtos_disponiveis = db.query(models.Produto).all()

    # NOVO: Busca os últimos 10 clientes para a barra superior
    clientes_recentes = db.query(models.Cliente).order_by(models.Cliente.id.desc()).limit(10).all()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "lavagens": lavagens,
        "produtos_disponiveis": produtos_disponiveis,
        "clientes_recentes": clientes_recentes  # <-- Importante para a barra superior
    })


@app.post("/lavagens/registrar")
async def registrar_nova_lavagem(
    modo_cliente: str = Form(...),
    veiculo_id: Optional[int] = Form(None),
    nome: Optional[str] = Form(None),
    telefone: Optional[str] = Form(None),
    marca: Optional[str] = Form(None),
    modelo: Optional[str] = Form(None),
    placa: Optional[str] = Form(None),
    categoria: Optional[str] = Form(None),
    servico_id: int = Form(...),
    tipo_sujeira: float = Form(0.0),
    obs_entrada: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    # --- 1. IDENTIFICAÇÃO DO VEÍCULO ---
    if modo_cliente == "existente":
        v_id = veiculo_id
    else:
        cliente = db.query(models.Cliente).filter(models.Cliente.telefone == telefone).first()
        if not cliente:
            cliente = models.Cliente(nome=nome, telefone=telefone)
            db.add(cliente)
            db.flush()

        veiculo = db.query(models.Veiculo).filter(models.Veiculo.placa == placa.upper()).first()
        if not veiculo:
            veiculo = models.Veiculo(marca=marca, modelo=modelo, placa=placa.upper(), categoria=categoria, cliente_id=cliente.id)
            db.add(veiculo)
            db.flush()
        v_id = veiculo.id

    # --- 2. PRECIFICAÇÃO ---
    servico_base = db.query(models.ServicoCatalogo).filter(models.ServicoCatalogo.id == servico_id).first()
    veiculo_obj = db.query(models.Veiculo).filter(models.Veiculo.id == v_id).first()
    cat = veiculo_obj.categoria.lower() if veiculo_obj.categoria else "hatch"

    precos = {
        "hatch": servico_base.preco_hatch,
        "sedan": servico_base.preco_sedan,
        "suv": servico_base.preco_suv,
        "pickup": servico_base.preco_pickup
    }
    valor_base = precos.get(cat, servico_base.preco_hatch)

    # --- 3. CRIAÇÃO DA LAVAGEM ---
    nova_lavagem = models.Lavagem(
        veiculo_id=v_id,
        servico_id=servico_id,
        valor_total=valor_base + tipo_sujeira, # Preço final sugerido salvo aqui
        tipo_sujeira=f"Adicional: R$ {tipo_sujeira}",
        checklist_avarias=obs_entrada,
        status="em_andamento",
        data_inicio=datetime.now() # <--- CORREÇÃO: Horário local
    )
    db.add(nova_lavagem)
    db.commit()
    return RedirectResponse(url="/", status_code=303)



@app.get("/lavagem/{lavagem_id}/checklist", response_class=HTMLResponse)
async def exibir_form_checklist(lavagem_id: int, request: Request, db: Session = Depends(get_db)):
    lavagem = db.query(models.Lavagem).get(lavagem_id)
    if not lavagem:
        raise HTTPException(status_code=404, detail="Lavagem não encontrada")
    # Certifique-se de que o nome do arquivo é checklist_form.html ou checklist.html
    return templates.TemplateResponse("checklist_form.html", {"request": request, "l": lavagem})

# --- ADICIONE ESTA ROTA PARA SALVAR O VALOR DA HORA ---
@app.post("/gestao/configurar_hora")
async def configurar_hora(valor_hora: float = Form(...), db: Session = Depends(get_db)):
    config = db.query(models.Configuracao).first()
    if not config:
        config = models.Configuracao(valor_hora=valor_hora)
        db.add(config)
    else:
        config.valor_hora = valor_hora
    db.commit()
    return RedirectResponse(url="/gestao", status_code=303)

@app.get("/lavagem/{id}/finalizar")
async def tela_finalizar(id: int, request: Request, db: Session = Depends(get_db)):
    lavagem = db.query(models.Lavagem).get(id)
    config = db.query(models.Configuracao).first()
    valor_hora = config.valor_hora if config else 0.0

    # 1. Cálculo de Tempo Real (Usando datetime.now() para bater com a entrada)
    tempo_decorrido = datetime.now() - lavagem.data_inicio
    minutos = max(tempo_decorrido.total_seconds() / 60, 0)
    custo_tempo = minutos * (valor_hora / 60)

    # 2. Custo de Insumos
    custo_produtos = 0.0
    if lavagem.servico:
        for p in lavagem.servico.produtos_fixos:
            if p.ml_total and p.ml_total > 0:
                custo_produtos += (p.preco_compra / p.ml_total) * p.ml_por_uso

    # 3. CORREÇÃO: Sugestão é o que foi gravado na entrada (40, 45, 50...)
    # Não somamos o custo_tempo no preço do cliente!
    sugestao = lavagem.valor_total or 0.0

    return templates.TemplateResponse("finalizar.html", {
        "request": request,
        "lavagem": lavagem,
        "sugestao": round(sugestao, 2),
        "custo_tempo": round(custo_tempo, 2),
        "custo_produtos": round(custo_produtos, 2)
    })


# --- ROTA DE FINALIZAÇÃO ATUALIZADA (COM RELATÓRIO DE ENTREGA) ---
@app.post("/lavagens/{lavagem_id}/finalizar")
async def finalizar_lavagem(
        lavagem_id: int,
        valor_final_cobrado: float = Form(...),
        produtos_ids: Optional[List[int]] = Form(None),
        foto_antes: Optional[UploadFile] = File(None),
        foto_depois: Optional[UploadFile] = File(None),
        db: Session = Depends(get_db)
):
    lavagem = db.query(models.Lavagem).filter(models.Lavagem.id == lavagem_id).first()
    config = db.query(models.Configuracao).first()
    valor_hora = config.valor_hora if config else 0.0

    # 1. CÁLCULO DE TEMPO (Sincronizado)
    lavagem.data_fim = datetime.now()
    duracao = lavagem.data_fim - lavagem.data_inicio
    segundos_totais = max(duracao.total_seconds(), 0)
    custo_mao_de_obra = (segundos_totais / 3600) * valor_hora

    # 2. CÁLCULO DE PRODUTOS
    custo_total_produtos = 0.0
    nomes_produtos = []
    if produtos_ids:
        for p_id in produtos_ids:
            produto = db.query(models.Produto).get(p_id)
            if produto and produto.ml_total > 0:
                custo_dose = (produto.preco_compra / produto.ml_total) * produto.ml_por_uso
                custo_total_produtos += custo_dose
                nomes_produtos.append(produto.nome)

    # 3. SALVAMENTO DE FOTOS (ENTRADA E SAÍDA)
    # Criamos pastas separadas para organizar melhor o servidor
    UPLOAD_DIR = "app/static/uploads/entregas"
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Processamos as fotos (Antes e Depois)
    for tipo, arquivo in [("entrada", foto_antes), ("saida", foto_depois)]:
        if arquivo and arquivo.filename:
            extensao = arquivo.filename.split(".")[-1]
            timestamp = int(datetime.utcnow().timestamp())
            nome_arquivo = f"{tipo}_{lavagem_id}_{timestamp}.{extensao}"
            caminho_completo = os.path.join(UPLOAD_DIR, nome_arquivo)

            with open(caminho_completo, "wb") as buffer:
                shutil.copyfileobj(arquivo.file, buffer)

            # Ajuste de nomes para bater com o banco de dados e templates
                # CORREÇÃO AQUI: Alinhando com os nomes das colunas do Models.py
                if tipo == "entrada":
                    lavagem.foto_entrada_url = f"static/uploads/entregas/{nome_arquivo}"
                else:
                    lavagem.foto_saida_url = f"static/uploads/entregas/{nome_arquivo}"

    # 4. ATUALIZAÇÃO DOS DADOS FINANCEIROS
    lavagem.status = "concluida"
    lavagem.produtos_usados = ", ".join(nomes_produtos) if nomes_produtos else "Insumos padrão DJ WASH"
    lavagem.custo_insumos = round(custo_total_produtos, 2)
    lavagem.custo_mao_de_obra = round(custo_mao_de_obra, 2)
    lavagem.valor_total = valor_final_cobrado

    # Cálculo do Lucro Real (Faturamento - Insumos - Mão de Obra)
    lavagem.lucro_real = round(valor_final_cobrado - (custo_total_produtos + custo_mao_de_obra), 2)

    # Formatação do tempo total para o recibo (HH:MM)
    minutos_totais = int(segundos_totais / 60)
    lavagem.tempo_total = f"{minutos_totais // 60:02d}:{minutos_totais % 60:02d}"

    db.commit()
    # Redireciona para o relatório de entrega (Antes e Depois)
    return RedirectResponse(url=f"/lavagem/{lavagem_id}/recibo_final", status_code=303)


@app.get("/lavagem/{lavagem_id}/comprovante_entrada", response_class=HTMLResponse)
async def comprovante_entrada(lavagem_id: int, request: Request, db: Session = Depends(get_db)):
    lavagem = db.query(models.Lavagem).filter(models.Lavagem.id == lavagem_id).first()
    if not lavagem:
        return "Lavagem não encontrada"

    return templates.TemplateResponse("comprovante_entrada.html", {
        "request": request,
        "l": lavagem
    })


@app.post("/lavagem/{lavagem_id}/checklist")
async def salvar_checklist_modal(
        lavagem_id: int,
        combustivel: Optional[str] = Form("Não informado"),
        avarias: Optional[str] = Form(None),
        fotos_checklist: List[UploadFile] = File([]),  # Recebe lista de fotos
        db: Session = Depends(get_db)
):
    lavagem = db.query(models.Lavagem).get(lavagem_id)
    lavagem.checklist_combustivel = combustivel

    # Processamento de Múltiplas Fotos
    caminhos_fotos = []
    if fotos_checklist:
        UPLOAD_DIR = "app/static/uploads/checklists"
        os.makedirs(UPLOAD_DIR, exist_ok=True)

        for foto in fotos_checklist:
            if foto.filename:
                ext = foto.filename.split(".")[-1]
                nome_arquivo = f"avaria_{lavagem_id}_{int(datetime.utcnow().timestamp())}_{os.urandom(4).hex()}.{ext}"
                caminho = os.path.join(UPLOAD_DIR, nome_arquivo)

                with open(caminho, "wb") as buffer:
                    shutil.copyfileobj(foto.file, buffer)

                caminhos_fotos.append(f"static/uploads/checklists/{nome_arquivo}")

    # Salvando os caminhos no banco (usando um campo de texto separado por vírgula)
    if caminhos_fotos:
        lavagem.foto_entrada_url = ",".join(caminhos_fotos)

    lavagem.checklist_avarias = avarias
    db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.get("/lavagem/{lavagem_id}/recibo_final", response_class=HTMLResponse)
async def visualizar_relatorio_final(lavagem_id: int, request: Request, db: Session = Depends(get_db)):
    lavagem = db.query(models.Lavagem).get(lavagem_id)
    if not lavagem:
        raise HTTPException(status_code=404, detail="Lavagem não encontrada")

    return templates.TemplateResponse("recibo_final.html", {
        "request": request,
        "l": lavagem
    })


@app.get("/lavagens/{lavagem_id}/dados-finalizacao")
async def dados_finalizacao(lavagem_id: int, db: Session = Depends(get_db)):
    lavagem = db.query(models.Lavagem).get(lavagem_id)
    if not lavagem:
        raise HTTPException(status_code=404, detail="Lavagem não encontrada")

    # 1. Cálculo de Tempo (Sincronizado com o horário local)
    agora = datetime.now()
    delta = agora - lavagem.data_inicio
    # max(..., 0) evita que o tempo fique negativo caso haja pequena variação de segundos
    minutos_totais = max(int(delta.total_seconds() / 60), 0)

    # 2. Busca Valor da Hora para cálculo interno de custo
    config = db.query(models.Configuracao).first()
    valor_hora = config.valor_hora if config else 0.0
    custo_mao_de_obra = (minutos_totais / 60) * valor_hora

    # 3. Lista de Produtos
    todos_produtos = db.query(models.Produto).all()
    lista_produtos_json = []
    for p in todos_produtos:
        dose = (p.preco_compra / p.ml_total * p.ml_por_uso) if p.ml_total > 0 else 0
        lista_produtos_json.append({
            "id": p.id,
            "nome": p.nome,
            "custo_por_dose": dose
        })

        valor_base = float(lavagem.valor_total or 0.0)
        valor_sugerido = valor_base + custo_mao_de_obra

        return {
            "minutos": minutos_totais,
            "valor_base": round(valor_base, 2),  # O JS estava travando aqui porque faltava essa linha
            "custo_mao_de_obra": round(custo_mao_de_obra, 2),
            "sugerido": round(valor_sugerido, 2),
            "todos_produtos": lista_produtos_json
        }

@app.get("/clientes/{cliente_id}/historico")
async def historico_especifico_cliente(cliente_id: int, db: Session = Depends(get_db)):
    # Agora o nome do argumento 'cliente_id' coincide com o da rota {cliente_id}
    historico = db.query(models.Lavagem).join(models.Veiculo).filter(
        models.Veiculo.cliente_id == cliente_id,
        models.Lavagem.status == "concluida"
    ).order_by(models.Lavagem.data_fim.desc()).all()

    return historico


@app.get("/lavagem/{lavagem_id}/detalhes", response_class=HTMLResponse)
async def detalhes_lavagem(lavagem_id: int, request: Request, db: Session = Depends(get_db)):
    lavagem = db.query(models.Lavagem).get(lavagem_id)
    if not lavagem:
        raise HTTPException(status_code=404, detail="Lavagem não encontrada")

    # Separar fotos de avarias (Vistoria) das fotos de entrega (Antes/Depois)
    fotos_avarias = []
    foto_antes_entrega = None

    if lavagem.foto_entrada_url:
        lista_fotos = [f.strip() for f in lavagem.foto_entrada_url.split(",")]
        # Fotos que estão na pasta checklists são avarias
        fotos_avarias = [f for f in lista_fotos if "checklists" in f]
        # A foto de "Antes" tirada na finalização está na pasta entregas
        foto_antes_entrega = next((f for f in lista_fotos if "entregas" in f), None)

    return templates.TemplateResponse("detalhes_lavagem.html", {
        "request": request,
        "l": lavagem,
        "fotos_avarias": fotos_avarias,
        "foto_antes": foto_antes_entrega
    })


@app.get("/historico", response_class=HTMLResponse)
async def historico_financeiro(request: Request, db: Session = Depends(get_db)):
    lavagens = db.query(models.Lavagem).filter(models.Lavagem.status == "concluida").all()

    total_faturado = sum(l.valor_total for l in lavagens if l.valor_total) or 0.0
    total_produtos = sum(l.custo_insumos for l in lavagens if l.custo_insumos) or 0.0
    total_mao_obra = sum(l.custo_mao_de_obra for l in lavagens if l.custo_mao_de_obra) or 0.0

    # Cálculos de Inteligência
    qtd_servicos = len(lavagens)
    ticket_medio = total_faturado / qtd_servicos if qtd_servicos > 0 else 0.0

    # Dados para o Gráfico (Exemplo simples: faturamento por serviço)
    labels_grafico = [l.data_fim.strftime('%d/%m') for l in lavagens[-7:]]
    valores_grafico = [float(l.valor_total or 0) for l in lavagens[-7:]]

    return templates.TemplateResponse("historico.html", {
        "request": request,
        "lavagens": lavagens[::-1],  # Inverte para mostrar as mais recentes primeiro
        "total_faturado": total_faturado,
        "total_produtos": total_produtos,
        "total_mao_obra": total_mao_obra,
        "ticket_medio": ticket_medio,
        "labels_grafico": labels_grafico,
        "valores_grafico": valores_grafico
    })
# --- ROTA DE GERAÇÃO DE RECIBO PREMIUM DJ WASH ---
@app.get("/lavagens/{lavagem_id}/recibo")
async def gerar_recibo(lavagem_id: int, db: Session = Depends(get_db)):
    lavagem = db.query(models.Lavagem).filter(models.Lavagem.id == lavagem_id).first()
    if not lavagem:
        return {"erro": "Lavagem não encontrada"}

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    largura, altura = A4

    # Paleta de Cores DJ WASH
    cor_roxo_dark = HexColor("#1A052D")  # Fundo Profundo
    cor_roxo_vibrante = HexColor("#6A1B9A")  # Destaques
    cor_gold = HexColor("#D4AF37")  # Dourado Premium
    cor_texto = HexColor("#333333")

    # --- 1. DESIGN DO CABEÇALHO (BANNER) ---
    pdf.setFillColor(cor_roxo_dark)
    pdf.rect(0, altura - 120, largura, 120, fill=1, stroke=0)

    # Detalhe em dourado no topo
    pdf.setFillColor(cor_gold)
    pdf.rect(0, altura - 5, largura, 5, fill=1, stroke=0)

    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 28)
    pdf.drawString(50, altura - 60, "DJ WASH")

    pdf.setFont("Helvetica", 10)
    pdf.drawString(50, altura - 80, "ESTÉTICA AUTOMOTIVA")

    # ID do Recibo no canto superior
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawRightString(largura - 50, altura - 60, f"RECIBO Nº {lavagem.id:04d}")
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(largura - 50, altura - 80, f"Emissão: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    # --- 2. INFORMAÇÕES DO CLIENTE E VEÍCULO ---
    y = altura - 160
    pdf.setFillColor(cor_roxo_vibrante)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "INFORMAÇÕES DO CLIENTE")

    pdf.setStrokeColor(cor_roxo_vibrante)
    pdf.setLineWidth(1)
    pdf.line(50, y - 5, largura - 50, y - 5)

    pdf.setFillColor(cor_texto)
    pdf.setFont("Helvetica-Bold", 10)
    y -= 25
    pdf.drawString(50, y, "CLIENTE:")
    pdf.drawString(300, y, "VEÍCULO:")

    pdf.setFont("Helvetica", 10)
    pdf.drawString(105, y, f"{lavagem.veiculo.cliente.nome}")
    pdf.drawString(355, y, f"{lavagem.veiculo.modelo} ({lavagem.veiculo.marca})")

    y -= 15
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(50, y, "TELEFONE:")
    pdf.drawString(300, y, "PLACA:")

    pdf.setFont("Helvetica", 10)
    pdf.drawString(115, y, f"{lavagem.veiculo.cliente.telefone}")
    pdf.drawString(350, y, f"{lavagem.veiculo.placa}")

    # --- 3. DETALHAMENTO DO SERVIÇO E PRODUTOS ---
    y -= 40
    pdf.setFillColor(cor_roxo_vibrante)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "DETALHES DO SERVIÇO REALIZADO")
    pdf.line(50, y - 5, largura - 50, y - 5)

    y -= 25
    pdf.setFillColor(cor_texto)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(50, y, "SERVIÇO:")

    pdf.setFont("Helvetica", 10)
    nome_servico = "Lavagem Geral / Detalhada"
    if hasattr(lavagem, 'servico_id') and lavagem.servico_id:
        servico_db = db.query(models.ServicoCatalogo).filter(models.ServicoCatalogo.id == lavagem.servico_id).first()
        if servico_db: nome_servico = servico_db.nome
    pdf.drawString(105, y, f"{nome_servico}")

    y -= 20
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(50, y, "PRODUTOS UTILIZADOS:")

    y -= 15
    pdf.setFont("Helvetica-Oblique", 9)
    # Quebra de texto automática para produtos longos
    produtos_texto = lavagem.produtos_usados if lavagem.produtos_usados else "Insumos profissionais biodegradáveis (Padrão DJ WASH)"
    pdf.drawString(60, y, f"- {produtos_texto}")

    # --- 4. QUADRO FINANCEIRO (TAXAS E TOTAL) ---
    y -= 50
    # Caixa de fundo para o total
    pdf.setFillColor(HexColor("#F9F9F9"))
    pdf.roundRect(50, y - 80, largura - 100, 90, 5, fill=1, stroke=1)

    pdf.setFillColor(cor_texto)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(70, y - 15, "RESUMO FINANCEIRO")

    pdf.setFont("Helvetica", 10)
    pdf.drawString(70, y - 35, "Valor Base do Serviço:")
    pdf.drawRightString(largura - 70, y - 35, f"R$ {lavagem.valor_total:.2f}")

    # Aqui listamos as taxas (se você tiver campos de taxas extras no futuro, aparecem aqui)
    pdf.drawString(70, y - 50, "Taxas Adicionais / Descontos:")
    pdf.drawRightString(largura - 70, y - 50, "R$ 0,00")

    pdf.setStrokeColor(colors.lightgrey)
    pdf.line(70, y - 58, largura - 70, y - 58)

    # Valor Total Destacado
    pdf.setFillColor(cor_roxo_dark)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(70, y - 75, "VALOR TOTAL PAGO")

    pdf.setFillColor(cor_gold)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawRightString(largura - 70, y - 75, f"R$ {lavagem.valor_total:.2f}")

    # --- 5. RODAPÉ ---
    y_final = 100
    pdf.setFillColor(cor_roxo_vibrante)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawCentredString(largura / 2, y_final, "Obrigado por confiar na DJ WASH!")

    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(colors.grey)
    pdf.drawCentredString(largura / 2, y_final - 15,
                          "O QR Code para pagamento e a chave PIX foram enviados via mensagem.")
    pdf.drawCentredString(largura / 2, y_final - 28, "Siga-nos no Instagram: @_djwash_")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return Response(
        content=buffer.read(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=Recibo_DJWASH_{lavagem.id}.pdf"}
    )
# --- ROTAS DE GESTÃO E CONFIGURAÇÃO ---
@app.get("/gestao", response_class=HTMLResponse)
async def pagina_gestao(request: Request, db: Session = Depends(get_db)):
    produtos = db.query(models.Produto).all()
    servicos = db.query(models.ServicoCatalogo).all()
    custos_fixos = db.query(models.CustoFixo).all()
    config = db.query(models.Configuracao).first()
    return templates.TemplateResponse("gestao.html", {
        "request": request,
        "produtos": produtos,
        "servicos": servicos,
        "custos": custos_fixos,
        "config": config
    })


@app.post("/gestao/produto")
async def salvar_produto(nome: str = Form(...), preco: float = Form(...), ml_total: int = Form(...),
                         ml_uso: int = Form(...), db: Session = Depends(get_db)):
    novo = models.Produto(nome=nome, preco_compra=preco, ml_total=ml_total, ml_por_uso=ml_uso)
    db.add(novo)
    db.commit()
    return RedirectResponse(url="/gestao", status_code=303)


@app.get("/cliente/{cliente_id}/historico", response_class=HTMLResponse)
async def historico_cliente(request: Request, cliente_id: int, db: Session = Depends(get_db)):
    cliente = db.query(models.Cliente).filter(models.Cliente.id == cliente_id).first()

    # Busca todas as lavagens dos veículos deste cliente
    lavagens = db.query(models.Lavagem).join(models.Veiculo).filter(models.Veiculo.cliente_id == cliente_id).order_by(
        models.Lavagem.data_inicio.desc()).all()
    total_pago = sum(l.valor_total or 0 for l in lavagens)

    return templates.TemplateResponse("perfil_cliente.html", {
        "request": request,
        "cliente": cliente,
        "lavagens": lavagens,
        "total_pago": f"{total_pago:.2f}"
    })


@app.post("/gestao/servico")
async def salvar_servico_catalogo(
        nome: str = Form(...),
        hatch: float = Form(0.0),
        sedan: float = Form(0.0),
        suv: float = Form(0.0),
        # Captura a lista de IDs selecionados no <select multiple>
        produtos_fixos_ids: List[int] = Form([]),
        db: Session = Depends(get_db)
):
    # 1. Cria o objeto do serviço
    servico = models.ServicoCatalogo(
        nome=nome,
        preco_hatch=hatch,
        preco_sedan=sedan,
        preco_suv=suv,
        preco_pickup=0.0
    )

    # 2. Busca os produtos selecionados e adiciona ao serviço
    if produtos_fixos_ids:
        produtos_selecionados = db.query(models.Produto).filter(models.Produto.id.in_(produtos_fixos_ids)).all()
        servico.produtos_fixos = produtos_selecionados

    db.add(servico)
    db.commit()
    return RedirectResponse(url="/gestao", status_code=303)


@app.post("/gestao/custofixo")
async def salvar_custo_fixo(item: str = Form(...), valor: float = Form(...), db: Session = Depends(get_db)):
    nova_despesa = models.CustoFixo(item=item, valor=valor)
    db.add(nova_despesa)
    db.commit()
    return RedirectResponse(url="/gestao", status_code=303)

@app.get("/clientes_gestao", response_class=HTMLResponse) # Adicione o response_class
async def gerenciar_clientes(request: Request, db: Session = Depends(get_db)): # Adicione o request aqui
    clientes = db.query(models.Cliente).all()
    hoje = datetime.utcnow()

    # Adicionamos a lógica de "Dias desde a última lavagem" para cada cliente
    for cliente in clientes:
        ultima_lavagem = None
        for veiculo in cliente.veiculos:
            lavagem = db.query(models.Lavagem).filter(
                models.Lavagem.veiculo_id == veiculo.id,
                models.Lavagem.status == 'concluida'
            ).order_by(models.Lavagem.data_inicio.desc()).first()

            if lavagem:
                if not ultima_lavagem or lavagem.data_inicio > ultima_lavagem:
                    ultima_lavagem = lavagem.data_inicio

        cliente.ultima_visita = ultima_lavagem
        if ultima_lavagem:
            cliente.dias_ausente = (hoje - ultima_lavagem).days
        else:
            cliente.dias_ausente = None

    return templates.TemplateResponse("clientes.html", {
        "request": request,  # Mude de {} para request
        "clientes": clientes
    })

@app.post("/clientes_gestao/cadastrar")
async def cadastrar_cliente_veiculo(
        nome: str = Form(...),
        telefone: str = Form(...),
        modelo: str = Form(...),
        marca: str = Form(...),
        placa: str = Form(...),
        categoria: str = Form(...),
        db: Session = Depends(get_db)
):
    # 1. Cria ou busca o cliente pelo telefone
    cliente = db.query(models.Cliente).filter(models.Cliente.telefone == telefone).first()
    if not cliente:
        cliente = models.Cliente(nome=nome, telefone=telefone)
        db.add(cliente)
        db.flush()  # Gera o ID do cliente antes do commit

    # 2. Cria o veículo vinculado ao cliente
    novo_veiculo = models.Veiculo(
        marca=marca,
        modelo=modelo,
        placa=placa.upper(),
        categoria=categoria,
        cliente_id=cliente.id
    )
    db.add(novo_veiculo)
    db.commit()

    return RedirectResponse(url="/clientes_gestao", status_code=303)


@app.get("/novo")
async def nova_lavagem_page(db: Session = Depends(get_db)):
    # Buscamos todos os veículos (que já vêm com os donos/clientes vinculados)
    veiculos = db.query(models.Veiculo).all()
    # Buscamos os serviços do catálogo para você escolher o preço certo
    servicos = db.query(models.ServicoCatalogo).all()

    return templates.TemplateResponse("cadastro.html", {
        "request": {},
        "veiculos": veiculos,
        "servicos": servicos
    })

from fastapi import HTTPException


# Rota para excluir Cliente
@app.delete("/clientes/{cliente_id}")
async def excluir_cliente(cliente_id: int, db: Session = Depends(get_db)):
    cliente = db.query(models.Cliente).filter(models.Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # Apaga veículos e lavagens associadas antes de apagar o cliente
    for v in cliente.veiculos:
        db.query(models.Lavagem).filter(models.Lavagem.veiculo_id == v.id).delete()
        db.delete(v)

    db.delete(cliente)
    db.commit()
    return {"status": "sucesso"}


# Rota para excluir Veículo
@app.delete("/veiculos/{veiculo_id}")
async def excluir_veiculo(veiculo_id: int, db: Session = Depends(get_db)):
    veiculo = db.query(models.Veiculo).filter(models.Veiculo.id == veiculo_id).first()
    if not veiculo:
        raise HTTPException(status_code=404, detail="Veículo não encontrado")
    db.delete(veiculo)
    db.commit()
    return {"status": "sucesso", "mensagem": "Veículo excluído"}


# Rota para excluir Lavagem
@app.delete("/lavagens/{lavagem_id}")
async def excluir_lavagem(lavagem_id: int, db: Session = Depends(get_db)):
    lavagem = db.query(models.Lavagem).filter(models.Lavagem.id == lavagem_id).first()
    if not lavagem:
        raise HTTPException(status_code=404, detail="Lavagem não encontrada")
    db.delete(lavagem)
    db.commit()
    return {"status": "sucesso", "mensagem": "Lavagem excluída"}

# Rota para excluir um Serviço do Catálogo
@app.delete("/servicos/{id}")
async def excluir_servico(id: int, db: Session = Depends(get_db)):
    item = db.query(models.ServicoCatalogo).filter(models.ServicoCatalogo.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")
    db.delete(item)
    db.commit()
    return {"status": "sucesso"}

# Rota para excluir um Produto/Insumo
@app.delete("/produtos/{id}")
async def excluir_produto(id: int, db: Session = Depends(get_db)):
    item = db.query(models.Produto).filter(models.Produto.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    db.delete(item)
    db.commit()
    return {"status": "sucesso"}

# Rota para excluir um Custo Fixo
@app.delete("/custosfixos/{id}")
async def excluir_custo_fixo(id: int, db: Session = Depends(get_db)):
    item = db.query(models.CustoFixo).filter(models.CustoFixo.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Custo não encontrado")
    db.delete(item)
    db.commit()
    return {"status": "sucesso"}

