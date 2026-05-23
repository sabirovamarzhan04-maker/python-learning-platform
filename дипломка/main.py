from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, Boolean, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, declarative_base
from pydantic import BaseModel
from openai import OpenAI
from fastapi.responses import FileResponse
import re
import json
import os
import docx

# -----------------------------------------
# 🔑 OPENAI
# -----------------------------------------
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)
# -----------------------------------------
# ⚙️ DATABASE
# -----------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)

Base = declarative_base()

SessionLocal = sessionmaker(bind=engine)
# -----------------------------------------
# 📦 MODELS
# -----------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    email = Column(String, unique=True)
    role = Column(String, default="student")

    results = relationship("Result", back_populates="user")
    quiz_results = relationship("TopicQuizResult", back_populates="user")


class Result(Base):
    __tablename__ = "results"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    topic = Column(String)
    task_number = Column(Integer)
    answer = Column(Text)
    feedback = Column(Text)
    completed = Column(Boolean, default=False)

    user = relationship("User", back_populates="results")


class TopicQuizResult(Base):
    __tablename__ = "topic_quiz_results"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    topic = Column(String)
    correct = Column(Integer)
    total = Column(Integer)
    answers = Column(Text, nullable=True)
    teacher_grade = Column(Integer, nullable=True)   # 0-10, set by teacher
    teacher_comment = Column(Text, nullable=True)     # teacher's comment

    user = relationship("User", back_populates="quiz_results")



Base.metadata.create_all(bind=engine)

# Обеспечиваем наличие колонок role и answers в уже существующей БД (SQLite)
try:
    with engine.connect() as conn:
        # Для users
        info = conn.execute(text("PRAGMA table_info(users)"))
        cols = [row[1] for row in info]
        if "role" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR"))
            
        # Для topic_quiz_results
        info_quiz = conn.execute(text("PRAGMA table_info(topic_quiz_results)"))
        cols_quiz = [row[1] for row in info_quiz]
        if "answers" not in cols_quiz:
            conn.execute(text("ALTER TABLE topic_quiz_results ADD COLUMN answers TEXT"))
        if "teacher_grade" not in cols_quiz:
            conn.execute(text("ALTER TABLE topic_quiz_results ADD COLUMN teacher_grade INTEGER"))
        if "teacher_comment" not in cols_quiz:
            conn.execute(text("ALTER TABLE topic_quiz_results ADD COLUMN teacher_comment TEXT"))
            
        conn.commit()
except Exception:
    # Если не удалось изменить структуру (другая БД и т.п.) — просто игнорируем
    pass

# -----------------------------------------
# 🚀 FASTAPI
# -----------------------------------------
app = FastAPI(title="Python Learning Platform")
app.mount("/static", StaticFiles(directory="дипломка"), name="static")
@app.get("/")
async def home():
    return FileResponse("дипломка/index.html")

# Раздача HTML/JS/CSS
# app.mount("/", StaticFiles(directory="static", html=True), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------
# 🧑‍🎓 INPUT MODELS
# -----------------------------------------
class TaskRequest(BaseModel):
    topic: str

class CheckRequest(BaseModel):
    username: str
    email: str
    answer: str
    topic: str
    task_number: int


class UserUpdateRequest(BaseModel):
    old_username: str
    old_email: str
    username: str
    email: str
    role: str | None = None


class TopicQuizSubmit(BaseModel):
    username: str
    email: str
    topic: str
    correct: int
    total: int
    answers: str | None = None


class TeacherGradeRequest(BaseModel):
    teacher_username: str
    student_username: str
    student_email: str
    topic: str
    grade: int             # 0-10
    comment: str | None = None


