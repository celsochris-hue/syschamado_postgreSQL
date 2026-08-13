import os
import uuid
import secrets
import string
from functools import wraps
from datetime import datetime
from zoneinfo import ZoneInfo
import socket

# Força o Python a priorizar conexões IPv4 em conexões de rede (resolve o Errno 101 no Render)
old_getaddrinfo = socket.getaddrinfo
def new_getaddrinfo(*args, **kwargs):
    responses = old_getaddrinfo(*args, **kwargs)
    return [response for response in responses if response[0] == socket.AF_INET]

socket.getaddrinfo = new_getaddrinfo

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, send_from_directory, send_file, abort
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.engine import URL
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from emails import (
    enviar_email, template_status_alterado, template_chamado_criado,
    template_chamado_atribuido, template_senha_redefinida,
)
from relatorios import gerar_excel, gerar_pdf_lista, gerar_pdf_chamado

# ---------------------------------------------------------------------------
# Configuração básica da aplicação
# ---------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {
    "png", "jpg", "jpeg", "gif", "webp",   # imagens
    "pdf", "doc", "docx", "xls", "xlsx",   # documentos
    "txt", "csv", "zip", "log", "mp4"      # outros
}
MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25 MB por upload

# Fuso horário de Brasília — usado em todas as datas gravadas no banco, para que
# "Aberto em", "Última atualização" etc. reflitam o horário local e não UTC.
FUSO_BRASILIA = ZoneInfo("America/Sao_Paulo")


def agora_br():
    """Retorna a data/hora atual no horário de Brasília, sem informação de fuso
    (naive), para gravação consistente nas colunas DateTime do banco."""
    return datetime.now(FUSO_BRASILIA).replace(tzinfo=None)


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "troque-esta-chave-em-producao")

# ---------------------------------------------------------------------------
# Banco de dados: PostgreSQL
# ---------------------------------------------------------------------------
# É possível configurar de duas formas:
#   1) Definindo DATABASE_URL diretamente (ex: usado por Heroku, Render, Railway etc.)
#   2) Definindo as variáveis separadas DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    # Alguns provedores fornecem a URL com o prefixo antigo "postgres://",
    # que não é mais aceito pelo SQLAlchemy 1.4+/2.x (precisa ser "postgresql://").
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    DB_USER = os.environ.get("DB_USER", "postgres")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = os.environ.get("DB_PORT", "5432")
    DB_NAME = os.environ.get("DB_NAME", "chamados")

    # Usar URL.create (em vez de montar a string manualmente com f-string) garante que
    # caracteres especiais/acentuados em usuário ou senha (ex: "@", ":", "ç", "%") sejam
    # codificados corretamente. Colar esses caracteres direto numa string quebra a URL
    # e pode causar erros de conexão difíceis de diagnosticar (ex: UnicodeDecodeError).
    DATABASE_URL = URL.create(
        "postgresql+psycopg2",
        username=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=int(DB_PORT),
        database=DB_NAME,
    )

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,  # evita erros de conexão "caída" com o PostgreSQL
}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

# Configuração de e-mail (SMTP) - defina via variáveis de ambiente ou arquivo .env
app.config["MAIL_ATIVO"] = os.environ.get("MAIL_ATIVO", "False").strip().lower() == "true"
app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", 587))
app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "True").strip().lower() == "true"
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME", "")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD", "")
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER", os.environ.get("MAIL_USERNAME", ""))

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

with app.app_context():
    # Exibe no terminal a URL do banco que o SQLAlchemy está usando no momento
    print("\n" + "="*50)
    print(f"🔗 CONECTADO AO BANCO DE DADOS: {db.engine.url.host}")
    print("="*50 + "\n")

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Faça login para acessar esta página."
login_manager.login_message_category = "aviso"

# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------
STATUS_OPCOES = ["Aberto", "Suspenso", "Encerrado"]
PRIORIDADE_OPCOES = ["Baixa", "Média", "Alta", "Urgente"]
PAPEL_OPCOES = ["usuario", "tecnico", "admin"]


