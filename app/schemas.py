from pydantic import BaseModel
from datetime import datetime
from typing import Optional

# Esquema para criação (o que vem do formulário/frontend)
class ClienteCreate(BaseModel):
    nome: str
    telefone: str
    email: Optional[str] = None

# Esquema para resposta (o que o sistema devolve, incluindo ID e Data)
class ClienteResponse(ClienteCreate):
    id: int
    data_cadastro: datetime

    class Config:
        from_attributes = True


class VeiculoCreate(BaseModel):
    marca: str
    modelo: str
    placa: str
    cor: Optional[str] = None
    cliente_id: int # ID do dono

class VeiculoResponse(VeiculoCreate):
    id: int

    class Config:
        from_attributes = True

class LavagemBase(BaseModel):
    veiculo_id: int
    produtos_usados: Optional[str] = None
    valor: float = 0.0

class LavagemCreate(LavagemBase):
    pass # Para iniciar a lavagem

class LavagemFinalizar(BaseModel):
    produtos_usados: Optional[str] = None
    valor: Optional[float] = None
    tempo_manual: Optional[str] = None # Caso o usuário queira digitar o tempo

class LavagemResponse(LavagemBase):
    id: int
    data_inicio: datetime
    data_fim: Optional[datetime] = None
    tempo_total: Optional[str] = None
    status: str

    class Config:
        from_attributes = True