# -----------------------------------------
# 🎯 QUIZ DATA (7 вопросов по теме)
# -----------------------------------------
QUIZZES = {
    "Python тіліне кіріспе": [
        {
            "type": "test",
            "question": "Что такое Python?",
            "options": [
                "Операционная система",
                "Язык программирования высокого уровня",
                "СУБД",
                "Браузер",
            ],
            "correct": 2,
        },
        {
            "type": "test",
            "question": "Какое расширение чаще всего имеют файлы с программами на Python?",
            "options": [".py", ".pt", ".pyt", ".exe"],
            "correct": 1,
        },
        {
            "type": "test",
            "question": "Как правильно вывести строку 'Hello, world!' в Python?",
            "options": [
                "echo('Hello, world!')",
                "printf('Hello, world!')",
                "print('Hello, world!')",
                "cout << 'Hello, world!';",
            ],
            "correct": 3,
        },
        {
            "type": "theory",
            "question": "Что такое интерпретатор Python?",
        },
        {
            "type": "theory",
            "question": "Для чего в программе на Python нужна функция input()?",
        },
        {
            "type": "code_fill",
            "question": "Дополните код так, чтобы программа запросила имя пользователя и вывела 'Hello, <имя>!'",
            "template": "name = ______('Введите ваше имя: ')\nprint('Hello, ' + ______ + '!')",
            "correct": ["input", "name"],
        },
        {
            "type": "code_fill",
            "question": "Дополните код, чтобы программа вывела на экран число 10.",
            "template": "x = 5\ny = 5\nresult = x + y\n______(result)",
            "correct": ["print"],
        },
    ],
    "Цикл": [
        {
            "type": "test",
            "question": "Для чего в Python используются циклы?",
            "options": [
                "Для определения функций",
                "Для многократного повторения однотипных действий",
                "Для импорта модулей",
                "Для обработки исключений",
            ],
            "correct": 2,
        },
        {
            "type": "test",
            "question": "Какой цикл удобнее использовать, когда заранее известно количество повторений?",
            "options": ["while", "for", "if", "match"],
            "correct": 2,
        },
        {
            "type": "test",
            "question": "Что делает оператор break в цикле?",
            "options": [
                "Пропускает одну итерацию",
                "Выходит из цикла полностью",
                "Повторяет текущую итерацию",
                "Ничего не делает",
            ],
            "correct": 2,
        },
        {
            "type": "theory",
            "question": "В чём отличие цикла while от цикла for?",
        },
        {
            "type": "theory",
            "question": "Что произойдёт, если в цикле while условие никогда не станет ложным?",
        },
        {
            "type": "code_fill",
            "question": "Дополните код, чтобы вывести числа от 1 до 5 включительно.",
            "template": "for i in ______(1, ______):\n    print(i)",
            "correct": ["range", "6"],
        },
        {
            "type": "code_fill",
            "question": "Дополните код, чтобы цикл while выводил числа от 0 до 3.",
            "template": "x = 0\nwhile x ______ 4:\n    print(x)\n    x = x ______ 1",
            "correct": ["<", "+"],
        },
    ],
    "Бірөлшемді тізімдер": [
        {
            "type": "test",
            "question": "Как создать пустой список в Python?",
            "options": ["list()", "{}", "()", "empty[]"],
            "correct": 1,
        },
        {
            "type": "test",
            "question": "Как получить длину списка a?",
            "options": ["size(a)", "len(a)", "length(a)", "count(a)"],
            "correct": 2,
        },
        {
            "type": "test",
            "question": "Какой индекс имеет первый элемент списка в Python?",
            "options": ["-1", "0", "1", "2"],
            "correct": 2,
        },
        {
            "type": "theory",
            "question": "Что такое список (list) в Python и для чего он используется?",
        },
        {
            "type": "theory",
            "question": "Чем отличается обращение к элементу списка по индексу от перебора списка в цикле for?",
        },
        {
            "type": "code_fill",
            "question": "Дополните код, чтобы вывести третий элемент списка nums.",
            "template": "nums = [10, 20, 30, 40]\nprint(nums[____])",
            "correct": ["2"],
        },
        {
            "type": "code_fill",
            "question": "Дополните код, чтобы добавить число 5 в конец списка a.",
            "template": "a = [1, 2, 3, 4]\na.____(5)\nprint(a)",
            "correct": ["append"],
        },
    ],
    "Массив": [
        {
            "type": "test",
            "question": "Какой встроенный тип в Python чаще всего используется как аналог массива?",
            "options": ["dict", "list", "set", "tuple"],
            "correct": 2,
        },
        {
            "type": "test",
            "question": "Какой метод списка изменяет порядок элементов на обратный?",
            "options": ["reverse()", "invert()", "back()", "flip()"],
            "correct": 1,
        },
        {
            "type": "test",
            "question": "Что делает выражение arr.sort()?",
            "options": [
                "Возвращает новый отсортированный список и не меняет arr",
                "Сортирует список arr на месте",
                "Удаляет дубликаты из arr",
                "Переворачивает список arr",
            ],
            "correct": 2,
        },
        {
            "type": "theory",
            "question": "В чём разница между доступом к элементу массива (списка) и перебором массива в цикле?",
        },
        {
            "type": "theory",
            "question": "Зачем может понадобиться сортировка массива (списка) в алгоритмах?",
        },
        {
            "type": "code_fill",
            "question": "Дополните код, чтобы найти максимум в массиве arr.",
            "template": "arr = [3, 7, 2, 9, 4]\nmax_val = ______(arr)\nprint(max_val)",
            "correct": ["max"],
        },
        {
            "type": "code_fill",
            "question": "Дополните код, чтобы посчитать сумму всех элементов массива.",
            "template": "arr = [1, 2, 3, 4]\ntotal = ______(arr)\nprint(total)",
            "correct": ["sum"],
        },
    ],
    "Екі өлшемді массивтер": [
        {
            "type": "test",
            "question": "Как в Python обычно представляют двумерный массив?",
            "options": [
                "Список кортежей",
                "Список списков",
                "Словарь списков",
                "Строку",
            ],
            "correct": 2,
        },
        {
            "type": "test",
            "question": "Как обратиться ко второму элементу первой строки двумерного массива a?",
            "options": ["a[2][1]", "a[1][2]", "a[0][1]", "a[1][0]"],
            "correct": 3,
        },
        {
            "type": "test",
            "question": "Какой фрагмент кода правильно обходит все элементы двумерного списка matrix?",
            "options": [
                "for x in matrix: print(x)",
                "for i in matrix:\n    for j in i:\n        print(j)",
                "for i in range(matrix): print(i)",
                "while matrix: print(matrix)",
            ],
            "correct": 2,
        },
        {
            "type": "theory",
            "question": "Приведи пример задачи, где удобно использовать двумерный массив.",
        },
        {
            "type": "theory",
            "question": "Что означает выражение len(matrix) и len(matrix[0]) для двумерного массива?",
        },
        {
            "type": "code_fill",
            "question": "Дополните код, чтобы создать двумерный массив 2×3, заполненный нулями.",
            "template": "rows = 2\ncols = 3\nmatrix = [[0 for j in range(cols)] for ______ in ______]\nprint(matrix)",
            "correct": ["i", "range(rows)"],
        },
        {
            "type": "code_fill",
            "question": "Дополните код, чтобы вывести все элементы двумерного массива matrix по строкам.",
            "template": "for row in matrix:\n    for value in ______:\n        print(______, end=' ')\n    print()",
            "correct": ["row", "value"],
        },
    ],
    "Ішкі бағдарламалар": [
        {
            "type": "test",
            "question": "Как в Python объявить функцию?",
            "options": [
                "function my_func():",
                "def my_func():",
                "func my_func():",
                "define my_func():",
            ],
            "correct": 2,
        },
        {
            "type": "test",
            "question": "Что делает оператор return в функции?",
            "options": [
                "Завершает программу",
                "Печатает значение на экран",
                "Возвращает значение из функции и завершает её выполнение",
                "Перезапускает функцию",
            ],
            "correct": 3,
        },
        {
            "type": "test",
            "question": "Как правильно вызвать функцию add(a, b) с аргументами 2 и 3?",
            "options": ["add = (2, 3)", "add(2, 3)", "add[2, 3]", "call add 2 3"],
            "correct": 2,
        },
        {
            "type": "theory",
            "question": "Зачем в программах используют функции? Назови минимум две причины.",
        },
        {
            "type": "theory",
            "question": "Чем отличаются параметры функции и аргументы функции?",
        },
        {
            "type": "code_fill",
            "question": "Дополните код, чтобы функция square возвращала квадрат числа.",
            "template": "def square(x):\n    ______ x * x\n\nresult = square(5)\nprint(result)",
            "correct": ["return"],
        },
        {
            "type": "code_fill",
            "question": "Дополните код, чтобы определить функцию greet(name), которая печатает приветствие.",
            "template": "______ greet(name):\n    print('Hello,', ______)\n\ngreet('Ali')",
            "correct": ["def", "name"],
        },
    ],
}


# -----------------------------------------
# 🔹 ПОЛЬЗОВАТЕЛИ
# -----------------------------------------
@app.post("/add_user/")
def add_user(username: str, email: str, role: str = "student"):
    db = SessionLocal()
    exists = db.query(User).filter(
        (User.username == username) | (User.email == email)
    ).first()

    if exists:
        db.close()
        return {"message": "Пайдаланушы бұрын тіркелген!"}

    user = User(username=username, email=email, role=role or "student")
    db.add(user)
    db.commit()
    db.close()
    return {"message": "✅ Тіркеу сәтті!"}


@app.get("/check_user/")
def check_user(username: str, email: str):
    db = SessionLocal()
    user = db.query(User).filter(
        User.username == username, User.email == email
    ).first()
    db.close()

    if user:
        return {
            "exists": True,
            "role": user.role or "student",
        }
    return {"exists": False}


@app.get("/users")
def list_users():
    db = SessionLocal()
    users = db.query(User).all()
    data = [
        {"id": u.id, "username": u.username, "email": u.email, "role": u.role}
        for u in users
    ]
    db.close()
    return data


@app.post("/update_user/")
def update_user(req: UserUpdateRequest):
    db = SessionLocal()

    user = db.query(User).filter(
        User.username == req.old_username,
        User.email == req.old_email,
    ).first()

    if not user:
        db.close()
        return {"message": "Пайдаланушы табылмады"}

    existing = db.query(User).filter(
        User.id != user.id,
        ((User.username == req.username) | (User.email == req.email)),
    ).first()

    if existing:
        db.close()
        return {"message": "Бұл логин немесе email басқа қолданушыда бар"}

    user.username = req.username
    user.email = req.email
    # Role changes are NOT allowed from profile — role is set only at registration
    # Only keep existing role
    final_role = user.role or "student"

    db.commit()
    db.close()

    return {"message": "Аккаунт сәтті жаңартылды", "username": req.username, "email": req.email, "role": final_role}


@app.post("/quiz_result/")
def save_quiz_result(req: TopicQuizSubmit):
    db = SessionLocal()

    user = db.query(User).filter(
        User.username == req.username,
        User.email == req.email,
    ).first()

    if not user:
        user = User(username=req.username, email=req.email, role="student")
        db.add(user)
        db.commit()
        db.refresh(user)

    quiz = db.query(TopicQuizResult).filter(
        TopicQuizResult.user_id == user.id,
        TopicQuizResult.topic == req.topic,
    ).first()

    if quiz:
        if req.answers:
            quiz.answers = req.answers
    else:
        quiz = TopicQuizResult(
            user_id=user.id,
            topic=req.topic,
            correct=req.correct,
            total=req.total,
            answers=req.answers,
        )
        db.add(quiz)

    db.commit()
    db.close()

    return {"message": "Тақырыптық тест нәтижесі сақталды"}

