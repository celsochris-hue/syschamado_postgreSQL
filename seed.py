"""
Script opcional para popular o banco com um usuário e alguns chamados de exemplo.
Execute com: python seed.py

Usuário de teste criado:
  E-mail: admin@empresa.com
  Senha:  admin123
"""
from datetime import timedelta
from app import app, db, User, Chamado, HistoricoStatus, agora_br

exemplos = [
    {
        "titulo": "Impressora do 2º andar não imprime",
        "descricao": "A impressora HP do setor financeiro está apresentando erro de papel emperrado constante.",
        "solicitante": "Maria Silva",
        "email_solicitante": "maria.silva@empresa.com",
        "setor": "Financeiro",
        "prioridade": "Média",
        "status": "Aberto",
    },
    {
        "titulo": "Solicitação de acesso ao sistema ERP",
        "descricao": "Novo colaborador precisa de acesso ao módulo de compras do ERP.",
        "solicitante": "João Pereira",
        "email_solicitante": "joao.pereira@empresa.com",
        "setor": "Compras",
        "prioridade": "Alta",
        "status": "Suspenso",
    },
    {
        "titulo": "Queda de internet no galpão B",
        "descricao": "Conexão intermitente desde ontem à tarde, já foi reiniciado o roteador sem sucesso.",
        "solicitante": "Ana Souza",
        "email_solicitante": "ana.souza@empresa.com",
        "setor": "Logística",
        "prioridade": "Urgente",
        "status": "Encerrado",
    },
    {
        "titulo": "Solicitação de férias do colaborador",
        "descricao": "Gestor solicitou aprovação de férias de 15 dias para colaborador do setor comercial.",
        "solicitante": "Patrícia Lima",
        "email_solicitante": "patricia.lima@empresa.com",
        "setor": "RH",  # setor RH → chamado restrito a perfis 'rh' e 'admin'
        "prioridade": "Alta",
        "status": "Aberto",
    },
]

with app.app_context():
    db.create_all()

    admin = User.query.filter_by(email="admin@empresa.com").first()
    if not admin:
        admin = User(nome="Administrador", email="admin@empresa.com", papel="admin")
        admin.set_senha("admin123")
        db.session.add(admin)
        db.session.flush()
        print("Usuário admin criado -> login: admin@empresa.com | senha: admin123")

    tecnico = User.query.filter_by(email="tecnico@empresa.com").first()
    if not tecnico:
        tecnico = User(nome="Carlos Andrade", email="tecnico@empresa.com", papel="tecnico")
        tecnico.set_senha("tecnico123")
        db.session.add(tecnico)
        db.session.flush()
        print("Usuário técnico criado -> login: tecnico@empresa.com | senha: tecnico123")

    rh = User.query.filter_by(email="rh@empresa.com").first()
    if not rh:
        rh = User(nome="Renata Borges", email="rh@empresa.com", papel="rh")
        rh.set_senha("rh123")
        db.session.add(rh)
        db.session.flush()
        print("Usuário RH criado -> login: rh@empresa.com | senha: rh123")

    for i, dados in enumerate(exemplos):
        chamado = Chamado(
            titulo=dados["titulo"],
            descricao=dados["descricao"],
            solicitante=dados["solicitante"],
            email_solicitante=dados["email_solicitante"],
            setor=dados["setor"],
            prioridade=dados["prioridade"],
            status=dados["status"],
            data_abertura=agora_br() - timedelta(days=3 - i),
            usuario_id=admin.id,
            responsavel_id=tecnico.id if i == 1 else None,
        )
        db.session.add(chamado)
        db.session.flush()
        db.session.add(HistoricoStatus(
            chamado_id=chamado.id,
            status_anterior=None,
            status_novo="Aberto",
            observacao="Chamado criado (exemplo).",
            usuario_id=admin.id,
        ))
        if dados["status"] != "Aberto":
            db.session.add(HistoricoStatus(
                chamado_id=chamado.id,
                status_anterior="Aberto",
                status_novo=dados["status"],
                observacao="Atualização automática (exemplo).",
                usuario_id=admin.id,
            ))

    db.session.commit()
    print("Banco populado com usuário admin e chamados de exemplo!")
