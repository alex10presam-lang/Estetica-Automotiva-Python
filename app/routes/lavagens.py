from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app import models, schemas
from typing import List
from fastapi import File, UploadFile # Para lidar com arquivos
import shutil
import os
from fastapi.responses import FileResponse
from reportlab.lib import colors
from reportlab.lib.colors import HexColor  # O 'H' é maiúsculo
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
router = APIRouter(prefix="/lavagens", tags=["Lavagens"])


@router.post("/iniciar", response_model=schemas.LavagemResponse)
def iniciar_lavagem(lavagem: schemas.LavagemCreate, db: Session = Depends(get_db)):
    nova_lavagem = models.Lavagem(**lavagem.model_dump())
    db.add(nova_lavagem)
    db.commit()
    db.refresh(nova_lavagem)
    return nova_lavagem


@router.patch("/finalizar/{lavagem_id}", response_model=schemas.LavagemResponse)
def finalizar_lavagem(lavagem_id: int, dados: schemas.LavagemFinalizar, db: Session = Depends(get_db)):
    db_lavagem = db.query(models.Lavagem).filter(models.Lavagem.id == lavagem_id).first()

    if not db_lavagem:
        raise HTTPException(status_code=404, detail="Lavagem não encontrada")

    db_lavagem.data_fim = datetime.utcnow()
    db_lavagem.status = "concluida"

    if dados.produtos_usados:
        db_lavagem.produtos_usados = dados.produtos_usados
    if dados.valor:
        db_lavagem.valor = dados.valor

    # Lógica do Cronômetro: Calcula tempo decorrido
    duracao = db_lavagem.data_fim - db_lavagem.data_inicio
    horas, rem = divmod(duracao.total_seconds(), 3600)
    minutos, segundos = divmod(rem, 60)

    # Se o usuário passou tempo manual, usa ele, senão usa o calculado
    db_lavagem.tempo_total = dados.tempo_manual if dados.tempo_manual else f"{int(horas):02}:{int(minutos):02}"

    db.commit()
    db.refresh(db_lavagem)
    return db_lavagem

@router.get("/", response_model=List[schemas.LavagemResponse])
def listar_lavagens(db: Session = Depends(get_db)):
    return db.query(models.Lavagem).all()