# -----------------------------------------
# 👩‍🏫 Результаты квизов для учителя
# -----------------------------------------
@app.get("/teacher/topic_results/")
def get_teacher_topic_results(topic: str):
    db = SessionLocal()
    # Возвращаем всех студентов, сдавших квиз по topic
    results = db.query(TopicQuizResult).filter(TopicQuizResult.topic == topic).all()
    
    data = []
    for r in results:
        data.append({
            "username": r.user.username,
            "email": r.user.email,
            "correct": r.correct,
            "total": r.total,
            "answers": r.answers,  # JSON string
            "teacher_grade": r.teacher_grade,
            "teacher_comment": r.teacher_comment,
        })
    db.close()
    return {"topic": topic, "results": data}


@app.post("/teacher/set_grade/")
def set_teacher_grade(req: TeacherGradeRequest):
    """Учитель вручную ставит оценку студенту за тест/практику."""
    db = SessionLocal()

    # Проверяем, что вызывающий — учитель или admin
    teacher = db.query(User).filter(
        User.username == req.teacher_username,
    ).first()
    if not teacher or (teacher.role != "teacher" and teacher.username != "admin"):
        db.close()
        return {"message": "Тек мұғалім баға қоя алады", "ok": False}

    student = db.query(User).filter(
        User.username == req.student_username,
        User.email == req.student_email,
    ).first()
    if not student:
        db.close()
        return {"message": "Студент табылмады", "ok": False}

    quiz = db.query(TopicQuizResult).filter(
        TopicQuizResult.user_id == student.id,
        TopicQuizResult.topic == req.topic,
    ).first()

    if not quiz:
        db.close()
        return {"message": "Бұл тақырып бойынша нәтиже табылмады", "ok": False}

    quiz.teacher_grade = max(0, min(10, req.grade))
    quiz.teacher_comment = req.comment
    db.commit()
    db.close()

    return {"message": "Баға сәтті қойылды", "ok": True}



# -----------------------------------------
# 🧠 Генерация *10 ЗАДАНИЙ* по теме
# -----------------------------------------
DOCX_MAPPING = {
    "1.1.1": "1.1.1.Python тілінің анықтамасы.docx",
    "1.1.2": "1.1.2.Сызықты және шартты алгоритмдер.docx",
    "1.2.1": "1.2.1.Цикл операторы.docx",
    "1.2.2": "1.2.2.Цикл операторы while.docx",
    "1.2.3": "1.2.3.Цикл операторлары және функциялар.docx",
    "1.3.1": "1.3.1.Тізімнің негізгі түсініктері.docx",
    "1.3.2": "1.3.2.Бірөлшемді тізімдер.docx",
    "2.1.1": "2.1.1.Массивтің құрылымы.docx",
    "2.1.2": "2.1.2.Массивті сұрыптаудың әдістері.docx",
    "2.2.1": "2.2.1.Екі өлшемді массивтер.docx",
    "2.2.2": "2.2.2.Екі өлшемді массив NumPy (Векторлар, матрицалар).docx",
    "2.3.1": "2.3.1. Рекурсия.docx",
    "2.3.2": "2.3.2. Жолдар.docx",
    "2.3.3": "2.3.3. Сөздіктер.docx",
    "2.3.4": "2.3.4. Кортеждер.docx",
}

def get_lecture_text(topic_id: str) -> str:
    filename = DOCX_MAPPING.get(topic_id)
    if not filename:
        return ""
    filepath = os.path.join("lectures", filename)
    if not os.path.exists(filepath):
        return ""
    try:
        doc = docx.Document(filepath)
        text = "\n".join([p.text.strip() for p in doc.paragraphs if p.text.strip()])
        return text[:5000] # Ограничим до 5000 символов, чтобы не превысить лимит токенов
    except Exception as e:
        print("Error reading docx:", e)
        return ""

@app.post("/generate_tasks/")
def generate_tasks(req: TaskRequest):
    topic = req.topic
    internal_topic = QUIZ_MAPPING.get(topic, topic)
    lecture_content = get_lecture_text(topic)
    context_msg = "Сен Python мұғалімісің. Берілген тақырып бойынша студентке арналған 10 қысқа ЖӘНЕ БІР-БІРІНЕН ЕРЕКШЕ сұрақ тізімін JSON форматында қайтар.\n"
    if lecture_content:
        context_msg += f"Мына лекция материалына сүйеніп сұрақтар құрастыр:\n---\n{lecture_content}\n---\n"
        
    
    context_msg += (
        "Маңызды: Дәл 10 тапсырма құрастыр және ретін сақта:\n"
        "1-5: тест сұрақтары.\n"
        "6-8: ашық сұрақтар.\n"
        "9-10: үлкенірек Python кодын талдау/толықтыру тапсырмасы.\n\n"

        "Тек JSON қайтар:\n"
        "{ \"questions\": [...] }\n\n"

        "1-5 тест форматы:\n"
        "{ \"type\":\"test\", \"question\":\"...\", \"options\":[\"A\",\"B\",\"C\",\"D\"], \"correct\":1, \"explanation\":\"Неге дұрыс екенін түсіндір\" }\n\n"

        "6-8 ашық сұрақ форматы:\n"
        "{ \"type\":\"theory\", \"question\":\"...\", \"teacher_check\":true }\n\n"

        "9-10 код тапсырмалары өте нақты және түсінікті болсын.\n"
        "Код тапсырмалары IDE-дегі шынайы Python кодына ұқсасын.\n"
        "Код кемінде 5-10 жол болсын.\n"
        "Тапсырма міндетті түрде берілген тақырыпқа қатысты болсын.\n\n"

        "Code тапсырма форматы:\n"
        "{\n"
        "  \"type\":\"code\",\n"
        "  \"question\":\"Экранда берілген нәтиже шығу үшін кодтағы бос орынды толтырыңыз немесе қатені табыңыз\",\n"
        "  \"template\":\"толық Python коды, ішінде ______ немесе қате жол болсын\",\n"
        "  \"expected_output\":\"экранда қандай нәтиже шығуы керек\",\n"
        "  \"answer\":[\"дұрыс жауап\"],\n"
        "  \"explanation\":\"неге дәл осы жауап дұрыс екенін түсіндір\"\n"
        "}\n\n"

        "Code тапсырма ережелері:\n"
        "- Тек бір қысқа жол емес, толық код көрсетілсін.\n"
        "- Код оқушыға түсінікті болсын.\n"
        "- Мысалы: for, if, while, print, list, function сияқты нақты Python темалары қолданылсын.\n"
        "- Кейде бос орын ______ болсын.\n"
        "- Кейде кодтағы қатені тапсын.\n"
        "- Кейде output бойынша missing code тапсын.\n"
        "- expected_output міндетті түрде болсын.\n"
        "- Код visually IDE style-ға ұқсайтын болсын.\n"

        "Қатаң ереже:\n"
        "- 1-5 тек test болсын.\n"
        "- 6-8 тек theory болсын, жауап нұсқасы болмайды.\n"
        "- 9-10 тек code болсын.\n"
        "- code тапсырмаларында код ұзын болсын, screenshot сияқты code block ретінде көрінетіндей.\n"
        "- Барлық тапсырма тек берілген тақырыпқа қатысты болсын.\n"
        "- Барлық мәтін қазақ тілінде болсын."
        "Сұрақтар сапалы, логикалық және адам құрастырғандай болсын.\n"
        "Өте оңай немесе мағынасыз сұрақтар болмасын.\n"
        "Python синтаксисіне сай нақты сұрақтар берілсін.\n"
        "Тест сұрақтары beginner student үшін пайдалы болсын.\n"
        "Мысалы:\n"
        "- Код не шығарады?\n"
        "- Қай жерде қате?\n"
        "- Қай оператор қолданылады?\n"
        "- Цикл неше рет орындалады?\n"
        "- Айнымалы не сақтайды?\n"
        "- print функциясы не істейді?\n\n"

        "Мынадай жаман сұрақтар БОЛМАСЫН:\n"
        "- '#' нені білдіреді?\n"
        "- Python жақсы тіл ме?\n"
        "- while бар ма?\n"
        "- өте қысқа немесе бір символдық жауаптар.\n\n"

        "Сұрақтар нақты лекция тақырыбына байланысты болсын.\n"
    )

    # Пытаемся попросить GPT сгенерировать 10 структурированных вопросов по теме
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": context_msg,
                },
                {
                    "role": "user",
                    "content": f"{internal_topic} ({topic}) тақырыбы бойынша дәл 10 тапсырма дайында: 5 тест, 3 ашық сұрақ, 2 кодтағы бос орынды толықтыру.",
                },
            ],
            max_tokens=3500,
            temperature=0.7
        )

        text = response.choices[0].message.content

        try:
            parsed_json = json.loads(text)
            questions = parsed_json.get("questions", [])
        except Exception:
            raise

        clean_questions = []
        for q in questions:
            if isinstance(q, dict) and "type" in q and "question" in q:
                clean_questions.append(q)
            if len(clean_questions) >= 10:
                break

        if not clean_questions:
            raise ValueError("no valid questions")

        return {"topic": topic, "questions": clean_questions}

    except Exception as e:
        print(f"[generate_tasks] GPT error for topic={topic}: {e}")
        fallback = PRACTICE_FALLBACK.get(topic, [])

        if not fallback:
            fallback = PRACTICE_FALLBACK.get("general", [])

        return {"topic": topic, "questions": fallback}

