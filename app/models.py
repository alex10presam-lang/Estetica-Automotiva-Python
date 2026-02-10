from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


# 1. Configurações Globais (NOVO: Para salvar o preço da hora)
class Configuracao(Base):
    __tablename__ = "configuracoes"
    id = Column(Integer, primary_key=True, index=True)
    valor_hora = Column(Float, default=0.0)  # Variável do preço da hora


# 2. Cadastro de Insumos (Shampoos, Ceras, etc)
class Produto(Base):
    __tablename__ = "produtos"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    preco_compra = Column(Float)
    ml_total = Column(Integer)
    ml_por_uso = Column(Integer)


# 3. Catálogo de Serviços (Preços por categoria)
class ServicoCatalogo(Base):
    __tablename__ = "servicos_catalogo"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String)
    preco_hatch = Column(Float)
    preco_sedan = Column(Float)
    preco_suv = Column(Float)
    preco_pickup = Column(Float)
    produtos_fixos = relationship("Produto", secondary="servico_produtos")

class ServicoProduto(Base):
    __tablename__ = "servico_produtos"
    servico_id = Column(Integer, ForeignKey("servicos_catalogo.id"), primary_key=True)
    produto_id = Column(Integer, ForeignKey("produtos.id"), primary_key=True)


# 4. Custos Fixos (Aluguel, Água, etc)
class CustoFixo(Base):
    __tablename__ = "custos_fixos"
    id = Column(Integer, primary_key=True, index=True)
    item = Column(String)
    valor = Column(Float)


# 5. Clientes
class Cliente(Base):
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    telefone = Column(String, nullable=False)
    veiculos = relationship("Veiculo", back_populates="cliente")


# 6. Veículos
class Veiculo(Base):
    __tablename__ = "veiculos"
    id = Column(Integer, primary_key=True, index=True)
    marca = Column(String)
    modelo = Column(String)
    placa = Column(String, unique=True)
    categoria = Column(String)
    cliente_id = Column(Integer, ForeignKey("clientes.id"))

    cliente = relationship("Cliente", back_populates="veiculos")
    lavagens = relationship("Lavagem", back_populates="veiculo")


# 7. Lavagens (Atualizada com campos de custo real)
class Lavagem(Base):
    __tablename__ = "lavagens"
    id = Column(Integer, primary_key=True, index=True)
    veiculo_id = Column(Integer, ForeignKey("veiculos.id"))

    servico_id = Column(Integer, ForeignKey("servicos_catalogo.id"), nullable=True)

    data_inicio = Column(DateTime, default=datetime.utcnow)
    data_fim = Column(DateTime, nullable=True)
    tempo_total = Column(String, nullable=True)  # Ex: "01:30"
    minutos_totais = Column(Integer, default=0)  # Para cálculos matemáticos precisos
    foto_saida_url = Column(String, nullable=True)
    foto_antes = Column(String, nullable=True)
    foto_depois = Column(String, nullable=True)

    # Financeiro Detalhado
    valor_total = Column(Float)  # Quanto o cliente pagou
    custo_insumos = Column(Float, default=0.0)  # Gasto com produtos
    custo_mao_de_obra = Column(Float, default=0.0)  # (Tempo x Valor da Hora)
    lucro_real = Column(Float, default=0.0)  # Valor Total - (Insumos + Mão de Obra)
    checklist_avarias = Column(String, nullable=True)  # Texto descrevendo riscos/mossas
    checklist_combustivel = Column(String, nullable=True)  # Ex: "1/4", "Reserva", "Cheio"
    checklist_objetos = Column(String, nullable=True)  # Itens de valor deixados
    checklist_pneus = Column(String, nullable=True)  # Estado dos pneus
    foto_entrada_url = Column(String, nullable=True)  # Caminho da foto principal


    status = Column(String, default="em_andamento")
    tipo_sujeira = Column(String)
    checklist = Column(Text)
    produtos_usados = Column(Text)  # Alterado para Text para suportar listas longas

    servico = relationship("ServicoCatalogo")

    veiculo = relationship("Veiculo", back_populates="lavagens")