class User(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    papel = db.Column(db.String(20), default="usuario", nullable=False)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    data_criacao = db.Column(db.DateTime, default=agora_br)

    def set_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def check_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)

    def is_admin(self):
        return self.papel == "admin"


class Chamado(db.Model):
    __tablename__ = "chamados"

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(150), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    solicitante = db.Column(db.String(120), nullable=False)
    email_solicitante = db.Column(db.String(150))
    setor = db.Column(db.String(100))
    prioridade = db.Column(db.String(20), default="Média")
    status = db.Column(db.String(20), default="Aberto", nullable=False)
    data_abertura = db.Column(db.DateTime, default=agora_br)
    data_atualizacao = db.Column(db.DateTime, default=agora_br, onupdate=agora_br)

    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    criado_por = db.relationship("User", foreign_keys=[usuario_id], backref="chamados_criados")

    responsavel_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    responsavel = db.relationship("User", foreign_keys=[responsavel_id], backref="chamados_atribuidos")

    anexos = db.relationship(
        "Anexo", backref="chamado", cascade="all, delete-orphan", lazy=True
    )
    historico = db.relationship(
        "HistoricoStatus", backref="chamado", cascade="all, delete-orphan",
        lazy=True, order_by="HistoricoStatus.data.desc()"
    )

    def badge_class(self):
        return {
            "Aberto": "badge-aberto",
            "Suspenso": "badge-suspenso",
            "Encerrado": "badge-encerrado",
        }.get(self.status, "badge-aberto")


class Anexo(db.Model):
    __tablename__ = "anexos"

    id = db.Column(db.Integer, primary_key=True)
    chamado_id = db.Column(db.Integer, db.ForeignKey("chamados.id"), nullable=False)
    nome_original = db.Column(db.String(255), nullable=False)
    nome_arquivo = db.Column(db.String(255), nullable=False)  # nome salvo em disco
    descricao = db.Column(db.String(255))
    data_upload = db.Column(db.DateTime, default=agora_br)


class HistoricoStatus(db.Model):
    __tablename__ = "historico_status"

    id = db.Column(db.Integer, primary_key=True)
    chamado_id = db.Column(db.Integer, db.ForeignKey("chamados.id"), nullable=False)
    status_anterior = db.Column(db.String(20))
    status_novo = db.Column(db.String(20))
    observacao = db.Column(db.String(255))
    data = db.Column(db.DateTime, default=agora_br)

    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    usuario = db.relationship("User", backref="alteracoes_status")


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def admin_required(f):
    """Restringe o acesso da rota apenas a usuários com papel 'admin'."""
    @wraps(f)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash("Acesso restrito a administradores.", "erro")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated_view


def tecnico_ou_admin_required(f):
    """Restringe o acesso da rota a usuários com papel 'tecnico' ou 'admin'.
    Usuários com papel 'usuario' só podem abrir chamados e consultar o status
    dos chamados que eles próprios cadastraram — não podem alterar status,
    atribuir responsável, anexar novas evidências ou excluir chamados."""
    @wraps(f)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated or current_user.papel not in ("tecnico", "admin"):
            flash("Esta ação é restrita a técnicos ou administradores.", "erro")
            return redirect(request.referrer or url_for("index"))
        return f(*args, **kwargs)
    return decorated_view


def pode_acessar_chamado(chamado):
    """Usuários com papel 'usuario' só podem acessar (visualizar) os chamados
    que eles próprios abriram. Técnicos e administradores acessam todos."""
    if current_user.papel in ("tecnico", "admin"):
        return True
    return chamado.usuario_id == current_user.id


def gerar_senha_temporaria(tamanho=10):
    """Gera uma senha aleatória segura para o fluxo de 'esqueci minha senha'."""
    alfabeto = string.ascii_letters + string.digits
    return "".join(secrets.choice(alfabeto) for _ in range(tamanho))


