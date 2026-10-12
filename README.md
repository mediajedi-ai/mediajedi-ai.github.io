# Наши в НХЛ — автоматическая сводка

Файлы:
- `build.py` — скрипт: берёт данные с api-web.nhle.com, находит россиян, пишет `index.html` и `data.json`
- `template.html` — шаблон страницы (дизайн), в него подставляются данные
- `.github/workflows/update.yml` — расписание запуска (07:00, 09:00, 11:00, 13:00 по Екатеринбургу) и ручная кнопка «Run workflow»

Страница: https://mediajedi-ai.github.io
