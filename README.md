# Mountain Passes API  

## Установка
1. Установи PostgreSQL
2. Создай БД: `createdb mountain_passes`
3. Выполни SQL: `psql -d mountain_passes -f init_db.sql`
4. Установи зависимости: `pip install -r requirements.txt`
5. Скопируй .env.example в .env и настрой
6. Запусти: `uvicorn main:app --reload`