# -----------------------------------------
# 📋 FALLBACK ВОПРОСЫ (когда GPT недоступен)
# -----------------------------------------
PRACTICE_FALLBACK = {
    "1.1.1": [
        {"type": "test", "question": "Python тілін кім жасады?", "options": ["Гвидо ван Россум", "Линус Торвальдс", "Билл Гейтс", "Джеймс Гослинг"], "correct": 1},
        {"type": "test", "question": "Python тілінде комментарий қалай жазылады?", "options": ["// текст", "# текст", "/* текст */", "-- текст"], "correct": 2},
        {"type": "test", "question": "print() функциясы не істейді?", "options": ["Мәнді сақтайды", "Экранға шығарады", "Кірісті оқиды", "Циклды бастайды"], "correct": 2},
        {"type": "code", "question": "Экранға 'Сәлем, Әлем!' деп шығаратын кодты толықтырыңыз:", "template": "____('Сәлем, Әлем!')", "answer": ["print"]},
        {"type": "test", "question": "Python-да айнымалы типін қалай анықтайды?", "options": ["Алдын ала жариялау керек", "Автоматты анықтайды", "Тек int болады", "Типтер жоқ"], "correct": 2},
        {"type": "code", "question": "x-ке 5 мәнін меншіктеңіз:", "template": "x ____ 5", "answer": ["="]},
        {"type": "theory", "question": "Python тілінің интерпретатор тілі деп аталу себебін түсіндіріңіз."},
        {"type": "test", "question": "Python-да жолдық тип қандай?", "options": ["int", "float", "str", "bool"], "correct": 3},
        {"type": "code", "question": "Пайдаланушыдан ат сұрайтын кодты толықтырыңыз:", "template": "name = ____('Атыңызды енгізіңіз: ')", "answer": ["input"]},
        {"type": "theory", "question": "Python тілінде негізгі деректер типтерін (int, float, str, bool) мысалдармен түсіндіріңіз."}
    ],
    "1.1.2": [
        {"type": "test", "question": "Сызықты алгоритм дегеніміз не?", "options": ["Тармақталу бар алгоритм", "Бірізді орындалатын алгоритм", "Қайталанатын алгоритм", "Рекурсивті алгоритм"], "correct": 2},
        {"type": "test", "question": "if операторы қандай алгоритмге жатады?", "options": ["Сызықты", "Шартты (тармақталу)", "Циклдік", "Рекурсивті"], "correct": 2},
        {"type": "code", "question": "Егер x > 0 болса 'Оң сан' деп шығаратын шартты толықтырыңыз:", "template": "____ x > 0:\n    print('Оң сан')", "answer": ["if"]},
        {"type": "test", "question": "else блогы қашан орындалады?", "options": ["Әрқашан", "if шарты True болғанда", "if шарты False болғанда", "Ешқашан"], "correct": 3},
        {"type": "code", "question": "elif қолданатын шартты толықтырыңыз:", "template": "if x > 0:\n    print('Оң')\n____ x == 0:\n    print('Нөл')\nelse:\n    print('Теріс')", "answer": ["elif"]},
        {"type": "theory", "question": "Шартты алгоритм мен сызықты алгоритмнің айырмашылығын мысалмен түсіндіріңіз."},
        {"type": "test", "question": "Python-да 'және' логикалық операторы қалай жазылады?", "options": ["&&", "and", "AND", "&"], "correct": 2},
        {"type": "test", "question": "Python-да 'немесе' логикалық операторы қалай жазылады?", "options": ["||", "or", "OR", "|"], "correct": 2},
        {"type": "code", "question": "a мен b-нің максимумын табатын шартты жазыңыз:", "template": "if a ____ b:\n    print(a)\nelse:\n    print(b)", "answer": [">"]},
        {"type": "theory", "question": "if-elif-else конструкциясын нақты мысалмен түсіндіріңіз."}
    ],
    "1.2.1": [
        {"type": "test", "question": "for циклы не үшін қолданылады?", "options": ["Шарт тексеру", "Қайталау (итерация)", "Функция жасау", "Файл оқу"], "correct": 2},
        {"type": "code", "question": "0-ден 4-ке дейін сандарды шығаратын циклды толықтырыңыз:", "template": "for i in ____(5):\n    print(i)", "answer": ["range"]},
        {"type": "test", "question": "range(1, 10, 2) нәтижесі не?", "options": ["1,2,3...10", "1,3,5,7,9", "2,4,6,8,10", "1,10,2"], "correct": 2},
        {"type": "code", "question": "Тізім элементтерін шығаратын циклды толықтырыңыз:", "template": "fruits = ['алма', 'банан', 'апельсін']\nfor fruit ____ fruits:\n    print(fruit)", "answer": ["in"]},
        {"type": "test", "question": "range(5) неше рет қайталанады?", "options": ["4", "5", "6", "1"], "correct": 2},
        {"type": "theory", "question": "for циклында range() функциясының 3 параметрін (start, stop, step) мысалмен түсіндіріңіз."},
        {"type": "code", "question": "1-ден 10-ға дейін сандар қосындысын табыңыз:", "template": "total = 0\nfor i in range(1, ____):\n    total += i", "answer": ["11"]},
        {"type": "test", "question": "break операторы не істейді?", "options": ["Циклды жалғастырады", "Циклды тоқтатады", "Қайтадан бастайды", "Шартты тексереді"], "correct": 2},
        {"type": "code", "question": "continue операторын қолданыңыз:", "template": "for i in range(10):\n    if i == 5:\n        ____\n    print(i)", "answer": ["continue"]},
        {"type": "theory", "question": "break және continue операторларының айырмашылығын түсіндіріңіз."}
    ],
    "1.2.2": [
        {"type": "test", "question": "while циклы for-дан қалай ерекшеленеді?", "options": ["Тезірек жұмыс істейді", "Шарт ақиқат болғанша қайталанады", "Тек сандармен жұмыс істейді", "Айырмашылығы жоқ"], "correct": 2},
        {"type": "code", "question": "while циклын толықтырыңыз:", "template": "i = 0\n____ i < 5:\n    print(i)\n    i += 1", "answer": ["while"]},
        {"type": "test", "question": "while True деген не?", "options": ["Бір рет орындалады", "Шексіз цикл", "Қате", "False-ке тең"], "correct": 2},
        {"type": "code", "question": "Пайдаланушы 'exit' жазғанша цикл жұмыс істесін:", "template": "while True:\n    cmd = input('Команда: ')\n    if cmd == ____:\n        break", "answer": ["'exit'"]},
        {"type": "theory", "question": "while циклында шексіз циклдан қалай сақтануға болады?"},
        {"type": "test", "question": "while 0: блогы неше рет орындалады?", "options": ["Шексіз", "0 рет", "1 рет", "Қате береді"], "correct": 2},
        {"type": "code", "question": "Санды кері есептеу циклын жазыңыз:", "template": "n = 10\nwhile n ____ 0:\n    print(n)\n    n -= 1", "answer": [">"]},
        {"type": "test", "question": "while циклында i += 1 не істейді?", "options": ["Мәнді кемітеді", "Мәнді 1-ге арттырады", "Мәнді нөлге теңейді", "Циклды тоқтатады"], "correct": 2},
        {"type": "theory", "question": "while мен for циклдарын қашан қолдану керек? Мысалмен түсіндіріңіз."},
        {"type": "code", "question": "1-ден бастап жұп сандарды 20-ға дейін шығарыңыз:", "template": "i = 2\nwhile i <= 20:\n    print(i)\n    i ____ 2", "answer": ["+="]},
    ],
    "1.2.3": [
        {"type": "test", "question": "Python-да функция қалай анықталады?", "options": ["function name():", "def name():", "func name():", "fn name():"], "correct": 2},
        {"type": "code", "question": "Функция анықтаңыз:", "template": "____ salam():\n    print('Сәлем!')", "answer": ["def"]},
        {"type": "test", "question": "return операторы не істейді?", "options": ["Функцияны шақырады", "Мәнді қайтарады", "Циклды бастайды", "Шарт тексереді"], "correct": 2},
        {"type": "code", "question": "Екі санның қосындысын қайтаратын функцияны толықтырыңыз:", "template": "def add(a, b):\n    ____ a + b", "answer": ["return"]},
        {"type": "theory", "question": "Функция деген не және ол не үшін қолданылады?"},
        {"type": "test", "question": "Функцияның параметрі деген не?", "options": ["Функция аты", "Кіріс деректер", "Қайтарылатын мән", "Циклдағы айнымалы"], "correct": 2},
        {"type": "code", "question": "Функцияны шақырыңыз:", "template": "def greet(name):\n    print(f'Сәлем, {name}!')\n\n____('Айдар')", "answer": ["greet"]},
        {"type": "test", "question": "Функцияда *args не істейді?", "options": ["Бір аргумент қабылдайды", "Кез келген саны аргумент қабылдайды", "Қате береді", "Сөздік қабылдайды"], "correct": 2},
        {"type": "code", "question": "Факториал функциясын толықтырыңыз:", "template": "def factorial(n):\n    if n <= 1:\n        return 1\n    return n * ____(n - 1)", "answer": ["factorial"]},
        {"type": "theory", "question": "Локальді және глобальді айнымалылардың айырмашылығын түсіндіріңіз."}
    ],
    "1.3.1": [
        {"type": "test", "question": "Python-да тізім (list) қандай жақшада жазылады?", "options": ["()", "{}", "[]", "<>"], "correct": 3},
        {"type": "code", "question": "Бос тізім жасаңыз:", "template": "my_list = ____", "answer": ["[]"]},
        {"type": "test", "question": "len() функциясы не қайтарады?", "options": ["Элемент мәнін", "Элементтер санын", "Ең үлкен элементті", "Индексті"], "correct": 2},
        {"type": "code", "question": "Тізімге элемент қосыңыз:", "template": "fruits = ['алма']\nfruits.____('банан')", "answer": ["append"]},
        {"type": "test", "question": "Тізімнің бірінші элементінің индексі нешеден басталады?", "options": ["1", "0", "-1", "auto"], "correct": 2},
        {"type": "theory", "question": "Тізім (list) деген не? Массивтен қандай айырмашылығы бар?"},
        {"type": "code", "question": "Тізімнен элемент жойыңыз:", "template": "nums = [1, 2, 3, 4]\nnums.____(2)", "answer": ["remove"]},
        {"type": "test", "question": "nums[-1] не қайтарады?", "options": ["Бірінші элемент", "Соңғы элемент", "Қате", "-1 индекстегі элемент"], "correct": 2},
        {"type": "code", "question": "Тізімді сұрыптаңыз:", "template": "nums = [3, 1, 4, 1, 5]\nnums.____()", "answer": ["sort"]},
        {"type": "theory", "question": "Тізімнің негізгі әдістерін (append, remove, sort, pop) мысалдармен жазыңыз."}
    ],
    "1.3.2": [
        {"type": "test", "question": "Бірөлшемді тізім дегеніміз не?", "options": ["Тізім ішіндегі тізім", "Жай тізім (бір қатарлы)", "Сөздік", "Кортеж"], "correct": 2},
        {"type": "code", "question": "Тізімнен кесу (slice) жасаңыз:", "template": "nums = [10, 20, 30, 40, 50]\nresult = nums[1:____]", "answer": ["4"]},
        {"type": "test", "question": "nums[::2] не қайтарады?", "options": ["Барлық элементтер", "Жұп индекстегі элементтер", "Тақ элементтер", "Қате"], "correct": 2},
        {"type": "code", "question": "List comprehension қолданып квадраттар тізімін жасаңыз:", "template": "squares = [x**2 for x in ____(5)]", "answer": ["range"]},
        {"type": "theory", "question": "Тізімді кесу (slicing) дегеніміз не? nums[start:stop:step] мысалмен түсіндіріңіз."},
        {"type": "test", "question": "List comprehension не үшін қолданылады?", "options": ["Тізімді жою", "Қысқаша тізім жасау", "Тізімді сұрыптау", "Файл оқу"], "correct": 2},
        {"type": "code", "question": "Тізімді кері аударыңыз:", "template": "nums = [1, 2, 3, 4, 5]\nnums.____()", "answer": ["reverse"]},
        {"type": "test", "question": "max() функциясы тізімнен не қайтарады?", "options": ["Минимумды", "Максимумды", "Ұзындықты", "Орташаны"], "correct": 2},
        {"type": "code", "question": "Тізімдегі элементтер қосындысын табыңыз:", "template": "nums = [1, 2, 3, 4, 5]\ntotal = ____(nums)", "answer": ["sum"]},
        {"type": "theory", "question": "enumerate() функциясын тізіммен қалай қолданады? Мысал жазыңыз."}
    ],
    "2.1.1": [
        {"type": "test", "question": "Массив дегеніміз не?", "options": ["Кез келген тип деректер жиыны", "Бір типті деректер жиыны", "Функция", "Сыныпc"], "correct": 2},
        {"type": "code", "question": "Массив жасаңыз:", "template": "import array\narr = array.array('i', [1, 2, ____, 4])", "answer": ["3"]},
        {"type": "test", "question": "Python-да массив модулі қайсы?", "options": ["numpy", "array", "list", "collections"], "correct": 2},
        {"type": "theory", "question": "Массив (array) мен тізімнің (list) айырмашылығын түсіндіріңіз."},
        {"type": "code", "question": "Массив элементін алыңыз:", "template": "arr = [10, 20, 30]\nprint(arr[____])", "answer": ["1"]},
        {"type": "test", "question": "Массив индексі неден басталады?", "options": ["1", "0", "-1", "auto"], "correct": 2},
        {"type": "code", "question": "Массивтен элемент жою:", "template": "arr = [1, 2, 3, 4]\ndel arr[____]", "answer": ["2"]},
        {"type": "theory", "question": "Массив қандай жағдайда тізімнен тиімді? Мысалмен көрсетіңіз."},
        {"type": "test", "question": "Массивтегі іздеу алгоритмі:", "options": ["Сызықты іздеу", "Бинарлық іздеу", "Екеуіде дұрыс", "Ешқайсысы"], "correct": 3},
        {"type": "code", "question": "Массивте элемент бар ма тексеріңіз:", "template": "arr = [5, 10, 15]\nif 10 ____ arr:\n    print('Табылды')", "answer": ["in"]}
    ],
    "2.1.2": [
        {"type": "test", "question": "Bubble sort (көпіршікті сұрыптау) алгоритмінің күрделілігі:", "options": ["O(n)", "O(n log n)", "O(n²)", "O(1)"], "correct": 3},
        {"type": "theory", "question": "Көпіршікті сұрыптау (Bubble Sort) алгоритмін қадамдарымен түсіндіріңіз."},
        {"type": "code", "question": "Bubble sort ішкі циклін толықтырыңыз:", "template": "for i in range(len(arr)):\n    for j in range(len(arr)-1-i):\n        if arr[j] ____ arr[j+1]:\n            arr[j], arr[j+1] = arr[j+1], arr[j]", "answer": [">"]},
        {"type": "test", "question": "Selection sort не істейді?", "options": ["Ең кіші элементті тауып орнына қояды", "Элементтерді кездейсоқ ауыстырады", "Тізімді бөледі", "Рекурсия қолданады"], "correct": 1},
        {"type": "theory", "question": "Selection sort пен Bubble sort-ты салыстырыңыз."},
        {"type": "test", "question": "Python-ның sorted() функциясы қай алгоритмді қолданады?", "options": ["Bubble Sort", "Quick Sort", "Timsort", "Merge Sort"], "correct": 3},
        {"type": "code", "question": "Python-да тізімді сұрыптаңыз:", "template": "nums = [5, 2, 8, 1, 9]\nsorted_nums = ____(nums)", "answer": ["sorted"]},
        {"type": "test", "question": "Insertion sort қай жағдайда тиімді?", "options": ["Үлкен деректер", "Кіші немесе дерлік сұрыпталған деректер", "Кездейсоқ деректер", "Ешқашан"], "correct": 2},
        {"type": "code", "question": "Кері сұрыптау жасаңыз:", "template": "nums = [3, 1, 4, 1, 5]\nnums.sort(reverse=____)", "answer": ["True"]},
        {"type": "theory", "question": "O(n²) мен O(n log n) күрделілігін мысалмен салыстырыңыз."}
    ],
    "2.2.1": [
        {"type": "test", "question": "Екі өлшемді массив дегеніміз не?", "options": ["Бір қатар", "Матрица (қатар мен бағандар)", "Бір элемент", "Функция"], "correct": 2},
        {"type": "code", "question": "2D массив жасаңыз:", "template": "matrix = [[1, 2, 3], [4, 5, ____], [7, 8, 9]]", "answer": ["6"]},
        {"type": "test", "question": "matrix[1][2] нәтижесі (matrix = [[1,2,3],[4,5,6]]):", "options": ["2", "5", "6", "4"], "correct": 3},
        {"type": "code", "question": "2D массивтің барлық элементтерін шығарыңыз:", "template": "for row in matrix:\n    for elem ____ row:\n        print(elem)", "answer": ["in"]},
        {"type": "theory", "question": "Екі өлшемді массив қандай жағдайларда қолданылады? 3 мысал келтіріңіз."},
        {"type": "test", "question": "3x3 матрицада неше элемент бар?", "options": ["3", "6", "9", "12"], "correct": 3},
        {"type": "code", "question": "Матрицаның бірінші қатарын алыңыз:", "template": "matrix = [[1,2],[3,4],[5,6]]\nfirst_row = matrix[____]", "answer": ["0"]},
        {"type": "theory", "question": "Матрица транспонирлеу дегеніміз не? Мысалмен көрсетіңіз."},
        {"type": "test", "question": "len(matrix) 2D массивте не қайтарады?", "options": ["Жалпы элемент саны", "Қатар саны", "Баған саны", "Қате"], "correct": 2},
        {"type": "code", "question": "3x3 нөлдік матрица жасаңыз:", "template": "matrix = [[0]*3 for _ in ____(3)]", "answer": ["range"]}
    ],
    "2.2.2": [
        {"type": "test", "question": "NumPy кітапханасы не үшін қолданылады?", "options": ["Веб-сайт жасау", "Ғылыми есептеулер мен массивтер", "Суреттерді өңдеу", "Деректер базасы"], "correct": 2},
        {"type": "code", "question": "NumPy массиві жасаңыз:", "template": "import numpy as np\narr = np.____([ 1, 2, 3, 4])", "answer": ["array"]},
        {"type": "test", "question": "NumPy массивінің Python тізімінен артықшылығы:", "options": ["Баяу жұмыс істейді", "Тез жұмыс істейді", "Аз жады қолданады", "B және C дұрыс"], "correct": 4},
        {"type": "code", "question": "NumPy-де нөлдік матрица:", "template": "import numpy as np\nzeros = np.____(( 3, 3))", "answer": ["zeros"]},
        {"type": "theory", "question": "NumPy массиві мен Python тізімінің айырмашылығын түсіндіріңіз."},
        {"type": "test", "question": "np.shape не қайтарады?", "options": ["Элемент мәнін", "Массив өлшемдерін", "Деректер типін", "Индексті"], "correct": 2},
        {"type": "code", "question": "Матрицаларды көбейтіңіз:", "template": "import numpy as np\na = np.array([[1, 2], [3, 4]])\nb = np.array([[5, 6], [7, 8]])\nresult = np.____(a, b)", "answer": ["dot"]},
        {"type": "test", "question": "NumPy-де reshape не істейді?", "options": ["Элементтерді жояды", "Массив формасын өзгертеді", "Сұрыптайды", "Қосады"], "correct": 2},
        {"type": "code", "question": "1-ден 9-ға дейін массив жасап 3x3 матрицаға айналдырыңыз:", "template": "import numpy as np\narr = np.arange(1, 10)\nmatrix = arr.____(( 3, 3))", "answer": ["reshape"]},
        {"type": "theory", "question": "Вектор мен матрица ұғымдарын түсіндіріп, NumPy-де қалай жасалатынын көрсетіңіз."}
    ],
    "2.3.1": [
        {"type": "test", "question": "Рекурсия дегеніміз не?", "options": ["Цикл түрі", "Функцияның өзін-өзі шақыруы", "Тізім әдісі", "Сыныптың қасиеті"], "correct": 2},
        {"type": "code", "question": "Факториал рекурсиясын толықтырыңыз:", "template": "def factorial(n):\n    if n <= 1:\n        return 1\n    return n * ____(n - 1)", "answer": ["factorial"]},
        {"type": "test", "question": "Рекурсияда базалық шарт не үшін керек?", "options": ["Жылдамдық үшін", "Шексіз шақыру тоқтату үшін", "Есте сақтау үшін", "Шарт тексеру үшін"], "correct": 2},
        {"type": "theory", "question": "Рекурсия мен итерацияның (цикл) айырмашылығын мысалмен көрсетіңіз."},
        {"type": "code", "question": "Фибоначчи рекурсиясын толықтырыңыз:", "template": "def fib(n):\n    if n <= 1:\n        return n\n    return fib(n-1) + fib(____)", "answer": ["n-2"]},
        {"type": "test", "question": "Python-да рекурсия тереңдігінің шегі:", "options": ["100", "500", "1000", "Шексіз"], "correct": 3},
        {"type": "code", "question": "Тізім элементтерін рекурсия арқылы қосу:", "template": "def sum_list(lst):\n    if len(lst) == 0:\n        return 0\n    return lst[0] + ____(lst[1:])", "answer": ["sum_list"]},
        {"type": "theory", "question": "Рекурсия қашан тиімді, қашан тиімсіз? Мысалмен түсіндіріңіз."},
        {"type": "test", "question": "Рекурсия кестесі (memoization) не істейді?", "options": ["Жадты тазалайды", "Нәтижелерді кэштейді", "Қате тудырады", "Функцияны жояды"], "correct": 2},
        {"type": "code", "question": "Санның дәрежесін рекурсия арқылы есептеңіз:", "template": "def power(base, exp):\n    if exp == 0:\n        return 1\n    return base * ____(base, exp - 1)", "answer": ["power"]}
    ],
    "2.3.2": [
        {"type": "test", "question": "Python-да жолдар (strings) қандай тырнақшамен жазылады?", "options": ["Тек жалғыз ''", "Тек қос \"\"", "Екеуі де дұрыс", "Тек ``` ```"], "correct": 3},
        {"type": "code", "question": "Жолды бас әріпке айналдырыңыз:", "template": "text = 'сәлем'\nresult = text.____()", "answer": ["upper"]},
        {"type": "test", "question": "len('Python') нәтижесі:", "options": ["5", "6", "7", "Қате"], "correct": 2},
        {"type": "code", "question": "Жолдан кесу жасаңыз:", "template": "s = 'Hello World'\nresult = s[0:____]", "answer": ["5"]},
        {"type": "theory", "question": "Python-да f-string форматтау қалай жұмыс істейді? Мысал жазыңыз."},
        {"type": "test", "question": "'hello'.replace('l', 'r') нәтижесі:", "options": ["herlo", "herro", "hello", "heLLo"], "correct": 2},
        {"type": "code", "question": "Жолды бөліңіз:", "template": "text = 'алма,банан,апельсін'\nfruits = text.____(',') ", "answer": ["split"]},
        {"type": "test", "question": "'  hello  '.strip() нәтижесі:", "options": ["  hello  ", "hello  ", "  hello", "hello"], "correct": 4},
        {"type": "code", "question": "Жолда символ бар ма тексеріңіз:", "template": "if 'a' ____ 'apple':\n    print('Табылды')", "answer": ["in"]},
        {"type": "theory", "question": "Жолдардың негізгі әдістерін (split, join, replace, strip, find) мысалмен жазыңыз."}
    ],
    "2.3.3": [
        {"type": "test", "question": "Сөздік (dictionary) қандай жақшада жазылады?", "options": ["[]", "()", "{}", "<>"], "correct": 3},
        {"type": "code", "question": "Сөздік жасаңыз:", "template": "student = ____'name': 'Айдар', 'age': 20}", "answer": ["{"]},
        {"type": "test", "question": "Сөздіктегі кілт (key) қайталана ма?", "options": ["Иә", "Жоқ", "Кейде", "Қатеге байланысты"], "correct": 2},
        {"type": "code", "question": "Сөздіктен мән алыңыз:", "template": "d = {'a': 1, 'b': 2}\nvalue = d[____]", "answer": ["'b'"]},
        {"type": "theory", "question": "Сөздік (dict) пен тізімнің (list) айырмашылығын түсіндіріңіз."},
        {"type": "test", "question": "d.keys() не қайтарады?", "options": ["Мәндер", "Кілттер", "Жұптар", "Ұзындық"], "correct": 2},
        {"type": "code", "question": "Сөздікке жаңа элемент қосыңыз:", "template": "d = {'x': 1}\nd[____] = 2", "answer": ["'y'"]},
        {"type": "test", "question": "d.get('key', 0) not found болса не қайтарады?", "options": ["None", "0", "Қате", "False"], "correct": 2},
        {"type": "code", "question": "Сөздік элементтерін шығарыңыз:", "template": "d = {'a': 1, 'b': 2}\nfor key, value in d.____():\n    print(key, value)", "answer": ["items"]},
        {"type": "theory", "question": "Сөздікте .get() мен [] арқылы мән алудың айырмашылығын түсіндіріңіз."}
    ],
    "2.3.4": [
        {"type": "test", "question": "Кортеж (tuple) тізімнен нені ерекшеленеді?", "options": ["Баяуырақ", "Өзгермейді (immutable)", "Бос бола алмайды", "Тек сандар сақтайды"], "correct": 2},
        {"type": "code", "question": "Кортеж жасаңыз:", "template": "my_tuple = ____(1, 2, 3)", "answer": ["("]},
        {"type": "test", "question": "Кортежге элемент қосуға бола ма?", "options": ["Иә, append() арқылы", "Жоқ, өзгермейді", "Иә, add() арқылы", "Иә, insert() арқылы"], "correct": 2},
        {"type": "code", "question": "Кортеж элементін алыңыз:", "template": "t = (10, 20, 30)\nprint(t[____])", "answer": ["1"]},
        {"type": "theory", "question": "Кортеж қашан тізімнен артық? Мысалдар келтіріңіз."},
        {"type": "test", "question": "Кортежді unpacking деген не?", "options": ["Кортежді жою", "Элементтерді айнымалыларға бөлу", "Кортежді тізімге айналдыру", "Элементтерді қосу"], "correct": 2},
        {"type": "code", "question": "Кортежді unpacking жасаңыз:", "template": "point = (3, 7)\nx, y ____ point", "answer": ["="]},
        {"type": "test", "question": "len((1, 2, 3)) нәтижесі:", "options": ["2", "3", "4", "Қате"], "correct": 2},
        {"type": "code", "question": "Тізімді кортежге айналдырыңыз:", "template": "my_list = [1, 2, 3]\nmy_tuple = ____(my_list)", "answer": ["tuple"]},
        {"type": "theory", "question": "Кортеж, тізім және сөздіктің негізгі айырмашылықтарын кестемен салыстырыңыз."}
    ],
    "general": [
        {"type": "test", "question": "Python-да деректер типін қалай анықтайсыз?", "options": ["typeof()", "type()", "dtype()", "check()"], "correct": 2},
        {"type": "code", "question": "Айнымалы жасаңыз:", "template": "name ____ 'Python'", "answer": ["="]},
        {"type": "test", "question": "Python тілі қай жылы шықты?", "options": ["1989", "1991", "2000", "1995"], "correct": 2},
        {"type": "theory", "question": "Python-ның басқа тілдерден артықшылықтарын жазыңыз."},
        {"type": "code", "question": "Екі санды қосыңыз:", "template": "a = 5\nb = 3\nresult = a ____ b", "answer": ["+"]},
        {"type": "test", "question": "Python-да бүтін санды бөлу операторы:", "options": ["/", "//", "%", "**"], "correct": 2},
        {"type": "code", "question": "Пайдаланушыдан сан сұраңыз:", "template": "n = int(____('Сан енгізіңіз: '))", "answer": ["input"]},
        {"type": "theory", "question": "Python тілінде ірі және кіші әріптердің маңызы бар ма? Түсіндіріңіз."},
        {"type": "test", "question": "Python-да тізім элементтерін қосу функциясы:", "options": ["add()", "sum()", "total()", "count()"], "correct": 2},
        {"type": "code", "question": "for циклімен 1-ден 5-ке дейін сандарды шығарыңыз:", "template": "for i in ____(1, 6):\n    print(i)", "answer": ["range"]}
    ]
}


