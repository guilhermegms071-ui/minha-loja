"""
Popula o banco com produtos fake para testar o sistema de ponta a ponta
sem depender de acesso real ao Bling.

Uso:
    flask --app run.py shell < scripts/seed_fake_data.py
ou:
    python scripts/seed_fake_data.py   (rodando de dentro do venv/container)

NÃO rode isso contra o banco de produção — é só para ambiente de teste.
"""
import os
import sys

# Garante que a raiz do projeto está no path, não importa de onde o script é chamado
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models import Produto

PRODUTOS_FAKE = [
    {"bling_id": "FAKE-001", "nome": "Bateria iPhone 11 3110mAh", "categoria": "baterias", "preco": 89.90, "estoque": 12},
    {"bling_id": "FAKE-002", "nome": "Bateria iPhone XR 2942mAh", "categoria": "baterias", "preco": 79.90, "estoque": 8},
    {"bling_id": "FAKE-003", "nome": "Bateria iPhone 12 2815mAh", "categoria": "baterias", "preco": 39.90, "estoque": 0},  # sem estoque de propósito, pra testar o bloqueio
    {"bling_id": "FAKE-004", "nome": "Tela iPhone 11 (Incl. Touch)", "categoria": "telas", "preco": 249.90, "estoque": 5},
    {"bling_id": "FAKE-005", "nome": "Tela iPhone XR", "categoria": "telas", "preco": 219.90, "estoque": 3},
    {"bling_id": "FAKE-006", "nome": "Conector de Carga iPhone 11", "categoria": "conectores", "preco": 39.90, "estoque": 20},
    {"bling_id": "FAKE-007", "nome": "Conector de Carga iPhone XR", "categoria": "conectores", "preco": 34.90, "estoque": 15},
    {"bling_id": "FAKE-008", "nome": "Câmera Traseira iPhone 12", "categoria": "cameras", "preco": 129.90, "estoque": 4},
    {"bling_id": "FAKE-009", "nome": "Carcaça iPhone 11", "categoria": "carcacas", "preco": 159.90, "estoque": 6},
    {"bling_id": "FAKE-010", "nome": "Cabo USB-C Original", "categoria": "cabos", "preco": 29.90, "estoque": 50},
]


def seed():
    app = create_app()
    with app.app_context():
        criados, atualizados = 0, 0
        for p in PRODUTOS_FAKE:
            produto = Produto.query.filter_by(bling_id=p["bling_id"]).first()
            if produto is None:
                produto = Produto(bling_id=p["bling_id"])
                db.session.add(produto)
                criados += 1
            else:
                atualizados += 1

            produto.nome = p["nome"]
            produto.categoria = p["categoria"]
            produto.preco = p["preco"]
            produto.estoque = p["estoque"]
            produto.ativo = True

        db.session.commit()
        print(f"Seed concluído: {criados} produtos criados, {atualizados} atualizados.")
        print("Lembrete: esses produtos têm bling_id fake (FAKE-XXX) — remova-os")
        print("antes de rodar o /bling/sync real, ou eles ficarão órfãos no cache.")


if __name__ == "__main__":
    seed()