def usuarios_atribuiveis():
    """Retorna usuários que podem ser designados como responsáveis por um chamado
    (técnicos e administradores), ordenados por nome."""
    return (
        User.query
        .filter(User.papel.in_(["tecnico", "admin"]), User.ativo.is_(True))
        .order_by(User.nome)
        .all()
    )


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------
def extensao_permitida(nome_arquivo):
    return "." in nome_arquivo and \
        nome_arquivo.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def salvar_anexo(arquivo, chamado_id):
    """Salva o arquivo em disco com nome único e retorna o registro Anexo."""
    nome_original = secure_filename(arquivo.filename)
    extensao = nome_original.rsplit(".", 1)[1].lower()
    nome_unico = f"{uuid.uuid4().hex}.{extensao}"
    caminho = os.path.join(app.config["UPLOAD_FOLDER"], nome_unico)
    arquivo.save(caminho)

    anexo = Anexo(
        chamado_id=chamado_id,
        nome_original=nome_original,
        nome_arquivo=nome_unico,
    )
    return anexo


def filtrar_chamados():
    """Aplica os filtros de status/busca vindos da querystring e retorna a lista.
    Usuários com papel 'usuario' só visualizam os chamados que eles próprios abriram;
    técnicos e administradores visualizam todos os chamados normalmente."""
    status_filtro = request.args.get("status", "Todos")
    busca = request.args.get("busca", "").strip()

    query = Chamado.query

    if current_user.is_authenticated and current_user.papel == "usuario":
        query = query.filter_by(usuario_id=current_user.id)

    if status_filtro in STATUS_OPCOES:
        query = query.filter_by(status=status_filtro)
    if busca:
        like = f"%{busca}%"
        query = query.filter(
            db.or_(
                Chamado.titulo.ilike(like),
                Chamado.solicitante.ilike(like),
                Chamado.descricao.ilike(like),
            )
        )
    return query.order_by(Chamado.data_abertura.desc()).all()


# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------
@app.route("/registrar", methods=["GET", "POST"])
def registrar():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        confirmar_senha = request.form.get("confirmar_senha", "")

        erros = []
        if not nome:
            erros.append("O nome é obrigatório.")
        if not email or "@" not in email:
            erros.append("Informe um e-mail válido.")
        if len(senha) < 6:
            erros.append("A senha deve ter ao menos 6 caracteres.")
        if senha != confirmar_senha:
            erros.append("As senhas não coincidem.")
        if email and User.query.filter_by(email=email).first():
            erros.append("Já existe uma conta com esse e-mail.")

        if erros:
            for e in erros:
                flash(e, "erro")
            return render_template("registrar.html", form=request.form)

        usuario = User(nome=nome, email=email)
        usuario.set_senha(senha)
        # o primeiro usuário cadastrado no sistema vira administrador
        usuario.papel = "admin" if User.query.count() == 0 else "usuario"

        db.session.add(usuario)
        db.session.commit()
        flash("Conta criada com sucesso! Faça login para continuar.", "sucesso")
        return redirect(url_for("login"))

    return render_template("registrar.html", form={})


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        usuario = User.query.filter_by(email=email).first()
        if usuario and usuario.ativo and usuario.check_senha(senha):
            login_user(usuario)
            flash(f"Bem-vindo(a), {usuario.nome}!", "sucesso")
            proxima = request.args.get("next")
            return redirect(proxima or url_for("index"))

        flash("E-mail ou senha inválidos.", "erro")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Você saiu do sistema.", "sucesso")
    return redirect(url_for("login"))


@app.route("/esqueci-senha", methods=["GET", "POST"])
def esqueci_senha():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        usuario = User.query.filter_by(email=email).first()

        if usuario and usuario.ativo:
            nova_senha = gerar_senha_temporaria()
            usuario.set_senha(nova_senha)
            db.session.commit()

            url_login = url_for("login", _external=True)
            corpo = template_senha_redefinida(usuario, nova_senha, url_login)
            enviado = enviar_email(
                app, usuario.email,
                "Nova senha de acesso - Sistema de Chamados",
                corpo,
            )
            if not enviado and not app.config["MAIL_ATIVO"]:
                # E-mail em modo de teste: a nova senha aparece no console do servidor.
                print(f"[ESQUECI SENHA] Nova senha gerada para {usuario.email}: {nova_senha}")

        # Mensagem sempre genérica, para não revelar se o e-mail existe na base.
        flash(
            "Se o e-mail informado estiver cadastrado, enviamos uma nova senha para ele. "
            "Verifique também a caixa de spam.",
            "sucesso",
        )
        return redirect(url_for("login"))

    return render_template("esqueci_senha.html")


