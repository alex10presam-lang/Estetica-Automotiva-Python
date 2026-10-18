"""Create a fictional dataset only when the database is empty."""

from datetime import datetime, timedelta
from app import models
from app.database import engine, SessionLocal


def seed_demo():
    models.Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if any(
            db.query(model).first()
            for model in (
                models.Cliente,
                models.Veiculo,
                models.Lavagem,
                models.Produto,
                models.ServicoCatalogo,
                models.Configuracao,
                models.CustoFixo,
            )
        ):
            return False
        shampoo = models.Produto(
            nome="Shampoo neutro · demonstração", preco_compra=60, ml_total=1000, ml_por_uso=50
        )
        wax = models.Produto(
            nome="Cera líquida · demonstração", preco_compra=80, ml_total=500, ml_por_uso=25
        )
        basic = models.ServicoCatalogo(
            nome="Lavagem de manutenção",
            preco_hatch=70,
            preco_sedan=90,
            preco_suv=110,
            preco_pickup=130,
            produtos_fixos=[shampoo],
        )
        detail = models.ServicoCatalogo(
            nome="Lavagem + proteção",
            preco_hatch=140,
            preco_sedan=160,
            preco_suv=190,
            preco_pickup=210,
            produtos_fixos=[shampoo, wax],
        )
        db.add_all(
            [
                basic,
                detail,
                models.Configuracao(valor_hora=30),
                models.CustoFixo(item="Espaço de trabalho · exemplo mensal", valor=900),
            ]
        )
        now = datetime.now()
        examples = [
            ("Cliente Demo 01", "Hatch conceito", "DEMO-01", "hatch", basic, 70),
            ("Cliente Demo 02", "SUV conceito", "DEMO-02", "suv", detail, 190),
            ("Cliente Demo 03", "Sedan conceito", "DEMO-03", "sedan", detail, 160),
        ]
        for i, (name, model, plate, category, service, price) in enumerate(examples):
            customer = models.Cliente(nome=name, telefone="00000000000")
            vehicle = models.Veiculo(
                marca="Demonstração",
                modelo=model,
                placa=plate,
                categoria=category,
                cliente=customer,
            )
            wash = models.Lavagem(
                veiculo=vehicle,
                servico=service,
                valor_total=price,
                data_inicio=now - timedelta(minutes=45 + 60 * i),
                status="em_andamento",
                checklist_avarias="Registro fictício para apresentação do projeto.",
                checklist_combustivel="1/2",
            )
            if i == 2:
                wash.status = "concluida"
                wash.data_fim = wash.data_inicio + timedelta(minutes=90)
                wash.tempo_total = "01:30"
                wash.custo_insumos = 7
                wash.custo_mao_de_obra = 45
                wash.lucro_real = price - 52
                wash.produtos_usados = "Shampoo neutro, cera líquida"
            db.add(wash)
        db.commit()
        return True


if __name__ == "__main__":
    print(
        "Demonstração criada com dados fictícios."
        if seed_demo()
        else "Banco já contém dados; nenhum registro foi alterado."
    )
