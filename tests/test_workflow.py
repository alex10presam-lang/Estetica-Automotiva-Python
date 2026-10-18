import io
import os
import tempfile
import atexit
from pathlib import Path
from datetime import datetime, timedelta

import pytest
from PIL import Image

# The test process never opens an existing application database.
_test_parent = Path(__file__).resolve().parents[1] / ".pytest_cache"
_test_parent.mkdir(exist_ok=True)
_data = tempfile.TemporaryDirectory(
    prefix="djwash-tests-", dir=_test_parent, ignore_cleanup_errors=True
)
os.environ["DJWASH_DATA_DIR"] = _data.name

from fastapi.testclient import TestClient
from app.main import app
from app.database import engine, SessionLocal
from app import models
from app.demo import seed_demo

atexit.register(engine.dispose)


@pytest.fixture
def client():
    models.Base.metadata.drop_all(engine)
    with TestClient(app) as client:
        yield client


def create_wash(client):
    seed_demo()
    with SessionLocal() as db:
        wash = db.query(models.Lavagem).filter_by(status="em_andamento").first()
        wash.data_inicio = datetime.now() - timedelta(hours=1)
        db.commit()
        return wash.id


@pytest.mark.parametrize("url", ["/", "/novo", "/gestao", "/historico", "/clientes_gestao"])
def test_pages_empty_and_demo(client, url):
    assert client.get(url).status_code == 200
    seed_demo()
    assert client.get(url).status_code == 200


def test_demo_never_overwrites(client):
    assert seed_demo()
    assert not seed_demo()
    with SessionLocal() as db:
        assert db.query(models.Cliente).count() == 3


@pytest.mark.parametrize("tail", ["checklist", "comprovante_entrada", "detalhes", "recibo_final"])
def test_service_pages(client, tail):
    identifier = create_wash(client)
    assert client.get(f"/lavagem/{identifier}/{tail}").status_code == 200


def test_supplies_empty_and_multiple(client):
    identifier = create_wash(client)
    data = client.get(f"/lavagens/{identifier}/dados-finalizacao").json()
    assert len(data["todos_produtos"]) == 2
    assert data["sugerido"] == data["valor_base"] == 70
    with SessionLocal() as db:
        db.query(models.ServicoProduto).delete()
        db.query(models.Produto).delete()
        db.commit()
    data = client.get(f"/lavagens/{identifier}/dados-finalizacao").json()
    assert data["todos_produtos"] == []
    assert data["sugerido"] == 70


def test_finish_costs_and_duplicate_submission(client):
    identifier = create_wash(client)
    with SessionLocal() as db:
        ids = [p.id for p in db.query(models.Produto).all()]
    response = client.post(
        f"/lavagens/{identifier}/finalizar",
        data={"valor_final_cobrado": "100", "produtos_ids": ids + ids},
        follow_redirects=False,
    )
    assert response.status_code == 303
    with SessionLocal() as db:
        wash = db.get(models.Lavagem, identifier)
        assert wash.custo_insumos == 7
        assert wash.custo_mao_de_obra == pytest.approx(30, abs=0.1)
        assert wash.lucro_real == pytest.approx(63, abs=0.1)
    assert (
        client.post(
            f"/lavagens/{identifier}/finalizar", data={"valor_final_cobrado": "999"}
        ).status_code
        == 409
    )
    pdf = client.get(f"/lavagens/{identifier}/recibo")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_invalid_registration_rolls_back(client):
    seed_demo()
    data = {
        "modo_cliente": "novo",
        "servico_id": 1,
        "nome": "Demo",
        "telefone": "000",
        "marca": "Demo",
        "modelo": "Demo",
        "categoria": "hatch",
    }
    assert client.post("/lavagens/registrar", data=data).status_code == 422
    with SessionLocal() as db:
        assert db.query(models.Cliente).count() == 3
    data["placa"] = "DEMO-01"
    assert client.post("/lavagens/registrar", data=data).status_code == 409


@pytest.mark.parametrize(
    "url",
    [
        "/lavagem/999/checklist",
        "/lavagem/999/recibo_final",
        "/lavagens/999/dados-finalizacao",
        "/cliente/999/historico",
    ],
)
def test_missing_records(client, url):
    assert client.get(url).status_code == 404


@pytest.mark.parametrize("value", ["-1", "nan", "inf"])
def test_invalid_money(client, value):
    identifier = create_wash(client)
    assert (
        client.post(
            f"/lavagens/{identifier}/finalizar", data={"valor_final_cobrado": value}
        ).status_code
        == 422
    )


def image_file():
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "gray").save(buffer, "PNG")
    return ("demo.png", buffer.getvalue(), "image/png")


def test_upload_validation_and_inspection_preservation(client):
    identifier = create_wash(client)
    url = f"/lavagem/{identifier}/checklist"
    assert (
        client.post(
            url, files={"fotos_checklist": ("fake.jpg", b"<script>alert(1)</script>", "image/jpeg")}
        ).status_code
        == 422
    )
    assert (
        client.post(
            url, files={"fotos_checklist": image_file()}, follow_redirects=False
        ).status_code
        == 303
    )
    assert (
        client.post(
            f"/lavagens/{identifier}/finalizar",
            data={"valor_final_cobrado": "100"},
            files={"foto_antes": image_file()},
            follow_redirects=False,
        ).status_code
        == 303
    )
    with SessionLocal() as db:
        paths = db.get(models.Lavagem, identifier).foto_entrada_url.split(",")
        assert len(paths) == 2
        assert "/checklists/" in paths[0] and "/entregas/" in paths[1]
    for path in paths:
        assert client.get("/" + path).headers["content-type"] == "image/jpeg"


def test_related_records_cannot_be_deleted(client):
    identifier = create_wash(client)
    with SessionLocal() as db:
        wash = db.get(models.Lavagem, identifier)
        vehicle, service = wash.veiculo_id, wash.servico_id
    assert client.delete(f"/veiculos/{vehicle}").status_code == 409
    assert client.delete(f"/servicos/{service}").status_code == 409


def test_full_registration_flow(client):
    seed_demo()
    response = client.post(
        "/lavagens/registrar",
        data={
            "modo_cliente": "novo",
            "nome": "Cliente de teste",
            "telefone": "00000",
            "marca": "Demo",
            "modelo": "Teste",
            "placa": "demo-04",
            "categoria": "pickup",
            "servico_id": 1,
            "tipo_sujeira": 20,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    with SessionLocal() as db:
        wash = db.query(models.Lavagem).order_by(models.Lavagem.id.desc()).first()
        assert wash.valor_total == 150
        assert wash.veiculo.placa == "DEMO-04"


def test_financial_charts_use_recorded_costs(client):
    seed_demo()
    response = client.get("/historico")
    assert response.context["custos_grafico"] == [52]
    assert response.context["categorias_grafico"] == [0, 160, 0, 0]
    assert response.context["valores_grafico"] == [160]


def test_browser_errors_are_readable(client):
    response = client.get("/lavagem/999/checklist", headers={"accept": "text/html"})
    assert response.status_code == 404
    assert "Voltar ao painel" in response.text


def test_oversized_photo(client):
    identifier = create_wash(client)
    response = client.post(
        f"/lavagem/{identifier}/checklist",
        files={"fotos_checklist": ("large.jpg", b"x" * (8 * 1024 * 1024 + 1), "image/jpeg")},
    )
    assert response.status_code == 413
