DJ WASH - Gestão de Estética Automotiva

O DJ WASH é um sistema de gestão especializado para centros de detalhamento automotivo. Ele permite o controle total desde a entrada do veículo (checklist de avarias) até a finalização do serviço com cálculos de lucro real, gestão de insumos e geração de relatórios digitais.

Funcionalidades principais

Checklist Inteligente: Registro fotográfico de avarias e nível de combustível na entrada.

Gestão Financeira: * Cálculo automático de custo de mão de obra por tempo decorrido.

Custo de insumos por dose/uso de produto.

Cálculo de Lucro Real (Faturamento - Custos Fixos - Insumos - Tempo).

Relatórios Digitais: Histórico detalhado com fotos de "Antes e Depois" e observações técnicas.

Gestão de Clientes: Histórico de visitas e alertas de retenção (dias ausentes).

Dashboard em Tempo Real: Visualização de serviços em andamento e estatísticas de faturamento.

🛠️ Tecnologias Utilizadas
O projeto foi construído com uma stack moderna e robusta:

Backend: FastAPI (Python 3.10+)

Banco de Dados: SQLite com SQLAlchemy ORM

Frontend: HTML5, CSS3 (Customizado), Bootstrap 5 e Jinja2 Templates

Relatórios: Geração de PDF com ReportLab (Opcional) e Relatórios HTML Responsivos

📂 Estrutura de Pastas
Plaintext

estetica_automotiva/
├── app/
│   ├── static/          # CSS, JS e Uploads de fotos
│   ├── templates/       # Arquivos HTML (Jinja2)
│   ├── database.py      # Conexão com banco de dados
│   ├── models.py        # Esquemas das tabelas (SQLAlchemy)
├── main.py              # Rotas e lógica principal do FastAPI
└── requirements.txt     # Dependências do projeto
🔧 Como Instalar e Rodar
Clone o repositório:

Bash

git clone https://github.com/alex10presam-lang/Estetica-Automotiva-Python.gitCrie um ambiente virtual:

Bash

python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
Instale as dependências:

Bash

pip install -r requirements.txt
Inicie o servidor:

Bash

uvicorn main:app --reload
Acesse no navegador: http://127.0.0.1:8000

📸 Screenshots
Tela de Finalização e Custos
Relatório de Detalhes (Antes e Depois)
🤝 Contribuição
Faça um Fork do projeto.

Crie uma Branch para sua feature (git checkout -b feature/NovaFeature).

Comite suas mudanças (git commit -m 'Adicionando nova feature').

Push para a Branch (git push origin feature/NovaFeature).

Abra um Pull Request.
