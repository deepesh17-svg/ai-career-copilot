from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, session, send_file
from db import Base, engine, SessionLocal
import models
from ai import analyze_resume
import PyPDF2
import docx
import json

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO

app = Flask(__name__)
app.secret_key = "secret123"

Base.metadata.create_all(bind=engine)


@app.route("/")
def home():
    if "user" in session:
        return redirect("/dashboard")
    return redirect("/login")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    db = SessionLocal()

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        existing_user = db.query(models.User).filter_by(email=email).first()

        if existing_user:
            return "User already exists"

        hashed_password = generate_password_hash(password)

        user = models.User(email=email, password=hashed_password)
        db.add(user)
        db.commit()

        return redirect("/login")

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    db = SessionLocal()

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = db.query(models.User).filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            session["user"] = user.email
            return redirect("/dashboard")

        return "Invalid credentials"

    return render_template("login.html")


@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user" not in session:
        return redirect("/login")

    result = None

    if request.method == "POST":
        user_goal = request.form.get("role")
        resume_text = request.form.get("resume")
        file = request.files.get("file")

        if file and file.filename != "":
            if file.filename.endswith(".pdf"):
                try:
                    pdf_reader = PyPDF2.PdfReader(file)
                    text = ""

                    for page in pdf_reader.pages:
                        text += page.extract_text() or ""

                    resume_text = text

                except Exception as e:
                    result = {"error": f"PDF error: {str(e)}"}

            elif file.filename.endswith(".docx"):
                try:
                    doc = docx.Document(file)
                    text = ""

                    for para in doc.paragraphs:
                        text += para.text + "\n"

                    resume_text = text

                except Exception as e:
                    result = {"error": f"DOCX error: {str(e)}"}

        if resume_text and user_goal:
            try:
                result = analyze_resume(resume_text, user_goal)

                db = SessionLocal()
                user = db.query(models.User).filter_by(email=session["user"]).first()

                report = models.Report(
                    user_id=user.id,
                    resume_text=resume_text,
                    result=json.dumps(result)
                )

                db.add(report)
                db.commit()

            except Exception as e:
                result = {"error": f"AI error: {str(e)}"}

    return render_template(
        "dashboard.html",
        user=session["user"],
        result=result
    )


@app.route("/history")
def history():
    if "user" not in session:
        return redirect("/login")

    db = SessionLocal()
    user = db.query(models.User).filter_by(email=session["user"]).first()

    reports = db.query(models.Report).filter_by(user_id=user.id).all()

    parsed_reports = []

    for r in reports:
        try:
            parsed_result = json.loads(r.result)
        except:
            parsed_result = {}

        parsed_reports.append({
            "resume": r.resume_text,
            "result": parsed_result
        })

    return render_template("history.html", reports=parsed_reports)


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")


@app.route("/download-pdf")
def download_pdf():
    if "user" not in session:
        return redirect("/login")

    db = SessionLocal()
    user = db.query(models.User).filter_by(email=session["user"]).first()

    report = (
        db.query(models.Report)
        .filter_by(user_id=user.id)
        .order_by(models.Report.id.desc())
        .first()
    )

    if not report:
        return "No report found"

    result = json.loads(report.result)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)

    y = 750

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, y, "AI Career Copilot Report")
    y -= 40

    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, y, f"Resume Score: {result.get('resume_score', 'N/A')}")
    y -= 30

    sections = [
        ("Skills", result.get("skills", [])),
        ("Missing Skills", result.get("missing_skills", [])),
        ("Roadmap", result.get("roadmap", [])),
        ("Interview Questions", result.get("interview_questions", [])),
    ]

    for title, items in sections:
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(50, y, title)
        y -= 20

        pdf.setFont("Helvetica", 10)

        for item in items:
            pdf.drawString(60, y, f"- {item[:100]}")
            y -= 15

            if y < 50:
                pdf.showPage()
                y = 750

        y -= 10

    pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="ai_career_copilot_report.pdf",
        mimetype="application/pdf"
    )


if __name__ == "__main__":
    app.run(debug=True)