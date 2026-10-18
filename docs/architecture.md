# Arquitetura e limites

## Caminho de uma requisição

`app.main` inicializa o FastAPI, cria as tabelas no ciclo de vida e registra as rotas de `app.routes.web`. Cada requisição recebe uma sessão SQLAlchemy, encerrada ao fim da operação; exceções provocam rollback.

As páginas usam Jinja2 com escape de HTML. O modal de finalização monta os nomes dos produtos com `textContent`, sem interpolar conteúdo cadastrado como HTML. Respostas de erro são HTML para navegação no navegador e JSON para as chamadas da aplicação.

## Modelo e cálculos

Um cliente possui veículos; cada atendimento referencia um veículo e um serviço do catálogo. A tabela de associação `servico_produtos` relaciona os insumos padrão ao serviço.

```text
custo de um insumo = preço de compra / volume total × volume por uso
custo do trabalho = segundos decorridos / 3600 × valor da hora
resultado do serviço = valor cobrado − insumos − trabalho
```

A finalização reúne os produtos do catálogo e os selecionados pelo operador, eliminando IDs repetidos. Valores negativos e não finitos são rejeitados. Alterações de preço de insumos afetam atendimentos ainda abertos; os custos calculados são gravados quando o atendimento termina.

O cadastro de despesas fixas é informativo. Não há rateio mensal, impostos, descontos financeiros, estornos ou integração de pagamento. Os horários usam o relógio local do processo; não há conversão entre fusos.

## Armazenamento

A aplicação cria `data/estetica.db` e `data/uploads/` por padrão. Defina `DJWASH_DATA_DIR` antes de iniciar para usar outro diretório. Não importe o antigo `db_estetica.db` sem uma revisão de compatibilidade: o projeto não possui migrações automáticas.

Cada lote aceita até oito fotografias, com limite de 8 MB e 20 megapixels por arquivo. O conteúdo é decodificado, a orientação EXIF é aplicada e a imagem é redimensionada para até 2400 px antes de ser regravada como JPEG, sem os metadados originais. Nomes de arquivo são gerados pela aplicação.

A validação ocorre antes da gravação do lote. Arquivos e banco não participam de uma transação única: uma falha posterior do banco pode deixar uma imagem sem vínculo. Exclusões de registros também não fazem coleta automática das fotografias. O limite de leitura por imagem não substitui um limite de requisição no proxy em uma implantação futura.

Fotos são acessíveis pelas URLs de `/uploads`. Isso é adequado apenas à demonstração local com conteúdo fictício, pois não há controle de acesso por usuário.

## O que mudou na preparação do portfólio

- Entrada da aplicação corrigida para `app.main:app`, com diretórios independentes da pasta atual.
- Demonstração reproduzível, sem banco ou fotografias pessoais versionadas na versão atual.
- Rotas antigas não registradas, incompatíveis com os modelos atuais, removidas.
- Estilos extraídos dos templates e comportamento do painel separado em JavaScript.
- Finalização corrigida para funcionar com zero ou vários insumos e preservar o preço combinado.
- Dados de exemplo fixos retirados dos indicadores e gráficos financeiros.
- Checklist preservado quando a fotografia de entrega é adicionada.
- Links quebrados de relatórios corrigidos para a página de detalhes existente.
- Testes de regressão, verificação de código e integração contínua incluídos.

## Evoluções possíveis

1. Autenticação, autorização, proteção CSRF e auditoria antes de qualquer implantação compartilhada.
2. Migrações com Alembic e valores monetários decimais.
3. Transições de estado atômicas para suportar finalizações concorrentes.
4. Separação do gerador de PDF e das rotas por domínio conforme o projeto crescer.
5. Paginação do histórico, política de retenção das imagens e backup/restauração.

A remoção de arquivos de uso desta versão não reescreve o histórico público. Uma eventual limpeza de todo o histórico deve ser tratada separadamente, com backup e coordenação dos clones existentes.