@app.route("/alterar-senha", methods=["GET", "POST"])
@login_required
def alterar_senha():
    if request.method == "POST":
        senha_atual = request.form.get("senha_atual", "")
        nova_senha = request.form.get("nova_senha", "")
        confirmar_nova_senha = request.form.get("confirmar_nova_senha", "")

        if not current_user.check_senha(senha_atual):
            flash("Senha atual incorreta.", "erro")
        elif len(nova_senha) < 6:
            flash("A nova senha deve ter ao menos 6 caracteres.", "erro")
        elif nova_senha != confirmar_nova_senha:
            flash("As senhas não coincidem.", "erro")
        else:
            current_user.set_senha(nova_senha)
            db.session.commit()
            flash("Senha alterada com sucesso!", "sucesso")
            return redirect(url_for("index"))

    return render_template("alterar_senha.html")


# ---------------------------------------------------------------------------
# Rotas principais
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def index():
    chamados = filtrar_chamados()
    status_filtro = request.args.get("status", "Todos")
    busca = request.args.get("busca", "")

    base_query = Chamado.query
    if current_user.papel == "usuario":
        base_query = base_query.filter_by(usuario_id=current_user.id)

    contadores = {
        "Todos": base_query.count(),
        "Aberto": base_query.filter(Chamado.status == "Aberto").count(),
        "Suspenso": base_query.filter(Chamado.status == "Suspenso").count(),
        "Encerrado": base_query.filter(Chamado.status == "Encerrado").count(),
    }

    return render_template(
        "index.html",
        chamados=chamados,
        status_filtro=status_filtro,
        busca=busca,
        contadores=contadores,
        status_opcoes=STATUS_OPCOES,
    )


@app.route("/novo", methods=["GET", "POST"])
@login_required
def novo_chamado():
    if request.method == "POST":
        titulo = request.form.get("titulo", "").strip()
        descricao = request.form.get("descricao", "").strip()
        solicitante = request.form.get("solicitante", "").strip()
        email_solicitante = request.form.get("email_solicitante", "").strip()
        setor = request.form.get("setor", "").strip()
        prioridade = request.form.get("prioridade", "Média")

        erros = []
        if not titulo:
            erros.append("O título é obrigatório.")
        if not descricao:
            erros.append("A descrição é obrigatória.")
        if not solicitante:
            erros.append("O solicitante é obrigatório.")

        arquivos = request.files.getlist("anexos")
        for arquivo in arquivos:
            if arquivo and arquivo.filename and not extensao_permitida(arquivo.filename):
                erros.append(f"Tipo de arquivo não permitido: {arquivo.filename}")

        if erros:
            for e in erros:
                flash(e, "erro")
            return render_template(
                "novo.html",
                prioridade_opcoes=PRIORIDADE_OPCOES,
                form=request.form,
            )

        chamado = Chamado(
            titulo=titulo,
            descricao=descricao,
            solicitante=solicitante,
            email_solicitante=email_solicitante or None,
            setor=setor,
            prioridade=prioridade,
            status="Aberto",
            usuario_id=current_user.id,
        )
        db.session.add(chamado)
        db.session.flush()  # garante chamado.id antes de salvar anexos

        for arquivo in arquivos:
            if arquivo and arquivo.filename:
                anexo = salvar_anexo(arquivo, chamado.id)
                db.session.add(anexo)

        historico = HistoricoStatus(
            chamado_id=chamado.id,
            status_anterior=None,
            status_novo="Aberto",
            observacao="Chamado criado.",
            usuario_id=current_user.id,
        )
        db.session.add(historico)
        db.session.commit()

        # notificação de criação (não bloqueia o fluxo em caso de falha)
        if chamado.email_solicitante:
            url_chamado = url_for("detalhe_chamado", chamado_id=chamado.id, _external=True)
            corpo = template_chamado_criado(chamado, url_chamado)
            enviar_email(app, chamado.email_solicitante,
                         f"Chamado #{chamado.id} aberto com sucesso", corpo)

        flash(f"Chamado #{chamado.id} criado com sucesso!", "sucesso")
        return redirect(url_for("detalhe_chamado", chamado_id=chamado.id))

    form_inicial = {"email_solicitante": current_user.email, "solicitante": current_user.nome}
    return render_template("novo.html", prioridade_opcoes=PRIORIDADE_OPCOES, form=form_inicial)


