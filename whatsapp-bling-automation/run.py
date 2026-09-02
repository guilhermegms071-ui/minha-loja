from app import create_app
from app.extensions import db

app = create_app()


@app.cli.command("init-db")
def init_db():
    """Cria as tabelas do banco. Rode com: flask --app run.py init-db"""
    with app.app_context():
        db.create_all()
    print("Banco de dados inicializado.")


if __name__ == "__main__":
    # host="0.0.0.0" — só pra rodar "python run.py" localmente aceitar
    # conexão de outros dispositivos na mesma rede (ex: celular via IP tipo
    # 192.168.0.x), não só de 127.0.0.1. Não afeta produção/Docker: lá quem
    # sobe o servidor é o gunicorn (ver Dockerfile), que já usa --bind
    # 0.0.0.0:5000 por conta própria, sem passar por este bloco.
    app.run(debug=True, port=5000, host="0.0.0.0")