# -----------------------------------------
# 🧾 Проверка одного задания
# -----------------------------------------
@app.post("/check_answer/")
def check_answer(req: CheckRequest):

    db = SessionLocal()
    user = db.query(User).filter(
        User.username == req.username,
        User.email == req.email
    ).first()

    if not user:
        user = User(username=req.username, email=req.email, role="student")
        db.add(user)
        db.commit()
        db.refresh(user)

    # Проверяем, проходил ли он это задание
    existing = db.query(Result).filter(
        Result.user_id == user.id,
        Result.topic == req.topic,
        Result.task_number == req.task_number
    ).first()

    if existing and existing.completed:
        db.close()
        return {"message": "⚠ Бұл тапсырма бұрын орындалған!"}

    # Генерация фидбэка
    try:
        feedback = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content":
                 f"Студенттің коды:\n{req.answer}\nҚысқа баға беріңіз (0-10) және 1-2 сөйлем комментарий жазыңыз."}
            ],
            max_tokens=150,
            temperature=0.5
        )
        feedback_text = feedback.choices[0].message.content

    except:
        feedback_text = "GPT қолжетімсіз. Жауап қабылданды."

    # Сохранение результата
    if existing:
        existing.answer = req.answer
        existing.feedback = feedback_text
        existing.completed = True
    else:
        res = Result(
            user_id=user.id,
            topic=req.topic,
            task_number=req.task_number,
            answer=req.answer,
            feedback=feedback_text,
            completed=True
        )
        db.add(res)

    db.commit()
    db.close()

    return {
        "message": "✅ Жауап сақталды!",
        "feedback": feedback_text
    }


