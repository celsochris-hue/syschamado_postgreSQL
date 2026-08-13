"""
Módulo responsável pelo envio de notificações por e-mail.
Usa smtplib puro (sem dependências extras) e funciona com qualquer
provedor SMTP (Gmail, Outlook, SendGrid, servidor corporativo, etc.).
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def enviar_email(app, destinatario, assunto, corpo_html):
    """
    Envia um e-mail HTML. Retorna True em caso de sucesso, False caso contrário.
    Se o envio de e-mail estiver desativado (MAIL_ATIVO=False), apenas
    registra a mensagem no console — útil para desenvolvimento/testes.
    """
    if not destinatario:
        return False

    if not app.config.get("MAIL_ATIVO"):
        print(f"[EMAIL DESATIVADO] Para: {destinatario} | Assunto: {assunto}")
        print("Defina MAIL_ATIVO=True e configure o SMTP para enviar e-mails de verdade.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"] = app.config["MAIL_DEFAULT_SENDER"]
        msg["To"] = destinatario

        msg.attach(MIMEText(corpo_html, "html", "utf-8"))

        with smtplib.SMTP(app.config["MAIL_SERVER"], app.config["MAIL_PORT"], timeout=30) as servidor:
            if app.config.get("MAIL_USE_TLS"):
                servidor.starttls()
            if app.config.get("MAIL_USERNAME"):
                servidor.login(app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"])
            servidor.sendmail(app.config["MAIL_DEFAULT_SENDER"], destinatario, msg.as_string())

        return True
    except Exception as exc:
        print(f"[ERRO AO ENVIAR EMAIL] destinatário={destinatario} | erro={exc}")
        return False


def template_status_alterado(chamado, status_anterior, observacao, url_chamado):
    """Gera o corpo HTML do e-mail de mudança de status."""
    obs_html = f"<p><strong>Observação:</strong> {observacao}</p>" if observacao else ""
    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #1f2333; background:#f4f5f9; padding: 24px;">
        <div style="max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 10px;
                    overflow: hidden; border: 1px solid #e4e6ef;">
            <div style="background: #4f46e5; color: #fff; padding: 18px 24px;">
                <h2 style="margin:0; font-size: 1.1rem;">Chamado #{chamado.id} atualizado</h2>
            </div>
            <div style="padding: 24px;">
                <p>Olá, <strong>{chamado.solicitante}</strong>!</p>
                <p>O status do seu chamado foi alterado:</p>
                <p style="font-size: 1rem;">
                    <span style="background:#eef0fb; color:#6b7080; padding:4px 10px; border-radius:999px;">{status_anterior or '—'}</span>
                    &rarr;
                    <span style="background:#dbeafe; color:#2563eb; padding:4px 10px; border-radius:999px; font-weight:700;">{chamado.status}</span>
                </p>
                {obs_html}
                <p><strong>Título:</strong> {chamado.titulo}</p>
                <p style="margin-top: 24px;">
                    <a href="{url_chamado}" style="background:#4f46e5; color:#fff; padding:10px 18px;
                       border-radius:8px; text-decoration:none; font-weight:600;">Ver chamado</a>
                </p>
            </div>
            <div style="padding: 14px 24px; background:#fafafe; color:#9ca3af; font-size:0.75rem;">
                Sistema de Chamados &middot; e-mail automático, não responda.
            </div>
        </div>
    </body>
    </html>
    """