@app.route("/chamado/<int:chamado_id>")
@login_required
def detalhe_chamado(chamado_id):
    chamado = Chamado.query.get_or_404(chamado_id)

    if not pode_acessar_chamado(chamado):
        flash("Você não tem permissão para visualizar este chamado.", "erro")
        return redirect(url_for("index"))

    return render_template(
        "detalhe.html",
        chamado=chamado,
        status_opcoes=STATUS_OPCOES,
        usuarios_atribuiveis=usuarios_atribuiveis(),
        pode_gerenciar=current_user.papel in ("tecnico", "admin"),
    )


@app.route("/chamado/<int:chamado_id>/status", methods=["POST"])
@login_required
@tecnico_ou_admin_required
def atualizar_status(chamado_id):
    chamado = Chamado.query.get_or_404(chamado_id)
    novo_status = request.form.get("status")
    observacao = request.form.get("observacao", "").strip()

    if novo_status not in STATUS_OPCOES:
        flash("Status inválido.", "erro")
        return redirect(url_for("detalhe_chamado", chamado_id=chamado_id))

    if novo_status != chamado.status:
        status_anterior = chamado.status

        historico = HistoricoStatus(
            chamado_id=chamado.id,
            status_anterior=status_anterior,
            status_novo=novo_status,
            observacao=observacao or None,
            usuario_id=current_user.id,
        )
        db.session.add(historico)
        chamado.status = novo_status
        chamado.data_atualizacao = agora_br()
        db.session.commit()
        flash(f"Status atualizado para '{novo_status}'.", "sucesso")

        # notificação por e-mail ao solicitante
        if chamado.email_solicitante:
            url_chamado = url_for("detalhe_chamado", chamado_id=chamado.id, _external=True)
            corpo = template_status_alterado(chamado, status_anterior, observacao, url_chamado)
            enviado = enviar_email(
                app, chamado.email_solicitante,
                f"Chamado #{chamado.id} - status atualizado para {novo_status}",
                corpo,
            )
            if enviado:
                flash("Notificação por e-mail enviada ao solicitante.", "sucesso")
            elif app.config["MAIL_ATIVO"]:
                flash("Não foi possível enviar a notificação por e-mail.", "aviso")
    else:
        flash("O chamado já está com esse status.", "aviso")

    return redirect(url_for("detalhe_chamado", chamado_id=chamado_id))


@app.route("/chamado/<int:chamado_id>/anexar", methods=["POST"])
@login_required
@tecnico_ou_admin_required
def anexar_arquivo(chamado_id):
    chamado = Chamado.query.get_or_404(chamado_id)
    arquivos = request.files.getlist("anexos")

    if not arquivos or not arquivos[0].filename:
        flash("Selecione ao menos um arquivo.", "erro")
        return redirect(url_for("detalhe_chamado", chamado_id=chamado_id))

    adicionados = 0
    for arquivo in arquivos:
        if not arquivo or not arquivo.filename:
            continue
        if not extensao_permitida(arquivo.filename):
            flash(f"Tipo de arquivo não permitido: {arquivo.filename}", "erro")
            continue
        anexo = salvar_anexo(arquivo, chamado.id)
        db.session.add(anexo)
        adicionados += 1

    if adicionados:
        chamado.data_atualizacao = agora_br()
        db.session.commit()
        flash(f"{adicionados} anexo(s) adicionado(s) com sucesso!", "sucesso")

    return redirect(url_for("detalhe_chamado", chamado_id=chamado_id))