# -----------------------------------------
# 📊 Все результаты пользователя
# -----------------------------------------
@app.get("/results/")
def get_results(username: str, email: str):
    db = SessionLocal()
    user = db.query(User).filter(
        User.username == username,
        User.email == email
    ).first()

    if not user:
        db.close()
        return {"message": "Пайдаланушы табылмады"}

    results = [
        {
            "topic": r.topic,
            "task_number": r.task_number,
            "answer": r.answer,
            "feedback": r.feedback,
            "completed": r.completed
        }
        for r in user.results
    ]

    db.close()
    return {"results": results}


# -----------------------------------------
# 📈 Прогресс пользователя по темам
# -----------------------------------------
def extract_score_from_feedback(feedback: str):
    if not feedback:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", feedback)
    if not match:
        return None
    try:
        score = float(match.group(1))
        if 0 <= score <= 10:
            return score
    except ValueError:
        return None
    return None


@app.get("/progress/")
def get_progress(username: str, email: str):
    db = SessionLocal()
    user = db.query(User).filter(
        User.username == username,
        User.email == email
    ).first()

    if not user:
        db.close()
        return {"message": "Пайдаланушы табылмады"}

    topics_data: dict[str, dict] = {}
    total_tasks = 0
    total_scored = 0
    sum_scores = 0.0

    # Учитываем результаты кода (Result)
    for r in user.results:
        total_tasks += 1
        score = extract_score_from_feedback(r.feedback)

        if r.topic not in topics_data:
            topics_data[r.topic] = {
                "topic": r.topic,
                "tasks_total": 0,
                "tasks_scored": 0,
                "sum_scores": 0.0,
            }

        topic_info = topics_data[r.topic]
        topic_info["tasks_total"] += 1

        if score is not None:
            topic_info["tasks_scored"] += 1
            topic_info["sum_scores"] += score
            total_scored += 1
            sum_scores += score

    # Учитываем результаты тематических квизов (TopicQuizResult)
    for q in user.quiz_results:
        if q.total and q.total > 0:
            percent = (q.correct / q.total) * 100.0
            # Переводим процент в шкалу 0-10
            score = max(0.0, min(10.0, percent / 10.0))
        else:
            continue

        total_tasks += q.total

        if q.topic not in topics_data:
            topics_data[q.topic] = {
                "topic": q.topic,
                "tasks_total": 0,
                "tasks_scored": 0,
                "sum_scores": 0.0,
            }

        topic_info = topics_data[q.topic]
        topic_info["tasks_total"] += q.total
        topic_info["tasks_scored"] += q.total
        topic_info["sum_scores"] += score * q.total
        total_scored += q.total
        sum_scores += score * q.total

    topics_stats = []
    weak_topics = []
    WEAK_THRESHOLD_PERCENT = 60.0

    for t in topics_data.values():
        avg_score = (t["sum_scores"] / t["tasks_scored"]) if t["tasks_scored"] > 0 else None
        avg_percent = (avg_score * 10) if avg_score is not None else None

        topic_stat = {
            "topic": t["topic"],
            "tasks_total": t["tasks_total"],
            "tasks_scored": t["tasks_scored"],
            "avg_score": avg_score,
            "avg_percent": avg_percent,
        }
        topics_stats.append(topic_stat)

        if avg_percent is not None and avg_percent < WEAK_THRESHOLD_PERCENT:
            weak_topics.append(t["topic"])

    overall_avg_score = (sum_scores / total_scored) if total_scored > 0 else None
    overall_avg_percent = (overall_avg_score * 10) if overall_avg_score is not None else None

    db.close()

    return {
        "username": username,
        "email": email,
        "overall": {
            "tasks_total": total_tasks,
            "tasks_scored": total_scored,
            "avg_score": overall_avg_score,
            "avg_percent": overall_avg_percent,
        },
        "topics": topics_stats,
        "weak_topics": weak_topics,
    }