def template_senha_redefinida(usuario, nova_senha, url_login):
    """Gera o corpo HTML do e-mail com a nova senha de acesso (fluxo 'esqueci minha senha').

    Observação técnica: a senha original NÃO pode ser recuperada, pois é armazenada
    apenas como hash (irreversível) no banco de dados — prática padrão de segurança.
    Por isso, ao solicitar a recuperação, uma nova senha temporária é gerada
    automaticamente e enviada por e-mail, substituindo a anterior."""
    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #1f2333; background:#f4f5f9; padding: 24px;">
        <div style="max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 10px;
                    overflow: hidden; border: 1px solid #e4e6ef;">
            <div style="background: #4f46e5; color: #fff; padding: 18px 24px;">
                <h2 style="margin:0; font-size: 1.1rem;">Nova senha de acesso</h2>
            </div>
            <div style="padding: 24px;">
                <p>Olá, <strong>{usuario.nome}</strong>!</p>
                <p>Recebemos uma solicitação de recuperação de senha para sua conta no
                   Sistema de Chamados. Sua nova senha de acesso é:</p>
                <p style="font-size: 1.3rem; font-weight: 700; letter-spacing: 1px;
                          background:#eef0fb; color:#4f46e5; padding:12px 18px;
                          border-radius:8px; text-align:center;">{nova_senha}</p>
                <p>Por segurança, recomendamos que você altere essa senha assim que
                   entrar no sistema, na opção <strong>"Alterar senha"</strong>.</p>
                <p style="margin-top: 24px;">
                    <a href="{url_login}" style="background:#4f46e5; color:#fff; padding:10px 18px;
                       border-radius:8px; text-decoration:none; font-weight:600;">Fazer login</a>
                </p>
                <p style="color:#9ca3af; font-size:0.8rem; margin-top:20px;">
                    Se você não solicitou essa alteração, entre em contato com o
                    administrador do sistema o quanto antes.
                </p>
            </div>
            <div style="padding: 14px 24px; background:#fafafe; color:#9ca3af; font-size:0.75rem;">
                Sistema de Chamados &middot; e-mail automático, não responda.
            </div>
        </div>
    </body>
    </html>
    """


def template_chamado_atribuido(chamado, responsavel, url_chamado):
    """Gera o corpo HTML do e-mail avisando o técnico que um chamado foi atribuído a ele."""
    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #1f2333; background:#f4f5f9; padding: 24px;">
        <div style="max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 10px;
                    overflow: hidden; border: 1px solid #e4e6ef;">
            <div style="background: #4f46e5; color: #fff; padding: 18px 24px;">
                <h2 style="margin:0; font-size: 1.1rem;">Novo chamado atribuído a você</h2>
            </div>
            <div style="padding: 24px;">
                <p>Olá, <strong>{responsavel.nome}</strong>!</p>
                <p>O chamado abaixo foi atribuído a você:</p>
                <p><strong>#{chamado.id} — {chamado.titulo}</strong></p>
                <p><strong>Solicitante:</strong> {chamado.solicitante}</p>
                <p><strong>Prioridade:</strong> {chamado.prioridade}</p>
                <p><strong>Status atual:</strong> {chamado.status}</p>
                <p style="margin-top: 24px;">
                    <a href="{url_chamado}" style="background:#4f46e5; color:#fff; padding:10px 18px;
                       border-radius:8px; text-decoration:none; font-weight:600;">Ver chamado</a>
                </p>
            </div>
            <div style="padding: 14px 24px; background:#fafafe; color:#9ca3af; font-size:0.75rem;">
                Sistema de Chamados &middot; e-mail automático, não responda.
            </div>
        </div>
    </body>
    </html>
    """


def template_chamado_criado(chamado, url_chamado):
    """Gera o corpo HTML do e-mail de confirmação de abertura de chamado."""
    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #1f2333; background:#f4f5f9; padding: 24px;">
        <div style="max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 10px;
                    overflow: hidden; border: 1px solid #e4e6ef;">
            <div style="background: #16a34a; color: #fff; padding: 18px 24px;">
                <h2 style="margin:0; font-size: 1.1rem;">Chamado #{chamado.id} aberto com sucesso</h2>
            </div>
            <div style="padding: 24px;">
                <p>Olá, <strong>{chamado.solicitante}</strong>!</p>
                <p>Seu chamado foi registrado e já está com o status <strong>{chamado.status}</strong>.</p>
                <p><strong>Título:</strong> {chamado.titulo}</p>
                <p><strong>Prioridade:</strong> {chamado.prioridade}</p>
                <p style="margin-top: 24px;">
                    <a href="{url_chamado}" style="background:#16a34a; color:#fff; padding:10px 18px;
                       border-radius:8px; text-decoration:none; font-weight:600;">Acompanhar chamado</a>
                </p>
            </div>
            <div style="padding: 14px 24px; background:#fafafe; color:#9ca3af; font-size:0.75rem;">
                Sistema de Chamados &middot; e-mail automático, não responda.
            </div>
        </div>
    </body>
    </html>
    """