@app.route("/chamado/<int:chamado_id>/anexo/<int:anexo_id>/download")
@login_required
def download_anexo(chamado_id, anexo_id):
    chamado = Chamado.query.get_or_404(chamado_id)

    if not pode_acessar_chamado(chamado):
        flash("Você não tem permissão para acessar este anexo.", "erro")
        return redirect(url_for("index"))

    anexo = Anexo.query.get_or_404(anexo_id)
    if anexo.chamado_id != chamado_id:
        abort(404)

    return send_from_directory(
        app.config["UPLOAD_FOLDER"], anexo.nome_arquivo,
        as_attachment=False, download_name=anexo.nome_original,
    )


@app.route("/chamado/<int:chamado_id>/anexo/<int:anexo_id>/excluir", methods=["POST"])
@login_required
@tecnico_ou_admin_required
def excluir_anexo(chamado_id, anexo_id):
    anexo = Anexo.query.get_or_404(anexo_id)
    if anexo.chamado_id != chamado_id:
        abort(404)

    caminho = os.path.join(app.config["UPLOAD_FOLDER"], anexo.nome_arquivo)
    if os.path.exists(caminho):
        os.remove(caminho)

    db.session.delete(anexo)
    db.session.commit()
    flash("Anexo removido.", "sucesso")
    return redirect(url_for("detalhe_chamado", chamado_id=chamado_id))


@app.route("/chamado/<int:chamado_id>/excluir", methods=["POST"])
@login_required
@tecnico_ou_admin_required
def excluir_chamado(chamado_id):
    chamado = Chamado.query.get_or_404(chamado_id)

    for anexo in chamado.anexos:
        caminho = os.path.join(app.config["UPLOAD_FOLDER"], anexo.nome_arquivo)
        if os.path.exists(caminho):
            os.remove(caminho)

    db.session.delete(chamado)
    db.session.commit()
    flash(f"Chamado #{chamado_id} excluído.", "sucesso")
    return redirect(url_for("index"))


@app.route("/chamado/<int:chamado_id>/atribuir", methods=["POST"])
@login_required
@tecnico_ou_admin_required
def atribuir_responsavel(chamado_id):
    chamado = Chamado.query.get_or_404(chamado_id)
    responsavel_id = request.form.get("responsavel_id", "").strip()

    if not responsavel_id:
        chamado.responsavel_id = None
        db.session.commit()
        flash("Responsável removido do chamado.", "sucesso")
        return redirect(url_for("detalhe_chamado", chamado_id=chamado_id))

    responsavel = User.query.get_or_404(int(responsavel_id))
    if responsavel.papel not in ("tecnico", "admin"):
        flash("Só é possível atribuir chamados a técnicos ou administradores.", "erro")
        return redirect(url_for("detalhe_chamado", chamado_id=chamado_id))

    chamado.responsavel_id = responsavel.id
    chamado.data_atualizacao = agora_br()
    db.session.commit()
    flash(f"Chamado atribuído a {responsavel.nome}.", "sucesso")

    if responsavel.email:
        url_chamado = url_for("detalhe_chamado", chamado_id=chamado.id, _external=True)
        corpo = template_chamado_atribuido(chamado, responsavel, url_chamado)
        enviar_email(
            app, responsavel.email,
            f"Chamado #{chamado.id} atribuído a você",
            corpo,
        )

    return redirect(url_for("detalhe_chamado", chamado_id=chamado_id))


# ---------------------------------------------------------------------------
# Painel de administração
# ---------------------------------------------------------------------------
@app.route("/admin/usuarios")
@login_required
@admin_required
def admin_usuarios():
    usuarios = User.query.order_by(User.data_criacao).all()
    return render_template("admin_usuarios.html", usuarios=usuarios, papel_opcoes=PAPEL_OPCOES)


