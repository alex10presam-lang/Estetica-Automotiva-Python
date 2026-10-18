import io

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Request, Depends, Form, Response, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session
from app.database import get_db
from app.config import APP_DIR
from app.services import require_record, money, dose_cost, save_photos
from app import models

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.colors import HexColor

app = APIRouter()
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    lavagens = db.query(models.Lavagem).order_by(models.Lavagem.id.desc()).all()

    produtos_disponiveis = db.query(models.Produto).all()

    clientes_recentes = db.query(models.Cliente).order_by(models.Cliente.id.desc()).limit(10).all()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "lavagens": lavagens,
            "produtos_disponiveis": produtos_disponiveis,
            "clientes_recentes": clientes_recentes,
        },
    )


@app.post("/lavagens/registrar")
def registrar_nova_lavagem(
    modo_cliente: str = Form(...),
    veiculo_id: Optional[int] = Form(None),
    nome: Optional[str] = Form(None),
    telefone: Optional[str] = Form(None),
    marca: Optional[str] = Form(None),
    modelo: Optional[str] = Form(None),
    placa: Optional[str] = Form(None),
    categoria: Optional[str] = Form(None),
    servico_id: int = Form(...),
    tipo_sujeira: float = Form(0.0, ge=0, allow_inf_nan=False),
    obs_entrada: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    if modo_cliente not in {"existente", "novo"}:
        raise HTTPException(422, "Modo de cadastro inválido.")
    money(tipo_sujeira)
    servico_base = require_record(db, models.ServicoCatalogo, servico_id)
    if modo_cliente == "novo":
        if not all(value and value.strip() for value in [nome, telefone, marca, modelo, placa]):
            raise HTTPException(422, "Preencha os dados do cliente e do veículo.")
        placa = placa.strip().upper()
        if db.query(models.Veiculo).filter_by(placa=placa).first():
            raise HTTPException(409, "Placa já cadastrada. Selecione o veículo existente.")
        if categoria not in {"hatch", "sedan", "suv", "pickup"}:
            raise HTTPException(422, "Categoria inválida.")
    if modo_cliente == "existente":
        require_record(db, models.Veiculo, veiculo_id)
        v_id = veiculo_id
    else:
        cliente = db.query(models.Cliente).filter(models.Cliente.telefone == telefone).first()
        if not cliente:
            cliente = models.Cliente(nome=nome, telefone=telefone)
            db.add(cliente)
            db.flush()

        veiculo = db.query(models.Veiculo).filter(models.Veiculo.placa == placa.upper()).first()
        if not veiculo:
            veiculo = models.Veiculo(
                marca=marca,
                modelo=modelo,
                placa=placa.upper(),
                categoria=categoria,
                cliente_id=cliente.id,
            )
            db.add(veiculo)
            db.flush()
        v_id = veiculo.id

    servico_base = (
        db.query(models.ServicoCatalogo).filter(models.ServicoCatalogo.id == servico_id).first()
    )
    veiculo_obj = db.query(models.Veiculo).filter(models.Veiculo.id == v_id).first()
    cat = veiculo_obj.categoria.lower() if veiculo_obj.categoria else "hatch"

    precos = {
        "hatch": servico_base.preco_hatch,
        "sedan": servico_base.preco_sedan,
        "suv": servico_base.preco_suv,
        "pickup": servico_base.preco_pickup,
    }
    valor_base = precos.get(cat, servico_base.preco_hatch) or 0.0

    nova_lavagem = models.Lavagem(
        veiculo_id=v_id,
        servico_id=servico_id,
        valor_total=valor_base + tipo_sujeira,  # Preço final sugerido salvo aqui
        tipo_sujeira=f"Adicional: R$ {tipo_sujeira}",
        checklist_avarias=obs_entrada,
        status="em_andamento",
        data_inicio=datetime.now(),
    )
    db.add(nova_lavagem)
    db.commit()
    return RedirectResponse(url="/", status_code=303)


@app.get("/lavagem/{lavagem_id}/checklist", response_class=HTMLResponse)
def exibir_form_checklist(lavagem_id: int, request: Request, db: Session = Depends(get_db)):
    lavagem = require_record(db, models.Lavagem, lavagem_id)
    if not lavagem:
        raise HTTPException(status_code=404, detail="Lavagem não encontrada")
    return templates.TemplateResponse(
        request=request, name="checklist_form.html", context={"request": request, "l": lavagem}
    )


@app.post("/gestao/configurar_hora")
def configurar_hora(
    valor_hora: float = Form(..., ge=0, allow_inf_nan=False), db: Session = Depends(get_db)
):
    config = db.query(models.Configuracao).first()
    if not config:
        config = models.Configuracao(valor_hora=valor_hora)
        db.add(config)
    else:
        config.valor_hora = valor_hora
    db.commit()
    return RedirectResponse(url="/gestao", status_code=303)


@app.get("/lavagem/{id}/finalizar")
def tela_finalizar(id: int, db: Session = Depends(get_db)):
    require_record(db, models.Lavagem, id)
    return RedirectResponse(url=f"/?finalizar={id}", status_code=303)


@app.post("/lavagens/{lavagem_id}/finalizar")
def finalizar_lavagem(
    lavagem_id: int,
    valor_final_cobrado: float = Form(..., ge=0, allow_inf_nan=False),
    produtos_ids: Optional[List[int]] = Form(None),
    foto_antes: Optional[UploadFile] = File(None),
    foto_depois: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    lavagem = require_record(db, models.Lavagem, lavagem_id)
    if lavagem.status != "em_andamento":
        raise HTTPException(409, "Este serviço já foi finalizado.")
    money(valor_final_cobrado)
    config = db.query(models.Configuracao).first()
    valor_hora = config.valor_hora if config else 0.0
    lavagem.data_fim = datetime.now()
    segundos_totais = max((lavagem.data_fim - lavagem.data_inicio).total_seconds(), 0)
    custo_mao_de_obra = segundos_totais / 3600 * valor_hora
    products = {p.id: p for p in (lavagem.servico.produtos_fixos if lavagem.servico else [])}
    for identifier in set(produtos_ids or []):
        products[identifier] = require_record(db, models.Produto, identifier)
    custo_total_produtos = sum(dose_cost(p) for p in products.values())
    nomes_produtos = [p.nome for p in products.values()]
    photos = [f for f in (foto_antes, foto_depois) if f and f.filename]
    urls = iter(save_photos(photos, "entregas"))
    if foto_antes and foto_antes.filename:
        before = next(urls)
        lavagem.foto_entrada_url = ",".join(filter(None, [lavagem.foto_entrada_url, before]))
    if foto_depois and foto_depois.filename:
        lavagem.foto_saida_url = next(urls)

    lavagem.status = "concluida"
    lavagem.produtos_usados = (
        ", ".join(nomes_produtos) if nomes_produtos else "Nenhum insumo registrado"
    )
    lavagem.custo_insumos = round(custo_total_produtos, 2)
    lavagem.custo_mao_de_obra = round(custo_mao_de_obra, 2)
    lavagem.valor_total = valor_final_cobrado

    lavagem.lucro_real = round(valor_final_cobrado - (custo_total_produtos + custo_mao_de_obra), 2)

    minutos_totais = int(segundos_totais / 60)
    lavagem.tempo_total = f"{minutos_totais // 60:02d}:{minutos_totais % 60:02d}"

    db.commit()
    return RedirectResponse(url=f"/lavagem/{lavagem_id}/recibo_final", status_code=303)


@app.get("/lavagem/{lavagem_id}/comprovante_entrada", response_class=HTMLResponse)
def comprovante_entrada(lavagem_id: int, request: Request, db: Session = Depends(get_db)):
    lavagem = db.query(models.Lavagem).filter(models.Lavagem.id == lavagem_id).first()
    if not lavagem:
        raise HTTPException(404, "Lavagem não encontrada")

    return templates.TemplateResponse(
        request=request, name="comprovante_entrada.html", context={"request": request, "l": lavagem}
    )


@app.post("/lavagem/{lavagem_id}/checklist")
def salvar_checklist_modal(
    lavagem_id: int,
    combustivel: Optional[str] = Form("Não informado"),
    avarias: Optional[str] = Form(None),
    fotos_checklist: List[UploadFile] = File([]),
    db: Session = Depends(get_db),
):
    lavagem = require_record(db, models.Lavagem, lavagem_id)
    lavagem.checklist_combustivel = combustivel

    if lavagem.status != "em_andamento":
        raise HTTPException(409, "O checklist de um serviço concluído não pode ser alterado.")
    caminhos_fotos = save_photos(fotos_checklist, "checklists")
    if caminhos_fotos:
        lavagem.foto_entrada_url = ",".join(
            filter(None, [lavagem.foto_entrada_url, *caminhos_fotos])
        )

    lavagem.checklist_avarias = avarias
    db.commit()
    return RedirectResponse(url="/", status_code=303)


@app.get("/lavagem/{lavagem_id}/recibo_final", response_class=HTMLResponse)
def visualizar_relatorio_final(lavagem_id: int, request: Request, db: Session = Depends(get_db)):
    lavagem = require_record(db, models.Lavagem, lavagem_id)
    if not lavagem:
        raise HTTPException(status_code=404, detail="Lavagem não encontrada")

    return templates.TemplateResponse(
        request=request, name="recibo_final.html", context={"request": request, "l": lavagem}
    )


@app.get("/lavagens/{lavagem_id}/dados-finalizacao")
def dados_finalizacao(lavagem_id: int, db: Session = Depends(get_db)):
    lavagem = require_record(db, models.Lavagem, lavagem_id)
    if not lavagem:
        raise HTTPException(status_code=404, detail="Lavagem não encontrada")

    agora = datetime.now()
    delta = agora - lavagem.data_inicio
    minutos_totais = max(int(delta.total_seconds() / 60), 0)

    config = db.query(models.Configuracao).first()
    valor_hora = config.valor_hora if config else 0.0
    custo_mao_de_obra = (minutos_totais / 60) * valor_hora

    todos_produtos = db.query(models.Produto).all()
    lista_produtos_json = []
    for p in todos_produtos:
        dose = (p.preco_compra / p.ml_total * p.ml_por_uso) if p.ml_total > 0 else 0
        lista_produtos_json.append(
            {
                "id": p.id,
                "nome": p.nome,
                "incluido": bool(lavagem.servico and p in lavagem.servico.produtos_fixos),
                "custo_por_dose": dose,
            }
        )

    valor_base = float(lavagem.valor_total or 0.0)
    valor_sugerido = valor_base

    return {
        "minutos": minutos_totais,
        "valor_base": round(valor_base, 2),  # O JS estava travando aqui porque faltava essa linha
        "custo_mao_de_obra": round(custo_mao_de_obra, 2),
        "sugerido": round(valor_sugerido, 2),
        "todos_produtos": lista_produtos_json,
    }


@app.get("/clientes/{cliente_id}/historico")
def historico_especifico_cliente(cliente_id: int, db: Session = Depends(get_db)):
    historico = (
        db.query(models.Lavagem)
        .join(models.Veiculo)
        .filter(models.Veiculo.cliente_id == cliente_id, models.Lavagem.status == "concluida")
        .order_by(models.Lavagem.data_fim.desc())
        .all()
    )

    return historico


@app.get("/lavagem/{lavagem_id}/detalhes", response_class=HTMLResponse)
def detalhes_lavagem(lavagem_id: int, request: Request, db: Session = Depends(get_db)):
    lavagem = require_record(db, models.Lavagem, lavagem_id)
    if not lavagem:
        raise HTTPException(status_code=404, detail="Lavagem não encontrada")

    fotos_avarias = []
    foto_antes_entrega = None

    if lavagem.foto_entrada_url:
        lista_fotos = [f.strip() for f in lavagem.foto_entrada_url.split(",")]
        fotos_avarias = [f for f in lista_fotos if "checklists" in f]
        foto_antes_entrega = next((f for f in lista_fotos if "entregas" in f), None)

    return templates.TemplateResponse(
        request=request,
        name="detalhes_lavagem.html",
        context={
            "request": request,
            "l": lavagem,
            "fotos_avarias": fotos_avarias,
            "foto_antes": foto_antes_entrega,
        },
    )


@app.get("/historico", response_class=HTMLResponse)
def historico_financeiro(request: Request, db: Session = Depends(get_db)):
    lavagens = (
        db.query(models.Lavagem)
        .filter(models.Lavagem.status == "concluida")
        .order_by(models.Lavagem.data_fim)
        .all()
    )

    total_faturado = (
        sum(registro.valor_total for registro in lavagens if registro.valor_total) or 0.0
    )
    total_produtos = (
        sum(registro.custo_insumos for registro in lavagens if registro.custo_insumos) or 0.0
    )
    total_mao_obra = (
        sum(registro.custo_mao_de_obra for registro in lavagens if registro.custo_mao_de_obra)
        or 0.0
    )

    qtd_servicos = len(lavagens)
    ticket_medio = total_faturado / qtd_servicos if qtd_servicos > 0 else 0.0

    labels_grafico = [registro.data_fim.strftime("%d/%m") for registro in lavagens[-7:]]
    valores_grafico = [float(registro.valor_total or 0) for registro in lavagens[-7:]]

    return templates.TemplateResponse(
        request=request,
        name="historico.html",
        context={
            "request": request,
            "lavagens": lavagens[::-1],  # Inverte para mostrar as mais recentes primeiro
            "total_faturado": total_faturado,
            "total_produtos": total_produtos,
            "total_mao_obra": total_mao_obra,
            "ticket_medio": ticket_medio,
            "labels_grafico": labels_grafico,
            "valores_grafico": valores_grafico,
            "custos_grafico": [
                float((item.custo_insumos or 0) + (item.custo_mao_de_obra or 0))
                for item in lavagens[-7:]
            ],
            "categorias_grafico": [
                sum(
                    float(item.valor_total or 0)
                    for item in lavagens
                    if item.veiculo.categoria == categoria
                )
                for categoria in ("hatch", "sedan", "suv", "pickup")
            ],
        },
    )


@app.get("/lavagens/{lavagem_id}/recibo")
def gerar_recibo(lavagem_id: int, db: Session = Depends(get_db)):
    lavagem = db.query(models.Lavagem).filter(models.Lavagem.id == lavagem_id).first()
    if not lavagem:
        raise HTTPException(404, "Lavagem não encontrada")

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    largura, altura = A4

    cor_roxo_dark = HexColor("#1A052D")  # Fundo Profundo
    cor_roxo_vibrante = HexColor("#6A1B9A")  # Destaques
    cor_gold = HexColor("#D4AF37")  # Dourado Premium
    cor_texto = HexColor("#333333")

    pdf.setFillColor(cor_roxo_dark)
    pdf.rect(0, altura - 120, largura, 120, fill=1, stroke=0)

    pdf.setFillColor(cor_gold)
    pdf.rect(0, altura - 5, largura, 5, fill=1, stroke=0)

    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 28)
    pdf.drawString(50, altura - 60, "DJ WASH")

    pdf.setFont("Helvetica", 10)
    pdf.drawString(50, altura - 80, "ESTÉTICA AUTOMOTIVA")

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawRightString(largura - 50, altura - 60, f"RECIBO Nº {lavagem.id:04d}")
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(
        largura - 50, altura - 80, f"Emissão: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )

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
    if hasattr(lavagem, "servico_id") and lavagem.servico_id:
        servico_db = (
            db.query(models.ServicoCatalogo)
            .filter(models.ServicoCatalogo.id == lavagem.servico_id)
            .first()
        )
        if servico_db:
            nome_servico = servico_db.nome
    pdf.drawString(105, y, f"{nome_servico}")

    y -= 20
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(50, y, "PRODUTOS UTILIZADOS:")

    y -= 15
    pdf.setFont("Helvetica-Oblique", 9)
    produtos_texto = (
        lavagem.produtos_usados if lavagem.produtos_usados else "Nenhum insumo registrado"
    )
    pdf.drawString(60, y, f"- {produtos_texto}")

    y -= 50
    pdf.setFillColor(HexColor("#F9F9F9"))
    pdf.roundRect(50, y - 80, largura - 100, 90, 5, fill=1, stroke=1)

    pdf.setFillColor(cor_texto)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(70, y - 15, "RESUMO FINANCEIRO")

    pdf.setFont("Helvetica", 10)
    pdf.drawString(70, y - 35, "Valor Base do Serviço:")
    pdf.drawRightString(largura - 70, y - 35, f"R$ {lavagem.valor_total:.2f}")

    pdf.drawString(70, y - 50, "Taxas Adicionais / Descontos:")
    pdf.drawRightString(largura - 70, y - 50, "R$ 0,00")

    pdf.setStrokeColor(colors.lightgrey)
    pdf.line(70, y - 58, largura - 70, y - 58)

    pdf.setFillColor(cor_roxo_dark)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(70, y - 75, "VALOR DO SERVIÇO")

    pdf.setFillColor(cor_gold)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawRightString(largura - 70, y - 75, f"R$ {lavagem.valor_total:.2f}")

    y_final = 100
    pdf.setFillColor(cor_roxo_vibrante)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawCentredString(largura / 2, y_final, "Obrigado por confiar na DJ WASH!")

    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(colors.grey)
    pdf.drawCentredString(
        largura / 2, y_final - 15, "Documento demonstrativo. Não comprova quitação bancária."
    )
    pdf.drawCentredString(
        largura / 2, y_final - 28, "Projeto de portfólio | Gestão de estética automotiva"
    )

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return Response(
        content=buffer.read(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=Recibo_DJWASH_{lavagem.id}.pdf"},
    )


@app.get("/gestao", response_class=HTMLResponse)
def pagina_gestao(request: Request, db: Session = Depends(get_db)):
    produtos = db.query(models.Produto).all()
    servicos = db.query(models.ServicoCatalogo).all()
    custos_fixos = db.query(models.CustoFixo).all()
    config = db.query(models.Configuracao).first()
    return templates.TemplateResponse(
        request=request,
        name="gestao.html",
        context={
            "request": request,
            "produtos": produtos,
            "servicos": servicos,
            "custos": custos_fixos,
            "config": config,
        },
    )


@app.post("/gestao/produto")
def salvar_produto(
    nome: str = Form(...),
    preco: float = Form(..., ge=0, allow_inf_nan=False),
    ml_total: int = Form(..., gt=0),
    ml_uso: int = Form(..., gt=0),
    db: Session = Depends(get_db),
):
    novo = models.Produto(nome=nome, preco_compra=preco, ml_total=ml_total, ml_por_uso=ml_uso)
    db.add(novo)
    db.commit()
    return RedirectResponse(url="/gestao", status_code=303)


@app.get("/cliente/{cliente_id}/historico", response_class=HTMLResponse)
def historico_cliente(request: Request, cliente_id: int, db: Session = Depends(get_db)):
    cliente = require_record(db, models.Cliente, cliente_id)

    lavagens = (
        db.query(models.Lavagem)
        .join(models.Veiculo)
        .filter(models.Veiculo.cliente_id == cliente_id)
        .order_by(models.Lavagem.data_inicio.desc())
        .all()
    )
    total_pago = sum(
        registro.valor_total or 0 for registro in lavagens if registro.status == "concluida"
    )

    return templates.TemplateResponse(
        request=request,
        name="perfil_cliente.html",
        context={
            "request": request,
            "cliente": cliente,
            "lavagens": lavagens,
            "total_pago": f"{total_pago:.2f}",
        },
    )


@app.post("/gestao/servico")
def salvar_servico_catalogo(
    nome: str = Form(...),
    hatch: float = Form(0.0, ge=0, allow_inf_nan=False),
    sedan: float = Form(0.0, ge=0, allow_inf_nan=False),
    suv: float = Form(0.0, ge=0, allow_inf_nan=False),
    pickup: float = Form(0.0, ge=0, allow_inf_nan=False),
    produtos_fixos_ids: List[int] = Form([]),
    db: Session = Depends(get_db),
):
    servico = models.ServicoCatalogo(
        nome=nome, preco_hatch=hatch, preco_sedan=sedan, preco_suv=suv, preco_pickup=pickup
    )

    if produtos_fixos_ids:
        produtos_selecionados = (
            db.query(models.Produto).filter(models.Produto.id.in_(produtos_fixos_ids)).all()
        )
        servico.produtos_fixos = produtos_selecionados

    db.add(servico)
    db.commit()
    return RedirectResponse(url="/gestao", status_code=303)


@app.post("/gestao/custofixo")
def salvar_custo_fixo(
    item: str = Form(...),
    valor: float = Form(..., ge=0, allow_inf_nan=False),
    db: Session = Depends(get_db),
):
    nova_despesa = models.CustoFixo(item=item, valor=valor)
    db.add(nova_despesa)
    db.commit()
    return RedirectResponse(url="/gestao", status_code=303)


@app.get("/clientes_gestao", response_class=HTMLResponse)
def gerenciar_clientes(request: Request, db: Session = Depends(get_db)):
    clientes = db.query(models.Cliente).all()
    hoje = datetime.now()

    for cliente in clientes:
        ultima_lavagem = None
        for veiculo in cliente.veiculos:
            lavagem = (
                db.query(models.Lavagem)
                .filter(
                    models.Lavagem.veiculo_id == veiculo.id, models.Lavagem.status == "concluida"
                )
                .order_by(models.Lavagem.data_inicio.desc())
                .first()
            )

            if lavagem:
                if not ultima_lavagem or lavagem.data_inicio > ultima_lavagem:
                    ultima_lavagem = lavagem.data_inicio

        cliente.ultima_visita = ultima_lavagem
        if ultima_lavagem:
            cliente.dias_ausente = (hoje - ultima_lavagem).days
        else:
            cliente.dias_ausente = None

    return templates.TemplateResponse(
        request=request,
        name="clientes.html",
        context={
            "request": request,  # Mude de {} para request
            "clientes": clientes,
        },
    )


@app.post("/clientes_gestao/cadastrar")
def cadastrar_cliente_veiculo(
    nome: str = Form(...),
    telefone: str = Form(...),
    modelo: str = Form(...),
    marca: str = Form(...),
    placa: str = Form(...),
    categoria: str = Form(...),
    db: Session = Depends(get_db),
):
    if not all(value.strip() for value in [nome, telefone, modelo, marca, placa]):
        raise HTTPException(422, "Preencha os dados do cliente e do veículo.")
    placa = placa.strip().upper()
    if categoria not in {"hatch", "sedan", "suv", "pickup"}:
        raise HTTPException(422, "Categoria inválida.")
    if db.query(models.Veiculo).filter_by(placa=placa).first():
        raise HTTPException(409, "Placa já cadastrada.")
    cliente = db.query(models.Cliente).filter(models.Cliente.telefone == telefone).first()
    if not cliente:
        cliente = models.Cliente(nome=nome, telefone=telefone)
        db.add(cliente)
        db.flush()  # Gera o ID do cliente antes do commit

    novo_veiculo = models.Veiculo(
        marca=marca, modelo=modelo, placa=placa.upper(), categoria=categoria, cliente_id=cliente.id
    )
    db.add(novo_veiculo)
    db.commit()

    return RedirectResponse(url="/clientes_gestao", status_code=303)


@app.get("/novo")
def nova_lavagem_page(request: Request, db: Session = Depends(get_db)):
    veiculos = db.query(models.Veiculo).all()
    servicos = db.query(models.ServicoCatalogo).all()

    return templates.TemplateResponse(
        request=request,
        name="cadastro.html",
        context={"request": request, "veiculos": veiculos, "servicos": servicos},
    )


@app.delete("/clientes/{cliente_id}")
def excluir_cliente(cliente_id: int, db: Session = Depends(get_db)):
    cliente = require_record(db, models.Cliente, cliente_id)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    for v in cliente.veiculos:
        db.query(models.Lavagem).filter(models.Lavagem.veiculo_id == v.id).delete()
        db.delete(v)

    db.delete(cliente)
    db.commit()
    return {"status": "sucesso"}


@app.delete("/veiculos/{veiculo_id}")
def excluir_veiculo(veiculo_id: int, db: Session = Depends(get_db)):
    veiculo = db.query(models.Veiculo).filter(models.Veiculo.id == veiculo_id).first()
    if not veiculo:
        raise HTTPException(status_code=404, detail="Veículo não encontrado")
    if veiculo.lavagens:
        raise HTTPException(409, "O veículo possui serviços registrados.")
    db.delete(veiculo)
    db.commit()
    return {"status": "sucesso", "mensagem": "Veículo excluído"}


@app.delete("/lavagens/{lavagem_id}")
def excluir_lavagem(lavagem_id: int, db: Session = Depends(get_db)):
    lavagem = db.query(models.Lavagem).filter(models.Lavagem.id == lavagem_id).first()
    if not lavagem:
        raise HTTPException(status_code=404, detail="Lavagem não encontrada")
    db.delete(lavagem)
    db.commit()
    return {"status": "sucesso", "mensagem": "Lavagem excluída"}


@app.delete("/servicos/{id}")
def excluir_servico(id: int, db: Session = Depends(get_db)):
    item = db.query(models.ServicoCatalogo).filter(models.ServicoCatalogo.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")
    if db.query(models.Lavagem).filter_by(servico_id=id).first():
        raise HTTPException(409, "O serviço possui atendimentos registrados.")
    item.produtos_fixos.clear()
    db.delete(item)
    db.commit()
    return {"status": "sucesso"}


@app.delete("/produtos/{id}")
def excluir_produto(id: int, db: Session = Depends(get_db)):
    item = db.query(models.Produto).filter(models.Produto.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    if db.query(models.ServicoProduto).filter_by(produto_id=id).first():
        raise HTTPException(409, "O produto está vinculado a um serviço.")
    db.delete(item)
    db.commit()
    return {"status": "sucesso"}


@app.delete("/custosfixos/{id}")
def excluir_custo_fixo(id: int, db: Session = Depends(get_db)):
    item = db.query(models.CustoFixo).filter(models.CustoFixo.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Custo não encontrado")
    db.delete(item)
    db.commit()
    return {"status": "sucesso"}
