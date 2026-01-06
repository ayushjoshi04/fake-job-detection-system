import os
from dotenv import load_dotenv
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{os.getenv('MYSQL_USER','root')}:{os.getenv('MYSQL_PASSWORD','')}"
        f"@{os.getenv('MYSQL_HOST','localhost')}/{os.getenv('MYSQL_DB','fakejobdb')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
