from modules.models import init_db

if __name__ == '__main__':
    print("Створення таблиць в базі даних...")
    init_db()
    print("✅ База даних успішно створена!") 