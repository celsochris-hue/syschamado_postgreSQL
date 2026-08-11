# Sistema de Abertura de Chamados e Demandas

Sistema web desenvolvido em **Python (Flask)** com banco de dados **PostgreSQL**, para
cadastro de chamados/demandas, upload de anexos (evidências), controle de status
(**Aberto**, **Suspenso**, **Encerrado**), **login de usuários**, **notificações por e-mail**
e **exportação de relatórios em Excel e PDF**.

## Funcionalidades

- **Login de usuários** com senha (criptografada), cadastro de conta e sessão protegida
- **Painel de administração** (`/admin/usuarios`) para gerenciar contas: alterar papel
  (usuário/técnico/admin), ativar/desativar e excluir usuários
- **Atribuição de chamados a um técnico responsável**, com notificação automática por e-mail
  ao técnico designado
- Cadastro de chamados com título, descrição, solicitante, e-mail, setor e prioridade
- Upload de múltiplos anexos como evidência (imagens, PDF, Word, Excel, ZIP, etc.)
- Adição de novos anexos a um chamado já existente
- Alteração de status com registro de histórico (quem mudou, quando, observação)
- **Notificação automática por e-mail** ao solicitante sempre que o status do chamado mudar
  (e também quando o chamado é aberto)
- **Exportação em Excel (.xlsx)** e **PDF** da lista de chamados (respeitando os filtros aplicados)
- **Exportação em PDF** de um chamado individual, com descrição, anexos e histórico completo
- Listagem com filtros por status e busca por texto
- Exclusão de chamados e de anexos individuais
- Identidade visual com a logo da Marista no cabeçalho e nas telas de login/cadastro
- Interface web responsiva, sem necessidade de frameworks JS externos

## Estrutura do projeto

```
chamados/
├── app.py                 # Aplicação Flask (rotas, modelos, login, lógica principal)
├── emails.py               # Envio de e-mails (SMTP) e templates HTML de notificação
├── relatorios.py            # Geração de relatórios em Excel (openpyxl) e PDF (reportlab)
├── seed.py                  # Script opcional: cria usuário admin + chamados de exemplo
├── requirements.txt         # Dependências Python
├── .env.example              # Modelo de variáveis de ambiente (copie para .env)
├── templates/
│   ├── base.html             # Layout principal (com barra de usuário/logout)
│   ├── login.html            # Tela de login
│   ├── registrar.html        # Tela de criação de conta
│   ├── index.html            # Listagem de chamados
│   ├── novo.html              # Formulário de novo chamado
│   └── detalhe.html           # Detalhe do chamado, status, anexos e histórico
├── static/
│   └── style.css              # Estilo visual do sistema
└── uploads/                    # Pasta onde os anexos são salvos (criada automaticamente)
```

> O banco de dados PostgreSQL roda separado da aplicação (localmente ou em um serviço
> gerenciado) — não há mais um arquivo de banco dentro da pasta do projeto.

## Como instalar e executar

### 1. Pré-requisitos
- Python 3.9 ou superior instalado
- pip (gerenciador de pacotes do Python)
- **PostgreSQL instalado e rodando** (local, em um container Docker, ou um serviço
  gerenciado como Render, Railway, Supabase, RDS etc.)

### 2. Criar o banco de dados PostgreSQL

Se estiver usando PostgreSQL local, crie o banco e (opcionalmente) um usuário dedicado.
Exemplo via `psql`:

```sql
CREATE DATABASE chamados;
CREATE USER chamados_app WITH PASSWORD 'uma-senha-forte';
GRANT ALL PRIVILEGES ON DATABASE chamados TO chamados_app;
```

Ou, rapidamente com Docker:

```bash
docker run --name chamados-postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=chamados \
  -p 5432:5432 -d postgres:16
```