@app.route("/admin/usuarios/<int:user_id>/status", methods=["POST"])
@login_required
@admin_required
def admin_alternar_status(user_id):
    usuario = User.query.get_or_404(user_id)

    if usuario.id == current_user.id:
        flash("Você não pode desativar a própria conta.", "erro")
        return redirect(url_for("admin_usuarios"))

    usuario.ativo = not usuario.ativo
    db.session.commit()
    estado = "ativada" if usuario.ativo else "desativada"
    flash(f"Conta de {usuario.nome} {estado}.", "sucesso")
    return redirect(url_for("admin_usuarios"))


@app.route("/admin/usuarios/<int:user_id>/papel", methods=["POST"])
@login_required
@admin_required
def admin_alterar_papel(user_id):
    usuario = User.query.get_or_404(user_id)
    novo_papel = request.form.get("papel")

    if novo_papel not in PAPEL_OPCOES:
        flash("Papel inválido.", "erro")
        return redirect(url_for("admin_usuarios"))

    if usuario.id == current_user.id and novo_papel != "admin":
        flash("Você não pode remover seu próprio acesso de administrador.", "erro")
        return redirect(url_for("admin_usuarios"))

    usuario.papel = novo_papel
    db.session.commit()
    flash(f"Papel de {usuario.nome} atualizado para '{novo_papel}'.", "sucesso")
    return redirect(url_for("admin_usuarios"))


@app.route("/admin/usuarios/<int:user_id>/excluir", methods=["POST"])
@login_required
@admin_required
def admin_excluir_usuario(user_id):
    usuario = User.query.get_or_404(user_id)

    if usuario.id == current_user.id:
        flash("Você não pode excluir a própria conta.", "erro")
        return redirect(url_for("admin_usuarios"))

    tem_vinculos = usuario.chamados_criados or usuario.chamados_atribuidos or usuario.alteracoes_status
    if tem_vinculos:
        flash(
            f"Não é possível excluir {usuario.nome}: existem chamados ou históricos vinculados a essa "
            "conta. Desative a conta em vez de excluí-la.",
            "erro",
        )
        return redirect(url_for("admin_usuarios"))

    db.session.delete(usuario)
    db.session.commit()
    flash(f"Usuário {usuario.nome} excluído.", "sucesso")
    return redirect(url_for("admin_usuarios"))


# ---------------------------------------------------------------------------
# Exportação (Excel / PDF)
# ---------------------------------------------------------------------------
@app.route("/exportar/excel")
@login_required
def exportar_excel():
    chamados = filtrar_chamados()
    buffer = gerar_excel(chamados)
    nome_arquivo = f"chamados_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(
        buffer, as_attachment=True, download_name=nome_arquivo,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/exportar/pdf")
@login_required
def exportar_pdf():
    chamados = filtrar_chamados()
    status_filtro = request.args.get("status", "Todos")
    buffer = gerar_pdf_lista(chamados, status_filtro)
    nome_arquivo = f"chamados_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    return send_file(buffer, as_attachment=True, download_name=nome_arquivo, mimetype="application/pdf")


@app.route("/chamado/<int:chamado_id>/pdf")
@login_required
def exportar_pdf_chamado(chamado_id):
    chamado = Chamado.query.get_or_404(chamado_id)

    if not pode_acessar_chamado(chamado):
        flash("Você não tem permissão para exportar este chamado.", "erro")
        return redirect(url_for("index"))

    buffer = gerar_pdf_chamado(chamado)
    nome_arquivo = f"chamado_{chamado.id}.pdf"
    return send_file(buffer, as_attachment=True, download_name=nome_arquivo, mimetype="application/pdf")


# ---------------------------------------------------------------------------
# Inicialização do banco de dados
# ---------------------------------------------------------------------------
def inicializar_banco():
    with app.app_context():
        db.create_all()


if __name__ == "__main__":
    inicializar_banco()
    app.run(debug=True, host="0.0.0.0", port=5000)