# -----------------------------------------
# 📝 Мини-тест по теме (7 вопросов)
# -----------------------------------------
QUIZ_MAPPING = {
    "1.1.1": "Python тіліне кіріспе",
    "1.1.2": "Python тіліне кіріспе",
    "1.2.1": "Цикл",
    "1.2.2": "Цикл",
    "1.2.3": "Цикл",
    "1.3.1": "Бірөлшемді тізімдер",
    "1.3.2": "Бірөлшемді тізімдер",
    "2.1.1": "Массив",
    "2.1.2": "Массив",
    "2.2.1": "Екі өлшемді массивтер",
    "2.2.2": "Екі өлшемді массивтер",
    "2.3.1": "Ішкі бағдарламалар",
    "2.3.2": "Ішкі бағдарламалар",
    "2.3.3": "Ішкі бағдарламалар",
    "2.3.4": "Ішкі бағдарламалар",
}

@app.get("/quiz/")
def get_quiz(topic: str):
    internal_topic = QUIZ_MAPPING.get(topic, topic)
    questions = QUIZZES.get(internal_topic)
    if not questions:
        return {"message": "Бұл тақырып бойынша тест табылмады"}
    return {"topic": topic, "questions": questions}


# -----------------------------------------
# ROOT
# -----------------------------------------
@app.get("/api")
def root():
    return {"message": "API жұмыс істеп тұр!"}