@router.post("/{lavagem_id}/upload-foto")
def upload_foto(
    lavagem_id: int,
    tipo: str, # "antes" ou "depois"
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    db_lavagem = db.query(models.Lavagem).filter(models.Lavagem.id == lavagem_id).first()
    if not db_lavagem:
        raise HTTPException(status_code=404, detail="Lavagem não encontrada")

    # Define o nome do arquivo (Ex: lavagem_1_antes.jpg)
    extensao = os.path.splitext(arquivo.filename)[1]
    nome_arquivo = f"lavagem_{lavagem_id}_{tipo}{extensao}"
    caminho_final = os.path.join("app/static/uploads", nome_arquivo)

    # Salva o arquivo no disco
    with open(caminho_final, "wb") as buffer:
        shutil.copyfileobj(arquivo.file, buffer)

    # Salva o caminho no banco de dados
    url_foto = f"/static/uploads/{nome_arquivo}"
    if tipo == "antes":
        db_lavagem.foto_antes = url_foto
    else:
        db_lavagem.foto_depois = url_foto

    db.commit()
    return {"url": url_foto}


@router.get("/{lavagem_id}/recibo")
def gerar_recibo(lavagem_id: int, db: Session = Depends(get_db)):
    lavagem = db.query(models.Lavagem).filter(models.Lavagem.id == lavagem_id).first()
    veiculo = db.query(models.Veiculo).filter(models.Veiculo.id == lavagem.veiculo_id).first()
    cliente = db.query(models.Cliente).filter(models.Cliente.id == veiculo.cliente_id).first()

    pdf_path = f"app/static/uploads/recibo_{lavagem_id}.pdf"
    c = canvas.Canvas(pdf_path, pagesize=A4)
    largura, altura = A4

    # Cores da Marca
    cor_primaria = HexColor("#1A1A1A")  # Grafite Escuro
    cor_destaque = HexColor("#FFD700")  # Amarelo Ouro (ou use #00D4FF para Azul)
    cor_texto_claro = colors.whitesmoke

    # --- FUNDO DO CABEÇALHO ---
    c.setFillColor(cor_primaria)
    c.rect(0, altura - 4 * cm, largura, 4 * cm, fill=1)

    # --- LOGO (Se existir) ---
    logo_path = "app/static/logo.png"
    if os.path.exists(logo_path):
        c.drawImage(logo_path, 1.5 * cm, altura - 3 * cm, width=2.5 * cm, preserveAspectRatio=True)

    # --- TÍTULO E CONTATO ---
    c.setFillColor(cor_texto_claro)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(4.5 * cm, altura - 2 * cm, "ESTÉTICA AUTOMOTIVA")
    c.setFont("Helvetica", 10)
    c.drawString(4.5 * cm, altura - 2.6 * cm, "Serviços de Alta Performance | (00) 00000-0000")

    # --- INFO DO CLIENTE (Card Estilizado) ---
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1.5 * cm, altura - 5 * cm, "DETALHES DO CLIENTE & VEÍCULO")
    c.line(1.5 * cm, altura - 5.2 * cm, largura - 1.5 * cm, altura - 5.2 * cm)

    c.setFont("Helvetica", 11)
    c.drawString(1.5 * cm, altura - 6 * cm, f"CLIENTE: {cliente.nome.upper()}")
    c.drawString(1.5 * cm, altura - 6.6 * cm, f"VEÍCULO: {veiculo.marca} {veiculo.modelo} | PLACA: {veiculo.placa}")

    # --- BOX DE RESUMO DO SERVIÇO ---
    c.setFillColor(HexColor("#F4F4F4"))
    c.rect(1.5 * cm, altura - 10 * cm, largura - 3 * cm, 2.5 * cm, fill=1, stroke=0)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(2 * cm, altura - 8.2 * cm, "SERVIÇO EXECUTADO")
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, altura - 8.8 * cm, f"Produtos: {lavagem.produtos_usados or 'Premium Selection'}")
    c.drawString(2 * cm, altura - 9.4 * cm, f"Tempo de Execução: {lavagem.tempo_total}")

    # Valor em Destaque
    c.setFillColor(cor_primaria)
    c.rect(largura - 7 * cm, altura - 9.8 * cm, 5.5 * cm, 1.5 * cm, fill=1)
    c.setFillColor(cor_destaque)
    c.setFont("Helvetica-Bold", 16)
    c.drawRightString(largura - 2 * cm, altura - 9 * cm, f"TOTAL R$ {lavagem.valor:.2f}")

    # --- FOTOS (Layout de Galeria) ---
    y_fotos = altura - 16 * cm

    def desenhar_moldura_foto(url, x, label):
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x, y_fotos + 4.2 * cm, label)

        caminho = os.path.join("app", url.lstrip('/')) if url else ""
        if caminho and os.path.exists(caminho):
            # Moldura fina em volta da foto
            c.setStrokeColor(colors.lightgrey)
            c.rect(x - 0.1 * cm, y_fotos - 0.1 * cm, 8.2 * cm, 4.2 * cm, stroke=1)
            c.drawImage(caminho, x, y_fotos, width=8 * cm, height=4 * cm, preserveAspectRatio=True)
        else:
            c.setFillColor(HexColor("#E0E0E0"))
            c.rect(x, y_fotos, 8 * cm, 4 * cm, fill=1, stroke=0)
            c.setFillColor(colors.gray)
            c.drawCentredString(x + 4 * cm, y_fotos + 2 * cm, "Registro não disponível")

    desenhar_moldura_foto(lavagem.foto_antes, 1.5 * cm, "REGISTRO: ANTES")
    desenhar_moldura_foto(lavagem.foto_depois, 11 * cm, "REGISTRO: DEPOIS")

    # --- RODAPÉ COM PIX ---
    pix_path = os.path.join("app", "static", "pix_qr.png")
    if os.path.exists(pix_path):
        c.setFillColor(cor_primaria)
        c.rect(0, 0, largura, 4.5 * cm, fill=1)
        c.drawImage(pix_path, 1.5 * cm, 0.5 * cm, width=3.5 * cm, height=3.5 * cm)
        c.setFillColor(cor_texto_claro)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(5.5 * cm, 2.5 * cm, "PAGAMENTO RÁPIDO VIA PIX")
        c.setFont("Helvetica", 9)
        c.drawString(5.5 * cm, 2 * cm, "Aponte a câmera do celular para o QR Code ao lado.")
        c.drawString(5.5 * cm, 1.6 * cm, "Obrigado pela confiança em nossos serviços!")

    c.showPage()
    c.save()
    return FileResponse(pdf_path, media_type='application/pdf')