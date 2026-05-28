from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, Boolean, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
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
    username: str | None = None
    email: str | None = None

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
# 🎯 READY PRACTICE TASKS / QUIZ DATA
# 1–5: test, 6–8: theory, 9–10: code_fill
# -----------------------------------------

QUIZZES = {
    "1.1.1": [
        {
            "type": "test",
            "question": "Python қандай бағдарламалау тілі?",
            "options": ["Төмен деңгейлі", "Орта деңгейлі", "Жоғары деңгейлі", "Машина тілі"],
            "correct": 3,
            "explanation": "Python — синтаксисі қарапайым, адамға түсінікті жоғары деңгейлі бағдарламалау тілі."
        },
        {
            "type": "test",
            "question": "Python тілінің авторы кім?",
            "options": ["Деннис Ритчи", "Гвидо ван Россум", "Джеймс Гослинг", "Бьёрн Страуструп"],
            "correct": 2,
            "explanation": "Python тілін Гвидо ван Россум жасаған."
        },
        {
            "type": "test",
            "question": "Python-ның алғашқы ресми нұсқасы қашан шықты?",
            "options": ["1989", "1991", "1995", "2000"],
            "correct": 2,
            "explanation": "Python-ның алғашқы ресми нұсқасы 1991 жылы жарық көрді."
        },
        {
            "type": "test",
            "question": "Python-да экранға мәтін шығару үшін қандай функция қолданылады?",
            "options": ["echo()", "console.log()", "print()", "printf()"],
            "correct": 3,
            "explanation": "Python тілінде экранға ақпарат шығару үшін print() функциясы қолданылады."
        },
        {
            "type": "test",
            "question": "Python-да пайдаланушыдан мәлімет енгізу үшін қандай функция қолданылады?",
            "options": ["print()", "input()", "scan()", "read()"],
            "correct": 2,
            "explanation": "input() функциясы қолданушыдан мәтін түрінде дерек қабылдайды."
        },
        {"type": "theory", "question": "Python тілінің жоғары деңгейлі тіл деп аталуының себебін түсіндіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "Python тілін қандай салаларда қолдануға болады? Кемінде үш мысал келтіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "Интерпретатор дегеніміз не және Python бағдарламасын орындауда оның рөлі қандай?", "teacher_check": True},
        {
            "type": "code_fill",
            "question": "Берілген нәтиже шығу үшін кодтағы бос орынды толтырыңыз.",
            "template": "name = input('Атыңызды енгізіңіз: ')\nprint('Сәлем, ' + ______ + '!')",
            "expected_output": "Егер қолданушы Айдана деп енгізсе:\nСәлем, Айдана!",
            "correct": ["name"],
            "explanation": "input() арқылы алынған мән name айнымалысында сақталады, сондықтан print ішінде name қолдану керек."
        },
        {
            "type": "code_fill",
            "question": "Кодтағы қатені түзетіңіз: экранға Hello, World! шығуы керек.",
            "template": "message = 'Hello, World!'\nprnt(message)",
            "expected_output": "Hello, World!",
            "correct": ["print"],
            "explanation": "Python-да экранға шығару функциясы print(), ал prnt деген функция жоқ."
        },
    ],

    "1.1.2": [
        {
            "type": "test",
            "question": "Алгоритм дегеніміз не?",
            "options": ["Математикалық есептеу әдісі", "Белгілі бір есепті шешуге арналған әрекеттердің жүйелі тізбегі", "Компьютердің құрылғысы", "Мәліметтерді сақтау тәсілі"],
            "correct": 2,
            "explanation": "Алгоритм — есепті шешу үшін орындалатын нақты қадамдар тізбегі."
        },
        {
            "type": "test",
            "question": "Сызықты алгоритмнің негізгі ерекшелігі қандай?",
            "options": ["Тек шарттардан тұрады", "Қадамдар қатаң реттілікпен орындалады", "Бірнеше тармақтары бар", "Қадамдар кездейсоқ орындалады"],
            "correct": 2,
            "explanation": "Сызықты алгоритмде командалар бірінен кейін бірі орындалады."
        },
        {
            "type": "test",
            "question": "Шартты алгоритм қандай процесті қамтиды?",
            "options": ["Тек есептеуді", "Шешім қабылдауды", "Тек дерек енгізуді", "Тек дерек сақтауды"],
            "correct": 2,
            "explanation": "Шартты алгоритмде логикалық шартқа байланысты әртүрлі әрекет орындалады."
        },
        {
            "type": "test",
            "question": "Сызықты алгоритмдерде қандай құрылым болмайды?",
            "options": ["Логикалық шарттар", "Мәліметтер енгізу", "Есептеулер", "Нәтиже шығару"],
            "correct": 1,
            "explanation": "Сызықты алгоритмде шарт бойынша тармақталу болмайды."
        },
        {
            "type": "test",
            "question": "Шартты алгоритмнің басты ерекшелігі қандай?",
            "options": ["Қадамдардың тек бірізді орындалуы", "Логикалық шарттардың болуы", "Циклдардың болуы", "Мәліметтерді автоматты сұрыптау"],
            "correct": 2,
            "explanation": "Шартты алгоритмде if/else сияқты логикалық шарттар қолданылады."
        },
        {"type": "theory", "question": "Сызықты алгоритм мен шартты алгоритмнің айырмашылығын мысалмен түсіндіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "Шартты алгоритм күнделікті өмірде қандай жағдайларда қолданылады?", "teacher_check": True},
        {"type": "theory", "question": "if, elif, else операторларының қызметін қысқаша түсіндіріңіз.", "teacher_check": True},
        {
            "type": "code_fill",
            "question": "Кодтағы бос орынды толтырыңыз: сан оң болса, экранға 'Оң сан' шығуы керек.",
            "template": "x = int(input('Сан енгізіңіз: '))\n______ x > 0:\n    print('Оң сан')\nelse:\n    print('Оң емес сан')",
            "expected_output": "Егер x = 7 болса:\nОң сан",
            "correct": ["if"],
            "explanation": "Шартты тексеру үшін Python тілінде if операторы қолданылады."
        },
        {
            "type": "code_fill",
            "question": "Кодтағы қатені түзетіңіз: x нөлге тең болса 'Нөл' шығуы керек.",
            "template": "x = 0\nif x > 0:\n    print('Оң')\nelif x = 0:\n    print('Нөл')\nelse:\n    print('Теріс')",
            "expected_output": "Нөл",
            "correct": ["=="],
            "explanation": "Шартта салыстыру үшін == қолданылады, ал = меншіктеу операторы."
        },
    ],

    "1.2.1": [
        {
            "type": "test",
            "question": "Python тілінде негізгі цикл түрлері қандай?",
            "options": ["for және foreach", "while және do-while", "for және while", "repeat және until"],
            "correct": 3,
            "explanation": "Python тілінде негізгі циклдер — for және while."
        },
        {
            "type": "test",
            "question": "for циклі қандай жағдайда қолданылады?",
            "options": ["Қайталану саны белгілі болғанда", "Тек шарт тексеру үшін", "Тек файл оқу үшін", "Тек бір рет орындау үшін"],
            "correct": 1,
            "explanation": "for циклі көбіне қайталану саны белгілі болғанда немесе тізім элементтерін өңдегенде қолданылады."
        },
        {
            "type": "test",
            "question": "break операторы не істейді?",
            "options": ["Циклді толық тоқтатады", "Келесі итерацияға өтеді", "Айнымалыны өшіреді", "Циклді қайта бастайды"],
            "correct": 1,
            "explanation": "break цикл жұмысын мерзімінен бұрын тоқтатады."
        },
        {
            "type": "test",
            "question": "continue операторы не істейді?",
            "options": ["Циклді толық тоқтатады", "Ағымдағы итерацияны өткізіп, келесі итерацияға өтеді", "Бағдарламаны жабады", "Айнымалыны нөлге теңейді"],
            "correct": 2,
            "explanation": "continue ағымдағы қадамды өткізіп, циклдің келесі қадамына өтеді."
        },
        {
            "type": "test",
            "question": "range(3) қандай мәндерді береді?",
            "options": ["1, 2, 3", "0, 1, 2", "0, 1, 2, 3", "3, 2, 1"],
            "correct": 2,
            "explanation": "range(3) 0-ден басталып, 3-ке жетпей тоқтайды: 0, 1, 2."
        },
        {"type": "theory", "question": "for циклі мен while циклінің айырмашылығын түсіндіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "break және continue операторларының айырмашылығын мысалмен түсіндіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "range(start, stop, step) параметрлерінің қызметін түсіндіріңіз.", "teacher_check": True},
        {
            "type": "code_fill",
            "question": "0-ден 4-ке дейінгі сандарды шығару үшін бос орынды толтырыңыз.",
            "template": "for i in ______(5):\n    print(i)",
            "expected_output": "0\n1\n2\n3\n4",
            "correct": ["range"],
            "explanation": "range(5) 0-ден 4-ке дейінгі мәндерді береді."
        },
        {
            "type": "code_fill",
            "question": "Кодтағы қатені түзетіңіз: цикл 1-ден 5-ке дейін шығуы керек.",
            "template": "for i in range(1, 5):\n    print(i)",
            "expected_output": "1\n2\n3\n4\n5",
            "correct": ["range(1, 6)"],
            "explanation": "range соңғы мәнді қоспайды, сондықтан 5 шығуы үшін stop мәні 6 болуы керек."
        },
    ],

    "1.2.2": [
        {
            "type": "test",
            "question": "while циклі қалай жұмыс істейді?",
            "options": ["Шарт жалған болғанша орындалады", "Шарт ақиқат болғанша орындалады", "Тек бір рет орындалады", "Тек тізіммен жұмыс істейді"],
            "correct": 2,
            "explanation": "while циклі шарт True болғанша қайталанады."
        },
        {
            "type": "test",
            "question": "while циклінің дұрыс жазылу форматы қандай?",
            "options": ["while шарт:", "while (шарт) {}", "while: шарт", "while шарт then"],
            "correct": 1,
            "explanation": "Python тілінде while шарт: түрінде жазылады."
        },
        {
            "type": "test",
            "question": "Егер while шарты ешқашан False болмаса, не болады?",
            "options": ["Цикл орындалмайды", "Шексіз цикл пайда болады", "Бағдарлама автоматты тоқтайды", "Айнымалы өшеді"],
            "correct": 2,
            "explanation": "Шарт әрдайым True болса, while циклі шексіз қайталанады."
        },
        {
            "type": "test",
            "question": "while циклінде break операторының қызметі қандай?",
            "options": ["Циклді толық тоқтатады", "Келесі итерацияға өткізеді", "Айнымалыны арттырады", "Шартты өткізіп жібереді"],
            "correct": 1,
            "explanation": "break циклден бірден шығарады."
        },
        {
            "type": "test",
            "question": "while циклінде else блогы қашан орындалады?",
            "options": ["Цикл break арқылы тоқтағанда", "Цикл шарты False болып қалыпты аяқталғанда", "Әр итерацияда", "Ешқашан"],
            "correct": 2,
            "explanation": "while-else блогы цикл break қолданылмай қалыпты аяқталғанда орындалады."
        },
        {"type": "theory", "question": "while циклінің for циклінен айырмашылығын түсіндіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "Шексіз циклден сақтану үшін қандай ережелерді сақтау керек?", "teacher_check": True},
        {"type": "theory", "question": "while циклінде break және continue операторларын қолдану жағдайларын сипаттаңыз.", "teacher_check": True},
        {
            "type": "code_fill",
            "question": "0-ден 3-ке дейін шығару үшін бос орынды толтырыңыз.",
            "template": "i = 0\nwhile i ______ 4:\n    print(i)\n    i += 1",
            "expected_output": "0\n1\n2\n3",
            "correct": ["<"],
            "explanation": "i < 4 шарты i мәні 0,1,2,3 болғанда ғана орындалады."
        },
        {
            "type": "code_fill",
            "question": "Кодтағы қатені түзетіңіз: SyntaxError болмауы керек.",
            "template": "while True\n    print('Hello')",
            "expected_output": "Hello сөзі шексіз қайталанады",
            "correct": [":"],
            "explanation": "Python тілінде while шартынан кейін міндетті түрде қос нүкте қойылады."
        },
    ],

    "1.2.3": [
        {
            "type": "test",
            "question": "Python тіліндегі циклдердің негізгі түрлері қандай?",
            "options": ["if және else", "while және for", "def және return", "list және tuple"],
            "correct": 2,
            "explanation": "Python-да негізгі циклдер while және for."
        },
        {
            "type": "test",
            "question": "Функцияны анықтау үшін қандай кілттік сөз қолданылады?",
            "options": ["function", "def", "func", "define"],
            "correct": 2,
            "explanation": "Python тілінде функция def кілттік сөзі арқылы анықталады."
        },
        {
            "type": "test",
            "question": "Функция нәтижесін қайтару үшін қандай оператор қолданылады?",
            "options": ["print", "return", "output", "result"],
            "correct": 2,
            "explanation": "return функциядан мән қайтару үшін қолданылады."
        },
        {
            "type": "test",
            "question": "Қай жағдайда функция құру пайдалы?",
            "options": ["Код бірнеше рет қолданылуы керек болса", "Код тек бір рет орындалса", "Код тек print-тен тұрса", "Айнымалы болмаса"],
            "correct": 1,
            "explanation": "Функция қайталанатын кодты бөлек блокқа жинауға көмектеседі."
        },
        {
            "type": "test",
            "question": "Функция ішінде ғана қолданылатын айнымалы қалай аталады?",
            "options": ["Глобалды", "Локалды", "Арнайы", "Тұрақты"],
            "correct": 2,
            "explanation": "Функция ішінде құрылған айнымалы локалды айнымалы деп аталады."
        },
        {"type": "theory", "question": "Функция дегеніміз не және ол бағдарламаны қалай жеңілдетеді?", "teacher_check": True},
        {"type": "theory", "question": "Параметр мен аргументтің айырмашылығын түсіндіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "return және print операторларының айырмашылығы қандай?", "teacher_check": True},
        {
            "type": "code_fill",
            "question": "Функция екі санның қосындысын қайтаруы үшін бос орынды толтырыңыз.",
            "template": "def add_numbers(a, b):\n    ______ a + b\n\nresult = add_numbers(4, 6)\nprint(result)",
            "expected_output": "10",
            "correct": ["return"],
            "explanation": "Функция нәтижесін сыртқа қайтару үшін return қолданылады."
        },
        {
            "type": "code_fill",
            "question": "Кодтағы қатені түзетіңіз: функция дұрыс анықталуы керек.",
            "template": "function greet(name):\n    print('Сәлем,', name)\n\ngreet('Айжан')",
            "expected_output": "Сәлем, Айжан",
            "correct": ["def"],
            "explanation": "Python-да function емес, def кілттік сөзі қолданылады."
        },
    ],

    "1.3.1": [
        {
            "type": "test",
            "question": "Python тілінде тізімнің өзгермелі (mutable) екенін қандай әрекет көрсетеді?",
            "options": ["Тізім элементтерін өзгертуге болмайды", "Тізімге жаңа элемент қосуға болады", "Тізім тек оқылады", "Тізім тек көшіріледі"],
            "correct": 2,
            "explanation": "List — өзгермелі құрылым, оған элемент қосуға, өзгертуге және жоюға болады."
        },
        {
            "type": "test",
            "question": "repeated = [1] * 4 кодының нәтижесі қандай?",
            "options": ["[1, 1, 1, 1]", "[4]", "[1, 4]", "[[1] * 4]"],
            "correct": 1,
            "explanation": "[1] * 4 тізімді төрт рет қайталайды."
        },
        {
            "type": "test",
            "question": "list1 = [1,2,3] және list2 = list1 болса, list1 өзгерсе list2-ге әсер ете ме?",
            "options": ["Иә, себебі list2 list1-ге сілтеме жасайды", "Жоқ, себебі list2 жаңа тізім", "Тек list2 өзгереді", "Қате пайда болады"],
            "correct": 1,
            "explanation": "list2 = list1 кезінде екі айнымалы бір объектіге сілтеме жасайды."
        },
        {
            "type": "test",
            "question": "list1.copy() әдісінің мақсаты қандай?",
            "options": ["Жаңа сілтеме жасау", "Тізімнің тәуелсіз көшірмесін жасау", "Соңғы элементті жою", "Барлық элементті өшіру"],
            "correct": 2,
            "explanation": "copy() тізімнің бөлек көшірмесін жасайды."
        },
        {
            "type": "test",
            "question": "pop() әдісі не істейді?",
            "options": ["Соңғы элементті жояды және қайтарады", "Барлық элементті жояды", "Тізімді кері аударады", "Тізімді сұрыптайды"],
            "correct": 1,
            "explanation": "pop() әдетте соңғы элементті алып тастап, оны қайтарады."
        },
        {"type": "theory", "question": "Тізімнің mutable қасиетін мысалмен түсіндіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "append(), extend(), insert() әдістерінің айырмашылығын түсіндіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "Тізімді көшіру кезінде copy() қолдану не үшін маңызды?", "teacher_check": True},
        {
            "type": "code_fill",
            "question": "Тізімнің соңына жаңа элемент қосу үшін бос орынды толтырыңыз.",
            "template": "fruits = ['алма', 'банан']\nfruits.______('апельсин')\nprint(fruits)",
            "expected_output": "['алма', 'банан', 'апельсин']",
            "correct": ["append"],
            "explanation": "append() тізімнің соңына бір элемент қосады."
        },
        {
            "type": "code_fill",
            "question": "Кодтағы бос орынды толтырыңыз: 30 элементі жойылуы керек.",
            "template": "numbers = [10, 20, 30, 40]\ndel numbers[______]\nprint(numbers)",
            "expected_output": "[10, 20, 40]",
            "correct": ["2"],
            "explanation": "Тізім индекстері 0-ден басталады, 30 санының индексі — 2."
        },
    ],

    "1.3.2": [
        {
            "type": "test",
            "question": "Python тілінде бірөлшемді тізімді қалай анықтауға болады?",
            "options": ["{1, 2, 3}", "(1, 2, 3)", "[1, 2, 3]", "<1, 2, 3>"],
            "correct": 3,
            "explanation": "Python-да тізім квадрат жақша арқылы жазылады."
        },
        {
            "type": "test",
            "question": "Python тілінде тізім индексі қай саннан басталады?",
            "options": ["1", "0", "-1", "2"],
            "correct": 2,
            "explanation": "Python-да бірінші элементтің индексі 0."
        },
        {
            "type": "test",
            "question": "Бірөлшемді тізімнің негізгі ерекшелігі қандай?",
            "options": ["Тек бір тип сақтайды", "Өзгертуге болмайды", "Әртүрлі типті элементтерді сақтай алады және өзгермелі", "Тек бүтін сандарды сақтайды"],
            "correct": 3,
            "explanation": "List әртүрлі типті элементтерден тұра алады және mutable."
        },
        {
            "type": "test",
            "question": "Тізімге жаңа элемент қосатын әдіс қайсы?",
            "options": ["append()", "remove()", "sort()", "index()"],
            "correct": 1,
            "explanation": "append() тізім соңына жаңа элемент қосады."
        },
        {
            "type": "test",
            "question": "Тізімдегі соңғы элементке қалай қол жеткізуге болады?",
            "options": ["list[0]", "list[-1]", "list[last]", "list[len(list)]"],
            "correct": 2,
            "explanation": "Python-да -1 индексі соңғы элементті көрсетеді."
        },
        {"type": "theory", "question": "Бірөлшемді тізім дегеніміз не? Мысал келтіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "Индекс арқылы элементке қол жеткізу қалай орындалады?", "teacher_check": True},
        {"type": "theory", "question": "sort(), reverse(), len() функцияларының қызметін түсіндіріңіз.", "teacher_check": True},
        {
            "type": "code_fill",
            "question": "Тізімдегі үшінші элементті шығару үшін бос орынды толтырыңыз.",
            "template": "nums = [10, 20, 30, 40]\nprint(nums[______])",
            "expected_output": "30",
            "correct": ["2"],
            "explanation": "Үшінші элементтің индексі 2, себебі индекстеу 0-ден басталады."
        },
        {
            "type": "code_fill",
            "question": "Кодтағы қатені түзетіңіз: соңғы элемент шығуы керек.",
            "template": "items = ['a', 'b', 'c']\nprint(items[len(items)])",
            "expected_output": "c",
            "correct": ["items[-1]"],
            "explanation": "items[len(items)] индексі жоқ, соңғы элемент үшін items[-1] қолданамыз."
        },
    ],

    "2.1.1": [
        {
            "type": "test",
            "question": "Массив дегеніміз не?",
            "options": ["Айнымалылар жиынтығы", "Бір типтегі деректерді сақтау құрылымы", "Файл сақтау құрылғысы", "Бағдарламалау тілі"],
            "correct": 2,
            "explanation": "Массив бір типтегі деректерді ретімен сақтау үшін қолданылады."
        },
        {
            "type": "test",
            "question": "Бірөлшемді массив қалай аталады?",
            "options": ["Матрица", "Вектор", "Кесте", "Баған"],
            "correct": 2,
            "explanation": "Бірөлшемді массив көбіне вектор деп аталады."
        },
        {
            "type": "test",
            "question": "Екіөлшемді массив элементіне қалай қол жеткізуге болады?",
            "options": ["massiv[1]", "matrix[1,2]", "matrix[1][2]", "matrix{1,2}"],
            "correct": 3,
            "explanation": "Python-да екіөлшемді тізім элементі matrix[row][col] арқылы алынады."
        },
        {
            "type": "test",
            "question": "len(massiv) қандай мәнді қайтарады?",
            "options": ["Элементтер санын", "Ең үлкен элементті", "Ең кіші элементті", "Қосындысын"],
            "correct": 1,
            "explanation": "len() құрылымдағы элементтер санын қайтарады."
        },
        {
            "type": "test",
            "question": "massiv = [3,6,9,12,15]; print(massiv[2]) нәтижесі қандай?",
            "options": ["3", "6", "9", "12"],
            "correct": 3,
            "explanation": "Индекс 2 үшінші элементті көрсетеді, ол 9."
        },
        {"type": "theory", "question": "Массив пен тізімнің ұқсастығы мен айырмашылығын түсіндіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "Массивтер қандай есептерде тиімді қолданылады?", "teacher_check": True},
        {"type": "theory", "question": "Индекс арқылы массив элементін алу принципін түсіндіріңіз.", "teacher_check": True},
        {
            "type": "code_fill",
            "question": "Массивтің үшінші элементін шығару үшін бос орынды толтырыңыз.",
            "template": "massiv = [3, 6, 9, 12, 15]\nprint(massiv[______])",
            "expected_output": "9",
            "correct": ["2"],
            "explanation": "Үшінші элементтің индексі 2."
        },
        {
            "type": "code_fill",
            "question": "Бес нөлден тұратын массив жасау үшін бос орынды толтырыңыз.",
            "template": "massiv = [0] * ______\nprint(massiv)",
            "expected_output": "[0, 0, 0, 0, 0]",
            "correct": ["5"],
            "explanation": "[0] * 5 бір нөлді бес рет қайталайды."
        },
    ],

    "2.1.2": [
        {
            "type": "test",
            "question": "Көпіршікті сұрыптау қалай жұмыс істейді?",
            "options": ["Массивті екіге бөледі", "Көрші элементтерді салыстырып, орындарын ауыстырады", "Ең үлкенін өшіреді", "Элементтерді кездейсоқ орналастырады"],
            "correct": 2,
            "explanation": "Bubble sort көрші элементтерді салыстырып, қажет болса ауыстырады."
        },
        {
            "type": "test",
            "question": "Үлкен көлемді деректерге тиімді сұрыптау әдістері қайсы?",
            "options": ["Көпіршікті сұрыптау", "Таңдау арқылы сұрыптау", "Біріктіру немесе жылдам сұрыптау", "Қарапайым ауыстыру"],
            "correct": 3,
            "explanation": "Merge sort және Quick sort үлкен деректерде тиімдірек."
        },
        {
            "type": "test",
            "question": "Таңдау арқылы сұрыптау қалай жұмыс істейді?",
            "options": ["Көрші элементтерді ауыстырады", "Ең кіші элементті таңдап, орнына қояды", "Массивті екіге бөледі", "Барлығын бірден сұрыптайды"],
            "correct": 2,
            "explanation": "Selection sort сұрыпталмаған бөліктен ең кіші элементті таңдайды."
        },
        {
            "type": "test",
            "question": "Python-дағы sorted() функциясы қандай алгоритмге негізделеді?",
            "options": ["Bubble sort", "Selection sort", "Timsort", "QuickSort ғана"],
            "correct": 3,
            "explanation": "Python sorted() функциясы Timsort алгоритмін қолданады."
        },
        {
            "type": "test",
            "question": "Көпіршікті сұрыптаудың уақыттық күрделілігі қандай?",
            "options": ["O(n)", "O(n log n)", "O(n²)", "O(1)"],
            "correct": 3,
            "explanation": "Bubble sort орта және нашар жағдайда O(n²) күрделілікке ие."
        },
        {"type": "theory", "question": "Көпіршікті сұрыптау алгоритмін қадамдармен түсіндіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "Selection sort пен Bubble sort айырмашылығын түсіндіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "O(n²) күрделілігі нені білдіреді?", "teacher_check": True},
        {
            "type": "code_fill",
            "question": "Тізімді өсу ретімен сұрыптау үшін бос орынды толтырыңыз.",
            "template": "massiv = [21, 34, 12, 45, 33]\nsorted_massiv = ______(massiv)\nprint(sorted_massiv)",
            "expected_output": "[12, 21, 33, 34, 45]",
            "correct": ["sorted"],
            "explanation": "sorted() жаңа сұрыпталған тізімді қайтарады."
        },
        {
            "type": "code_fill",
            "question": "Көпіршікті сұрыптауда орын ауыстыру шарты үшін бос орынды толтырыңыз.",
            "template": "arr = [5, 2, 8]\nfor i in range(len(arr)):\n    for j in range(len(arr)-1-i):\n        if arr[j] ______ arr[j+1]:\n            arr[j], arr[j+1] = arr[j+1], arr[j]\nprint(arr)",
            "expected_output": "[2, 5, 8]",
            "correct": [">"],
            "explanation": "Өсу ретімен сұрыптау үшін сол жақтағы элемент үлкен болса, орындарын ауыстыру керек."
        },
    ],

    "2.2.1": [
        {
            "type": "test",
            "question": "Екі өлшемді массив қандай құрылыммен ұсынылады?",
            "options": ["Тізімдер тізімі", "Бір тізім", "Кортеж", "Жол"],
            "correct": 1,
            "explanation": "Python-да екі өлшемді массив көбіне тізімдер тізімі ретінде жазылады."
        },
        {
            "type": "test",
            "question": "Екі өлшемді массивті дұрыс анықтау қайсы?",
            "options": ["matrix = (1,2,3)", "matrix = [[1,2,3],[4,5,6]]", "matrix = [1,2,3]", "matrix = {1,2,3}"],
            "correct": 2,
            "explanation": "Екі өлшемді массив жолдардан тұратын ішкі тізімдер арқылы беріледі."
        },
        {
            "type": "test",
            "question": "matrix[1][0] нені білдіреді?",
            "options": ["Бірінші жол, нөлінші баған", "Екінші жол, бірінші баған", "Екінші баған", "Қате"],
            "correct": 2,
            "explanation": "Индекс 1 — екінші жол, индекс 0 — бірінші баған."
        },
        {
            "type": "test",
            "question": "matrix = [[1,2],[3,4]]; print(matrix[1][0]) нәтижесі қандай?",
            "options": ["1", "2", "3", "4"],
            "correct": 3,
            "explanation": "matrix[1] — [3,4], ал оның 0-индексіндегі элемент — 3."
        },
        {
            "type": "test",
            "question": "Екі өлшемді массивтің барлық элементтерін қарау үшін не қолдануға болады?",
            "options": ["Екі цикл", "Тек бір print", "Тек if", "Тек input"],
            "correct": 1,
            "explanation": "Жолдар мен бағандарды өту үшін кірістірілген екі цикл қолданылады."
        },
        {"type": "theory", "question": "Екі өлшемді массив дегеніміз не? Мысал келтіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "matrix[row][col] индекстеу жүйесін түсіндіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "Екі өлшемді массивтер қандай нақты есептерде қолданылады?", "teacher_check": True},
        {
            "type": "code_fill",
            "question": "Барлық элементтерді шығару үшін бос орынды толтырыңыз.",
            "template": "matrix = [[1, 2], [3, 4]]\nfor row in matrix:\n    for value in ______:\n        print(value)",
            "expected_output": "1\n2\n3\n4",
            "correct": ["row"],
            "explanation": "Ішкі цикл әрбір row ішіндегі элементтерді қарап шығады."
        },
        {
            "type": "code_fill",
            "question": "2-жолдың 1-элементін шығару үшін бос орынды толтырыңыз.",
            "template": "matrix = [[1, 2], [3, 4]]\nprint(matrix[______][______])",
            "expected_output": "3",
            "correct": ["1", "0"],
            "explanation": "3 саны екінші жолда, бірінші бағанда орналасқан: matrix[1][0]."
        },
    ],

    "2.2.2": [
        {
            "type": "test",
            "question": "NumPy кітапханасы қандай мақсатта қолданылады?",
            "options": ["Сандық есептеулер үшін", "Веб дамыту үшін", "Ойын жасау үшін", "Мәтін теру үшін"],
            "correct": 1,
            "explanation": "NumPy массивтер және ғылыми есептеулер үшін қолданылады."
        },
        {
            "type": "test",
            "question": "Екі өлшемді массивтің негізгі құрылымы қандай?",
            "options": ["Жолдар мен бағандар", "Тек жолдар", "Тек бағандар", "Тек сөздіктер"],
            "correct": 1,
            "explanation": "Екі өлшемді массив жолдар мен бағандардан тұрады."
        },
        {
            "type": "test",
            "question": "NumPy массивтерінің артықшылығы қандай?",
            "options": ["Жоғары жылдамдық", "Жадты тиімді қолдану", "Күрделі есептеулерге қолайлы", "Барлығы дұрыс"],
            "correct": 4,
            "explanation": "NumPy жылдам, жадты тиімді қолданады және ғылыми есептерге ыңғайлы."
        },
        {
            "type": "test",
            "question": "Екі өлшемді массивтермен арифметикалық амал жасағанда не болады?",
            "options": ["Амал барлық элементтерге қолданылуы мүмкін", "Тек бірінші элемент өзгереді", "Қате болады", "Тек баған өшеді"],
            "correct": 1,
            "explanation": "NumPy-де векторланған амалдар барлық элементтерге бірден қолданылуы мүмкін."
        },
        {
            "type": "test",
            "question": "NumPy-де матрица формасын өзгерту үшін қандай әдіс қолданылады?",
            "options": ["reshape()", "resize_text()", "change()", "format()"],
            "correct": 1,
            "explanation": "reshape() массив өлшемін өзгертеді."
        },
        {"type": "theory", "question": "NumPy массиві мен Python тізімінің айырмашылығын түсіндіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "Вектор және матрица ұғымдарын NumPy арқылы сипаттаңыз.", "teacher_check": True},
        {"type": "theory", "question": "NumPy не үшін деректерді өңдеуде жиі қолданылады?", "teacher_check": True},
        {
            "type": "code_fill",
            "question": "NumPy массивін жасау үшін бос орынды толтырыңыз.",
            "template": "import numpy as np\narr = np.______([1, 2, 3, 4])\nprint(arr)",
            "expected_output": "[1 2 3 4]",
            "correct": ["array"],
            "explanation": "np.array() Python тізімінен NumPy массивін жасайды."
        },
        {
            "type": "code_fill",
            "question": "1-ден 9-ға дейінгі массивті 3x3 матрицаға айналдыру үшін бос орынды толтырыңыз.",
            "template": "import numpy as np\narr = np.arange(1, 10)\nmatrix = arr.______((3, 3))\nprint(matrix)",
            "expected_output": "[[1 2 3]\n [4 5 6]\n [7 8 9]]",
            "correct": ["reshape"],
            "explanation": "reshape((3,3)) бірөлшемді массивті 3 жол, 3 бағанды матрицаға өзгертеді."
        },
    ],

    "2.3.1": [
        {
            "type": "test",
            "question": "Рекурсия дегеніміз не?",
            "options": ["Функцияның өзін-өзі шақыруы", "Бағдарламаны қайта жүктеу", "Кодты жылдамдату", "Айнымалыны сақтау"],
            "correct": 1,
            "explanation": "Рекурсия — функцияның өз ішінде өзін қайта шақыру процесі."
        },
        {
            "type": "test",
            "question": "Рекурсивті функцияның міндетті компоненттері қандай?",
            "options": ["Цикл және шарт", "Базалық жағдай және рекурсивті қадам", "Тек айнымалылар", "Тек параметрлер"],
            "correct": 2,
            "explanation": "Базалық жағдай рекурсияны тоқтатады, рекурсивті қадам есепті кішірейтеді."
        },
        {
            "type": "test",
            "question": "Базалық жағдай дегеніміз не?",
            "options": ["Өзін шақыру бөлігі", "Рекурсияны тоқтататын шарт", "Стекті арттыру", "Аргументті өзгерту"],
            "correct": 2,
            "explanation": "Base case — рекурсивті шақыруды тоқтататын шарт."
        },
        {
            "type": "test",
            "question": "Егер рекурсияда базалық жағдай болмаса, не болады?",
            "options": ["Функция бір рет орындалады", "Шексіз шақырылып, қате болуы мүмкін", "Бағдарлама өзі түзетеді", "Нәтиже бірден шығады"],
            "correct": 2,
            "explanation": "Базалық жағдай болмаса RecursionError пайда болуы мүмкін."
        },
        {
            "type": "test",
            "question": "factorial(n) рекурсивті функциясы әдетте нені есептейді?",
            "options": ["Фибоначчи", "Санның факториалын", "Тізімді сұрыптайды", "Жол ұзындығын"],
            "correct": 2,
            "explanation": "factorial(n) = n * factorial(n-1) түрінде факториал есептейді."
        },
        {"type": "theory", "question": "Рекурсия мен циклдің айырмашылығын түсіндіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "Базалық жағдай не үшін міндетті?", "teacher_check": True},
        {"type": "theory", "question": "Рекурсия қандай алгоритмдерде жиі қолданылады?", "teacher_check": True},
        {
            "type": "code_fill",
            "question": "Факториал функциясында бос орынды толтырыңыз.",
            "template": "def factorial(n):\n    if n <= 1:\n        return 1\n    return n * ______(n - 1)\n\nprint(factorial(5))",
            "expected_output": "120",
            "correct": ["factorial"],
            "explanation": "Функция өзін қайта шақырады: factorial(n - 1)."
        },
        {
            "type": "code_fill",
            "question": "Фибоначчи функциясында жетіспейтін бөлікті толтырыңыз.",
            "template": "def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n - 1) + fibonacci(______)\n\nprint(fibonacci(5))",
            "expected_output": "5",
            "correct": ["n - 2"],
            "explanation": "Фибоначчи формуласы: F(n)=F(n-1)+F(n-2)."
        },
    ],

    "2.3.2": [
        {
            "type": "test",
            "question": "Python-да жол (string) дегеніміз не?",
            "options": ["Сандар жиыны", "Таңбалардың реттелген тізбегі", "Айнымалыны сақтау орны", "Цикл түрі"],
            "correct": 2,
            "explanation": "String — мәтіндік таңбалар тізбегі."
        },
        {
            "type": "test",
            "question": "Python-да жолды қалай анықтауға болады?",
            "options": ["Тек қос тырнақшамен", "Тек бір тырнақшамен", "Бір немесе қос тырнақшамен", "Тек list арқылы"],
            "correct": 3,
            "explanation": "Жол бір тырнақшада да, қос тырнақшада да жазылады."
        },
        {
            "type": "test",
            "question": "Жолдың ұзындығын анықтау үшін қандай функция қолданылады?",
            "options": ["size()", "count()", "len()", "length()"],
            "correct": 3,
            "explanation": "len() жолдағы таңбалар санын қайтарады."
        },
        {
            "type": "test",
            "question": "s = 'Python'; print(s[2]) нәтижесі қандай?",
            "options": ["t", "y", "h", "P"],
            "correct": 1,
            "explanation": "Индекстер 0-ден басталады: P=0, y=1, t=2."
        },
        {
            "type": "test",
            "question": "Жолды кіші әріпке айналдыру әдісі қайсы?",
            "options": ["lower()", "upper()", "capitalize()", "title()"],
            "correct": 1,
            "explanation": "lower() барлық әріпті кіші әріпке айналдырады."
        },
        {"type": "theory", "question": "Жолдардың индекстеу және slicing принципін түсіндіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "split(), replace(), strip() әдістерінің қызметін мысалмен түсіндіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "f-string форматтауы не үшін қолданылады?", "teacher_check": True},
        {
            "type": "code_fill",
            "question": "'Python' сөзін шығару үшін бос орынды толтырыңыз.",
            "template": "s = 'Python programming'\nprint(s[:______])",
            "expected_output": "Python",
            "correct": ["6"],
            "explanation": "s[:6] алғашқы 6 таңбаны алады."
        },
        {
            "type": "code_fill",
            "question": "Жолды үтір арқылы бөлу үшін бос орынды толтырыңыз.",
            "template": "text = 'apple,banana,cherry'\nitems = text.______(',')\nprint(items)",
            "expected_output": "['apple', 'banana', 'cherry']",
            "correct": ["split"],
            "explanation": "split(',') жолды үтір бойынша бөліктерге бөледі."
        },
    ],

    "2.3.3": [
        {
            "type": "test",
            "question": "Python сөздігінде кілт ретінде қандай типтер қолданылуы мүмкін?",
            "options": ["Кез келген тип", "Тек өзгермейтін типтер", "Тек тізімдер", "Тек сөздіктер"],
            "correct": 2,
            "explanation": "Сөздік кілті immutable болуы керек: str, int, tuple сияқты."
        },
        {
            "type": "test",
            "question": "Сөздікті дұрыс құру тәсілі қайсы?",
            "options": ["my_dict = {1: 'бір', 'екі': 2}", "my_dict = (1: 'бір')", "my_dict = [1: 'бір']", "my_dict = dict[]"],
            "correct": 1,
            "explanation": "Сөздік key: value жұптарынан тұрады және {} арқылы жазылады."
        },
        {
            "type": "test",
            "question": "Python-да бос сөздік қалай құрылады?",
            "options": ["[]", "dict[]", "{}", "set()"],
            "correct": 3,
            "explanation": "{} бос сөздік жасайды."
        },
        {
            "type": "test",
            "question": "Сөздіктен элементті қауіпсіз алу үшін қандай әдіс қолданылады?",
            "options": ["remove()", "get()", "delete()", "fetch()"],
            "correct": 2,
            "explanation": "get() кілт жоқ болса қате шығармай, None немесе default мән қайтарады."
        },
        {
            "type": "test",
            "question": "Сөздіктің барлық кілттерін алу әдісі қайсы?",
            "options": ["keys()", "values()", "items()", "all_keys()"],
            "correct": 1,
            "explanation": "keys() сөздіктің барлық кілттерін қайтарады."
        },
        {"type": "theory", "question": "Сөздік дегеніміз не және ол қандай жағдайда қолданылады?", "teacher_check": True},
        {"type": "theory", "question": "Кілт пен мән ұғымдарын мысалмен түсіндіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "get() және [] арқылы мән алудың айырмашылығы қандай?", "teacher_check": True},
        {
            "type": "code_fill",
            "question": "Сөздіктен city кілтін қауіпсіз алу үшін бос орынды толтырыңыз.",
            "template": "my_dict = {'name': 'Alice', 'age': 25}\nprint(my_dict.______('city', 'Қала жоқ'))",
            "expected_output": "Қала жоқ",
            "correct": ["get"],
            "explanation": "get('city', 'Қала жоқ') кілт табылмаса, default мәнді қайтарады."
        },
        {
            "type": "code_fill",
            "question": "Сөздікке жаңа элемент қосу үшін бос орынды толтырыңыз.",
            "template": "student = {'name': 'Ali'}\nstudent[______] = 20\nprint(student)",
            "expected_output": "{'name': 'Ali', 'age': 20}",
            "correct": ["'age'"],
            "explanation": "Жаңа key арқылы мән меншіктеу сөздікке жаңа элемент қосады."
        },
    ],

    "2.3.4": [
        {
            "type": "test",
            "question": "Кортеж (tuple) дегеніміз не?",
            "options": ["Өзгермейтін ретті деректер құрылымы", "Өзгермелі тізім", "Кілт-мән жұбы", "Тек сандар тізімі"],
            "correct": 1,
            "explanation": "Tuple — өзгермейтін, ретті деректер құрылымы."
        },
        {
            "type": "test",
            "question": "Кортежді қалай құруға болады?",
            "options": ["{1,2,3}", "[1,2,3]", "(1,2,3)", "'1,2,3'"],
            "correct": 3,
            "explanation": "Кортеж дөңгелек жақшамен жазылады."
        },
        {
            "type": "test",
            "question": "Кортеж бен тізімнің басты айырмашылығы қандай?",
            "options": ["Кортеж өзгермейді, тізім өзгереді", "Кортеж өзгереді, тізім өзгермейді", "Екеуі бірдей", "Тізім тек мәтін сақтайды"],
            "correct": 1,
            "explanation": "Tuple immutable, ал list mutable."
        },
        {
            "type": "test",
            "question": "Кортеждегі элементтерді өзгертуге бола ма?",
            "options": ["Иә, append() арқылы", "Иә, remove() арқылы", "Жоқ, өзгерту мүмкін емес", "Иә, insert() арқылы"],
            "correct": 3,
            "explanation": "Кортеж immutable болғандықтан элементтерін тікелей өзгертуге болмайды."
        },
        {
            "type": "test",
            "question": "Кортежді тізімге қалай түрлендіруге болады?",
            "options": ["list(кортеж)", "convert(кортеж)", "to_list(кортеж)", "change(кортеж)"],
            "correct": 1,
            "explanation": "list(tuple_name) кортежді тізімге айналдырады."
        },
        {"type": "theory", "question": "Кортеждің тізімнен айырмашылығын түсіндіріңіз.", "teacher_check": True},
        {"type": "theory", "question": "Кортеж қандай жағдайларда тиімді қолданылады?", "teacher_check": True},
        {"type": "theory", "question": "Tuple unpacking дегеніміз не? Мысал келтіріңіз.", "teacher_check": True},
        {
            "type": "code_fill",
            "question": "Кортежден екінші элементті шығару үшін бос орынды толтырыңыз.",
            "template": "t = (10, 20, 30)\nprint(t[______])",
            "expected_output": "20",
            "correct": ["1"],
            "explanation": "Екінші элементтің индексі 1."
        },
        {
            "type": "code_fill",
            "question": "Кортежді тізімге айналдыру үшін бос орынды толтырыңыз.",
            "template": "my_tuple = (1, 2, 3)\nmy_list = ______(my_tuple)\nprint(my_list)",
            "expected_output": "[1, 2, 3]",
            "correct": ["list"],
            "explanation": "list() функциясы кортежді өзгермелі тізімге түрлендіреді."
        },
    ],
}

# Старые внутренние темы қалсын десең, compatibility үшін:
QUIZZES["Python тіліне кіріспе"] = QUIZZES["1.1.1"]
QUIZZES["Цикл"] = QUIZZES["1.2.1"]
QUIZZES["Бірөлшемді тізімдер"] = QUIZZES["1.3.2"]
QUIZZES["Массив"] = QUIZZES["2.1.1"]
QUIZZES["Екі өлшемді массивтер"] = QUIZZES["2.2.1"]
QUIZZES["Ішкі бағдарламалар"] = QUIZZES["2.3.1"]

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
        quiz.correct = req.correct
        quiz.total = req.total
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
@app.get("/leaderboard/")
def leaderboard():
    db = SessionLocal()
    rows = db.query(TopicQuizResult).all()

    students = {}

    for r in rows:
        key = r.user.username

        if key not in students:
            students[key] = {
                "username": r.user.username,
                "email": r.user.email,
                "points": 0,
                "total": 0
            }

        percent = int((r.correct / r.total) * 100) if r.total else 0
        teacher_percent = (r.teacher_grade * 10) if r.teacher_grade is not None else percent

        students[key]["points"] += teacher_percent
        students[key]["total"] += 1

    result = []
    for s in students.values():
        avg = round(s["points"] / s["total"]) if s["total"] else 0
        result.append({
            "username": s["username"],
            "email": s["email"],
            "percent": avg
        })

    result.sort(key=lambda x: x["percent"], reverse=True)

    db.close()
    return {"leaderboard": result}


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

def get_student_level(username: str | None, email: str | None) -> dict:
    if not username or not email:
        return {"level": "beginner", "percent": None}

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username, User.email == email).first()
        if not user:
            return {"level": "beginner", "percent": None}

        percents = []
        for result in user.quiz_results:
            if result.total and result.total > 0:
                auto_percent = (result.correct / result.total) * 100
                teacher_percent = result.teacher_grade * 10 if result.teacher_grade is not None else None
                percents.append(teacher_percent if teacher_percent is not None else auto_percent)

        if not percents:
            return {"level": "beginner", "percent": None}

        avg_percent = sum(percents) / len(percents)
        if avg_percent >= 80:
            level = "advanced"
        elif avg_percent >= 55:
            level = "middle"
        else:
            level = "beginner"
        return {"level": level, "percent": round(avg_percent, 1)}
    finally:
        db.close()


def build_interactive_task_prompt(topic: str, internal_topic: str, lecture_content: str, student_level: dict) -> str:
    level = student_level.get("level", "beginner")
    difficulty_rules = {
        "beginner": "Оңай деңгей: таныс синтаксис, 1 цикл немесе 1 шарт, қысқа код, бір нақты ой.",
        "middle": "Орта деңгей: 2-3 қадамдық логика, тізім/цикл/шарт бірге қолданылуы мүмкін.",
        "advanced": "Күрделі деңгей: бірнеше қадам, функция, тізім өңдеу, қате талдау немесе output болжау.",
    }
    lecture_block = ""
    if lecture_content:
        lecture_block = f"\nЛекция материалы. Тек осы материал мен тақырыпқа сүйен:\n---\n{lecture_content}\n---\n"

    return f"""
Сен Python пәнінен тәжірибелі қазақ тілді мұғалімсің.
Мақсат: тест пен ашық сұрақ емес, оқушы әрекет жасайтын интерактивті практикалық тапсырмалар құрастыру.

Тақырып ID: {topic}
Тақырып атауы: {internal_topic}
Оқушы деңгейі: {level}
Деңгей ережесі: {difficulty_rules.get(level, difficulty_rules["beginner"])}
{lecture_block}

Тек JSON қайтар. Markdown, түсіндірме мәтін, ``` қолданба.
Жауап дәл мына құрылымда болсын: {{"questions":[...]}}

Қатаң формат:
- Дәл 10 тапсырма болсын.
- test, theory, open_question типтерін мүлде қолданба.
- Барлық мәтін қазақ тілінде болсын.
- Әр тапсырма берілген тақырыпқа тікелей қатысты болсын.
- Бірдей шаблонды қайталама: тапсырмалар әртүрлі ойлау әрекетін талап етсін.
- Әр тапсырмада explanation міндетті түрде болсын.
- Әр тапсырмада difficulty: "beginner", "middle" немесе "advanced" болсын.

Міндетті тапсырма құрамы:
- 1-2: matching
- 3-5: code_fill
- 6-7: order_lines
- 8: find_error
- 9-10: predict_output немесе find_error

matching форматы:
{{
  "type":"matching",
  "difficulty":"{level}",
  "question":"Сәйкестендіріңіз: ...",
  "left":["Python ұғымы 1","Python ұғымы 2","Python ұғымы 3","Python ұғымы 4"],
  "right":["Түсіндірме A","Түсіндірме B","Түсіндірме C","Түсіндірме D"],
  "answer":[0,2,1,3],
  "explanation":"Неге осылай сәйкестенеді"
}}
answer массиві left индексі бойынша дұрыс right индексін көрсетеді. right реті аралас болсын.

code_fill форматы:
{{
  "type":"code_fill",
  "difficulty":"{level}",
  "question":"Код дұрыс жұмыс істеуі үшін ______ орнына бір сөз немесе бір оператор жазыңыз.",
  "template":"5-10 жолдық толық Python коды, ішінде тек бір ______ болсын",
  "expected_output":"экранда шығатын нақты нәтиже",
  "answer":["бір ғана дұрыс сөз немесе оператор"],
  "explanation":"Неге осы жауап дұрыс"
}}

order_lines форматы:
{{
  "type":"order_lines",
  "difficulty":"{level}",
  "question":"Код дұрыс орындалуы үшін жолдарды дұрыс ретке қойыңыз.",
  "lines":["араласқан жол 1","араласқан жол 2","араласқан жол 3","араласқан жол 4","араласқан жол 5"],
  "answer":[2,0,4,1,3],
  "expected_output":"экранда шығатын нақты нәтиже",
  "explanation":"Неге осы рет дұрыс"
}}
answer массиві lines ішіндегі индекстердің дұрыс орындалу ретін көрсетеді.

find_error форматы:
{{
  "type":"find_error",
  "difficulty":"{level}",
  "question":"Кодтағы қатені табыңыз және дұрыс жолды жазыңыз.",
  "template":"5-10 жолдық Python коды, ішінде бір ғана синтаксистік немесе логикалық қате болсын",
  "answer":["қате жолдың дұрыс нұсқасы"],
  "expected_output":"қате түзелгеннен кейін шығатын нәтиже",
  "explanation":"Қате неде және неге осылай түзетіледі"
}}

predict_output форматы:
{{
  "type":"predict_output",
  "difficulty":"{level}",
  "question":"Код орындалғанда экранға не шығады?",
  "template":"5-10 жолдық толық Python коды",
  "answer":["нақты output"],
  "expected_output":"нақты output",
  "explanation":"Нәтиже қалай шықты"
}}

Сапа ережелері:
- Python синтаксисі дұрыс болсын.
- Кодтар оқушыға түсінікті, бірақ тым қарапайым емес болсын.
- Айнымалы аттары мағыналы болсын: numbers, total, name, scores, matrix, text.
- Тақырып цикл болса: for/while/range/break/continue бойынша нақты код бер.
- Тақырып тізім/массив болса: индекстер, append, len, циклмен өңдеу, сұрыптау қолдан.
- Тақырып функция болса: def, параметр, return, шақыру қолдан.
- Тақырып сөздік/кортеж/жол болса: дәл сол құрылымға арналған операциялар қолдан.
- Жауаптар автоматты тексеруге ыңғайлы қысқа және нақты болсын.
"""


REQUIRED_INTERACTIVE_ORDER = [
    "matching", "matching",
    "code_fill", "code_fill", "code_fill",
    "order_lines", "order_lines",
    "find_error",
    None, None,
]


def validate_interactive_question(q: dict, idx: int) -> dict:
    if not isinstance(q, dict):
        raise ValueError("question is not object")

    q_type = q.get("type")
    expected_type = REQUIRED_INTERACTIVE_ORDER[idx]
    if expected_type and q_type != expected_type:
        raise ValueError(f"question {idx + 1} must be {expected_type}")
    if expected_type is None and q_type not in {"find_error", "predict_output"}:
        raise ValueError(f"question {idx + 1} must be find_error or predict_output")
    if q_type in {"test", "theory", "open_question"}:
        raise ValueError("old question type is not allowed")
    if not q.get("question") or not q.get("explanation"):
        raise ValueError("question and explanation are required")

    if q_type == "matching":
        if not all(isinstance(q.get(key), list) for key in ("left", "right", "answer")):
            raise ValueError("matching fields are invalid")
        if len(q["left"]) < 3 or len(q["left"]) != len(q["right"]) or len(q["answer"]) != len(q["left"]):
            raise ValueError("matching lengths are invalid")
    elif q_type == "order_lines":
        if not isinstance(q.get("lines"), list) or not isinstance(q.get("answer"), list):
            raise ValueError("order_lines fields are invalid")
        if len(q["lines"]) < 4 or len(q["answer"]) != len(q["lines"]):
            raise ValueError("order_lines length is invalid")
        if sorted(q["answer"]) != list(range(len(q["lines"]))):
            raise ValueError("order_lines answer must contain all indexes")
    else:
        answers = q.get("answer")
        if not q.get("template") or not isinstance(answers, list) or not answers:
            raise ValueError(f"{q_type} template and answer are required")
        if q_type == "code_fill":
            template = str(q.get("template", ""))
            blank_count = template.count("______")
            if blank_count == 0:
                answer_text = str(answers[0])
                if answer_text and answer_text in template:
                    q["template"] = template.replace(answer_text, "______", 1)
                else:
                    raise ValueError("code_fill must contain exactly one blank")
            elif blank_count > 1:
                raise ValueError("code_fill must contain exactly one blank")

    q.setdefault("difficulty", "beginner")
    return q


def normalize_interactive_questions(raw_questions: list) -> list:
    clean_questions = []

    for idx, q in enumerate(raw_questions[:10]):
        clean_questions.append(validate_interactive_question(q, idx))


    if len(clean_questions) != 10:
        raise ValueError("exactly 10 questions are required")
    return clean_questions


def complete_interactive_questions(raw_questions: list, fallback_questions: list) -> list:
    completed = []
    for idx in range(10):
        candidate = raw_questions[idx] if idx < len(raw_questions) else None
        try:
            completed.append(validate_interactive_question(candidate, idx))
        except Exception:
            completed.append(validate_interactive_question(fallback_questions[idx], idx))
    return completed


def build_interactive_fallback(topic: str, internal_topic: str, level: str) -> list:
    title = internal_topic or topic
    return [
        {
            "type": "matching",
            "difficulty": level,
            "question": f"{title} тақырыбы бойынша ұғымдарды мағынасымен сәйкестендіріңіз.",
            "left": ["print()", "айнымалы", "input()", "int"],
            "right": ["Бүтін сан типі", "Экранға нәтиже шығарады", "Пернетақтадан мән оқиды", "Мән сақтайтын атау"],
            "answer": [1, 3, 2, 0],
            "explanation": "Әр ұғым Python кодында нақты қызмет атқарады: шығару, сақтау, енгізу және типке айналдыру.",
        },
        {
            "type": "matching",
            "difficulty": level,
            "question": f"{title} тақырыбындағы код бөліктерін қызметімен сәйкестендіріңіз.",
            "left": ["for", "if", "range()", "len()"],
            "right": ["Ұзындықты анықтайды", "Қайталау жасайды", "Шартты тексереді", "Сандар тізбегін құрады"],
            "answer": [1, 2, 3, 0],
            "explanation": "Бұл құралдар Python-да алгоритм құрудың негізгі бөліктері ретінде бірге жиі қолданылады.",
        },
        {
            "type": "code_fill",
            "difficulty": level,
            "question": "Код 1-ден 5-ке дейінгі сандарды шығару үшін бос орынды толтырыңыз.",
            "template": "start = 1\nfinish = 5\n\nfor number in range(start, finish + 1):\n    ______(number)",
            "expected_output": "1\n2\n3\n4\n5",
            "answer": ["print"],
            "explanation": "print() функциясы әр number мәнін экранға шығарады.",
        },
        {
            "type": "code_fill",
            "difficulty": level,
            "question": "Қосынды дұрыс есептелуі үшін бос орынды толтырыңыз.",
            "template": "numbers = [2, 4, 6]\ntotal = 0\n\nfor number in numbers:\n    total = total + ______\n\nprint(total)",
            "expected_output": "12",
            "answer": ["number"],
            "explanation": "Цикл әр айналымда ағымдағы number мәнін total айнымалысына қосады.",
        },
        {
            "type": "code_fill",
            "difficulty": level,
            "question": "Шарт тек жұп сандарды шығару үшін бос орынды толтырыңыз.",
            "template": "numbers = [1, 2, 3, 4, 5, 6]\n\nfor number in numbers:\n    if number % 2 ______ 0:\n        print(number)",
            "expected_output": "2\n4\n6",
            "answer": ["=="],
            "explanation": "== операторы қалдықтың 0-ге тең екенін тексереді.",
        },
        {
            "type": "order_lines",
            "difficulty": level,
            "question": "Код жолдарын дұрыс ретке қойыңыз.",
            "lines": ["print(total)", "for number in numbers:", "numbers = [3, 5, 7]", "    total += number", "total = 0"],
            "answer": [2, 4, 1, 3, 0],
            "expected_output": "15",
            "explanation": "Алдымен тізім мен total дайындалады, содан кейін цикл қосындыны есептеп, соңында нәтиже шығарылады.",
        },
        {
            "type": "order_lines",
            "difficulty": level,
            "question": "Шартпен жұмыс істейтін кодты дұрыс ретке қойыңыз.",
            "lines": ["    print('үлкен')", "value = 8", "else:", "if value > 5:", "    print('кіші немесе тең')"],
            "answer": [1, 3, 0, 2, 4],
            "expected_output": "үлкен",
            "explanation": "Алдымен value беріледі, кейін if шарты тексеріледі, else блогы соңынан жазылады.",
        },
        {
            "type": "find_error",
            "difficulty": level,
            "question": "Кодтағы қатені табыңыз және дұрыс жолды жазыңыз.",
            "template": "scores = [80, 90, 75]\ntotal = 0\n\nfor score in scores\n    total += score\n\nprint(total)",
            "answer": ["for score in scores:"],
            "expected_output": "245",
            "explanation": "for жолының соңында қос нүкте болуы керек, өйткені одан кейін цикл блогы басталады.",
        },
        {
            "type": "predict_output",
            "difficulty": level,
            "question": "Код орындалғанда экранға не шығады?",
            "template": "items = ['a', 'b', 'c']\ncount = 0\n\nfor item in items:\n    count += 1\n\nprint(count)",
            "answer": ["3"],
            "expected_output": "3",
            "explanation": "Тізімде үш элемент бар, цикл үш рет орындалып count мәні 3 болады.",
        },
        {
            "type": "predict_output",
            "difficulty": level,
            "question": "Код орындалғанда экранға не шығады?",
            "template": "numbers = [1, 2, 3, 4]\nresult = []\n\nfor number in numbers:\n    if number > 2:\n        result.append(number)\n\nprint(result)",
            "answer": ["[3, 4]"],
            "expected_output": "[3, 4]",
            "explanation": "Шарттан тек 3 және 4 өтеді, сондықтан result тізіміне осы мәндер қосылады.",
        },
    ]


@app.post("/generate_tasks/")
def generate_interactive_tasks(req: TaskRequest):
    topic = req.topic
    internal_topic = QUIZ_MAPPING.get(topic, topic)
    lecture_content = get_lecture_text(topic)
    student_level = get_student_level(req.username, req.email)
    context_msg = build_interactive_task_prompt(topic, internal_topic, lecture_content, student_level)

    user_prompt = (
        f"{internal_topic} ({topic}) тақырыбы бойынша дәл 10 интерактивті тапсырма дайында. "
        "Тест және ашық сұрақ қоспа. Ретті қатаң сақта."
    )

    try:
        last_error = None
        last_text = ""
        for attempt in range(2):
            current_prompt = user_prompt
            if attempt == 1:
                current_prompt = (
                    "Алдыңғы JSON қате болды. Оны толық қайта құрастыр.\n"
                    f"Қате себебі: {last_error}\n"
                    "Ең маңыздысы: code_fill тапсырмаларының template ішінде дәл бір ғана ______ болуы керек.\n"
                    "matching/order_lines answer массивтері индекс ретінде берілсін.\n"
                    "Тек дұрыс JSON қайтар: {\"questions\":[...]}\n"
                    f"Алдыңғы жауап:\n{last_text[:2500]}"
                )

            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": context_msg},
                    {"role": "user", "content": current_prompt},
                ],
                max_tokens=3200,
                temperature=0.55,
            )
            last_text = response.choices[0].message.content
            try:
                parsed_json = json.loads(last_text)
                questions = normalize_interactive_questions(parsed_json.get("questions", []))
                break
            except Exception as validation_error:
                last_error = validation_error
        else:
            raise ValueError(f"invalid generated questions after retry: {last_error}")

        return {
            "topic": topic,
            "level": student_level["level"],
            "student_percent": student_level["percent"],
            "questions": questions,
        }
    except Exception as e:
        print(f"[generate_tasks] GPT error for topic={topic}: {e}")
        fallback = build_interactive_fallback(topic, internal_topic, student_level["level"])
        return {"topic": topic, "level": student_level["level"], "questions": fallback}


@app.post("/generate_tasks_legacy/")
def generate_tasks(req: TaskRequest):
    topic = req.topic
    #if topic in QUIZZES:
        #return {"topic": topic, "questions": QUIZZES[topic]}
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
        "Тест сұрақтары логикалық, нақты және Python тақырыбына сай болсын.\n"
        "Өте оңай немесе мағынасыз жауаптар берме.\n"
        "'Түсінбеймін', 'Білмеймін', 'Қате' сияқты жауап нұсқаларын қолданба.\n"
        "Жауап нұсқалары бір-біріне ұқсас және ойландыратын болсын.\n"
        "Сұрақтар теория емес, практикалық ойлау деңгейінде болсын.\n"
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
                "teacher_grade": q.teacher_grade,
                "teacher_comment": q.teacher_comment,
                "answers": q.answers,
                "correct": q.correct,
                "total": q.total,
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
            "teacher_grade": t.get("teacher_grade"),
            "teacher_comment": t.get("teacher_comment"),
            "answers": t.get("answers"),
            "correct": t.get("correct"),
            "total": t.get("total"),
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