### 3. Criar um ambiente virtual (recomendado)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / Mac
source venv/bin/activate
```

### 4. Instalar as dependências

```bash
pip install -r requirements.txt
```

Isso instala o driver `psycopg2-binary`, necessário para o Flask/SQLAlchemy conversar
com o PostgreSQL.

### 5. Configurar variáveis de ambiente

Copie o arquivo de exemplo e edite com seus dados:

```bash
cp .env.example .env
```

Abra o `.env` e ajuste:
- `SECRET_KEY` — qualquer string aleatória e longa
- `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME` — dados de conexão com o
  PostgreSQL (ou, alternativamente, defina só `DATABASE_URL` com a string de conexão
  completa — útil para serviços gerenciados)
- `MAIL_ATIVO` — deixe `False` para testar sem enviar e-mails de verdade (eles aparecerão
  apenas no console/terminal); mude para `True` quando configurar um SMTP real
- `MAIL_SERVER`, `MAIL_USERNAME`, `MAIL_PASSWORD`, etc. — dados do seu provedor de e-mail

> Este passo agora é **obrigatório**: sem as credenciais corretas do PostgreSQL no
> `.env` (ou nas variáveis de ambiente do sistema), a aplicação não conseguirá se
> conectar ao banco.

### 6. Executar a aplicação

```bash
python app.py
```

Ao iniciar, a aplicação se conecta ao PostgreSQL configurado e cria automaticamente
todas as tabelas necessárias (caso ainda não existam).

Acesse no navegador: **http://localhost:5000**

Você será redirecionado para a tela de login. Clique em **"Criar conta"** para se
cadastrar — o **primeiro usuário criado vira administrador automaticamente**.

### 7. (Opcional) Popular com dados de exemplo

```bash
python seed.py
```

Isso cria dois usuários de teste:
- **Admin:** admin@empresa.com / senha `admin123`
- **Técnico:** tecnico@empresa.com / senha `tecnico123`

e três chamados de exemplo (um de cada status, um já atribuído ao técnico de teste).

## Papéis de usuário e atribuição de chamados

O sistema tem três papéis:

- **usuario** — pode abrir chamados, ver a lista, alterar status e exportar relatórios
- **tecnico** — mesmas permissões de `usuario`, e pode ser selecionado como responsável
  por um chamado
- **admin** — todas as permissões acima, mais acesso ao painel `/admin/usuarios`

O **primeiro usuário cadastrado no sistema vira administrador automaticamente**. A partir
daí, o admin acessa **"Administração"** no topo da página para:

- Alterar o papel de qualquer usuário (ex: promover alguém a "técnico" para que ele possa
  receber chamados atribuídos)
- Ativar ou desativar contas (uma conta desativada não consegue mais fazer login)
- Excluir contas que nunca tiveram chamados, atribuições ou alterações de status vinculadas
  (caso contrário, o sistema pede para desativar em vez de excluir, preservando o histórico)

Na tela de detalhe de cada chamado, qualquer usuário logado pode atribuir (ou remover) um
técnico responsável através do menu **"Responsável Técnico"**. Ao atribuir, o técnico
recebe um e-mail de notificação (se o envio de e-mail estiver ativado).

## Configuração de e-mail (SMTP)

O sistema envia e-mails usando `smtplib` (biblioteca padrão do Python), sem depender de
serviços externos pagos. Funciona com qualquer provedor SMTP. Exemplos comuns:

**Gmail** (é necessário gerar uma "senha de app" nas configurações de segurança da conta
Google — a senha normal da conta não funciona com SMTP):
```
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=seuemail@gmail.com
MAIL_PASSWORD=sua-senha-de-app
```

**Outlook / Office 365:**
```
MAIL_SERVER=smtp.office365.com
MAIL_PORT=587
MAIL_USE_TLS=True
```

**SendGrid:**
```
MAIL_SERVER=smtp.sendgrid.net
MAIL_PORT=587
MAIL_USERNAME=apikey
MAIL_PASSWORD=sua-api-key-do-sendgrid
```

Enquanto `MAIL_ATIVO=False`, nenhum e-mail real é enviado — o sistema apenas imprime no
console o que seria enviado, o que é útil para testar sem configurar SMTP.

## Exportação de relatórios

- Na **listagem de chamados**, os botões **"⬇ Excel"** e **"⬇ PDF"** exportam os chamados
  filtrados (respeitam o status e a busca selecionados).
- No **detalhe de um chamado**, o botão **"⬇ PDF"** gera um relatório individual completo,
  com descrição, lista de anexos e histórico de status.

## Banco de dados

O sistema usa **PostgreSQL**. A conexão é montada em `app.py` a partir de variáveis de
ambiente (via `.env` ou variáveis do sistema):

- `DATABASE_URL` (se definida, tem prioridade sobre as demais — formato
  `postgresql://usuario:senha@host:porta/nome_do_banco`), **ou**
- `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME` (usadas para montar a URL de
  conexão automaticamente)

As tabelas são criadas automaticamente na primeira execução (`db.create_all()`), não é
necessário rodar nenhum script SQL manualmente. São elas:

- **usuarios** — contas de login (nome, e-mail, senha criptografada, papel, ativo/inativo)
- **chamados** — dados principais de cada chamado (título, descrição, solicitante, e-mail,
  setor, prioridade, status, datas, quem abriu, técnico responsável)
- **anexos** — arquivos de evidência vinculados a cada chamado
- **historico_status** — registro de todas as mudanças de status, incluindo quem alterou

> **Atenção:** se você já tinha uma versão anterior deste sistema rodando com SQLite,
> os dados **não são migrados automaticamente** — trata-se de um banco novo (PostgreSQL).
> Rode `python seed.py` para popular com dados de teste, ou cadastre os chamados novamente
> pela interface.

## Segurança e observações para uso em produção

- Troque o valor de `SECRET_KEY` por uma chave segura e secreta (não deixe o valor padrão).
- Nunca envie o arquivo `.env` para repositórios públicos — ele deve conter dados
  sensíveis (senha de e-mail, chave secreta).
- Não use o servidor de desenvolvimento (`app.run(debug=True)`) em produção. Utilize um
  servidor WSGI como **Gunicorn** ou **Waitress** atrás de um proxy reverso (Nginx).
- A senha é armazenada com hash seguro (`werkzeug.security`), nunca em texto puro.
- Por padrão, o cadastro de contas é aberto (qualquer pessoa pode criar uma conta). Em um
  ambiente corporativo, considere restringir isso (por exemplo, exigir aprovação de um
  administrador antes de ativar a conta).
- O limite de upload está configurado em 25 MB por requisição (`MAX_CONTENT_LENGTH`),
  ajuste conforme sua necessidade.

## Tecnologias utilizadas

- [Flask](https://flask.palletsprojects.com/) — framework web
- [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/) — ORM para o banco de dados
- [Flask-Login](https://flask-login.readthedocs.io/) — autenticação e gerenciamento de sessão
- [PostgreSQL](https://www.postgresql.org/) — banco de dados
- [psycopg2](https://www.psycopg.org/) — driver de conexão com o PostgreSQL
- [openpyxl](https://openpyxl.readthedocs.io/) — geração de relatórios Excel
- [ReportLab](https://www.reportlab.com/) — geração de relatórios PDF
- `smtplib` (biblioteca padrão do Python) — envio de e-mails
- HTML5 + CSS3 puro (sem dependências externas de front-end)
