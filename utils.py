from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer
from flask import url_for

def send_reset_email(user, mail, app):
    s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    token = s.dumps(user.email, salt='email-confirm')
    link = url_for('reset_token', token=token, _external=True)

    msg = Message("Password Reset Request",
                    sender=app.config['MAIL_USERNAME'],
                    recipients=[user.email])
    msg.body = f'''To reset your password, click the following link:
{link}
If you didn't request this, please ignore this email.'''
    mail.send(msg)

def verify_reset_token(token, app, expiration=3600):
    s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    try:
        email = s.loads(token, salt='email-confirm', max_age=expiration)
    except Exception:
        return None
    return email
