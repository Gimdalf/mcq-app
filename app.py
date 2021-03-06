from flask import Flask, request, render_template, url_for, redirect, send_file, make_response
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, IntegerField
from wtforms.validators import DataRequired, AnyOf, Length, NoneOf
import os
from flask_sqlalchemy import SQLAlchemy
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.platypus.tables import Table, TableStyle
from reportlab.pdfgen import canvas
from reportlab.lib.colors import black
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO
from math import ceil

app = Flask(__name__)
app.config['SECRET_KEY'] = '7PlzThx'

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'data.sqlite')
app.config['SLQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

#should return a list with one of all the elements of arguments
def merger(*argv):
	final = []
	for arg in argv:
		for i in arg:
			if i not in final:
				final.append(i)
	return final

#database declarations for students and papers
class Paper(db.Model):
	__tablename__ = 'papers'
	name = db.Column(db.String(64), primary_key=True, unique = True)
	no_of_questions = db.Column(db.Integer)
	choices = db.Column(db.String(32))
	answers = db.Column(db.JSON)
	students = db.relationship('Student', backref='paper', cascade="all, delete-orphan")
	#takes iterable answerz and returns enumerated dictionary
	def answerify(self, answerz):
		return dict(zip((i + 1 for i in range(len(answerz))), answerz))
	def listify(self):
		if len(self.answers.keys()) > 0:
			return list(self.answers[str(i)] for i in range(1, self.no_of_questions+1))
		else:
			return []
class Student(db.Model):
	__tablename__ = 'student'
	name = db.Column(db.String, primary_key = True)
	# answers = db.Column(db.Enum)
	paper_id = db.Column(db.String, db.ForeignKey('papers.name'), primary_key = True)
	answers = db.Column(db.JSON)
	def mark(self):
		return len(list(filter(lambda i: i[0] == i[1], ((self.answers.get(str(i)), self.paper.answers.get(str(i))) for i in range(1, self.paper.no_of_questions + 1)))))
	def listify(self):
		if len(self.answers.keys()) > 0:
			return list((self.answers[str(i)] for i in range(1, self.paper.no_of_questions+1)))
		else:
			return None	

db.create_all()
class InitializePaper(FlaskForm):
	name = StringField('Name of paper', validators = [DataRequired(), NoneOf(list(map(lambda x: x.name, Paper.query.all())))])
	qn = IntegerField('Number of questions in paper', validators = [DataRequired()])

	choyce = StringField('Possible answers', validators = [DataRequired()])
	create = SubmitField('Create')

class SubmitButton(FlaskForm):
	text = "Submit"
	button = SubmitField(text)

@app.route('/', methods = ['GET','POST']) 
def index():
	paperz = Paper.query.all()
	return render_template('index.html', paperz = paperz)

@app.route('/paper/<name>', methods = ['GET', 'POST'])
def paperView(name):
	paper = Paper.query.get(name)
	studentz = {i:{'name':student.name, 'student_answers':[student.listify()[j:ceil(paper.no_of_questions/4)*4:ceil(paper.no_of_questions/4)] for j in range(ceil(paper.no_of_questions/4))] + [None for i in range(paper.no_of_questions - (paper.no_of_questions % ceil(paper.no_of_questions/4)))] if paper.no_of_questions % 4 != 0 else [student.listify()[j:ceil(paper.no_of_questions/4)*4:ceil(paper.no_of_questions/4)] for j in range(ceil(paper.no_of_questions/4))], 'mark': student.mark()} for i, student in enumerate(paper.students)}
#change start from 0
	processed_questions = [{key: 0 for key in list(paper.choices)} for i in range(1, paper.no_of_questions+1)]
	for student in paper.students:
		student_answers = student.answers
		for i, answer in ((i, student_answers[str(i)]) for i in range(1, paper.no_of_questions + 1)):
			processed_questions[i-1][answer] += 1
#note: processed_questions is currently a dictionary in a list(no shit sherlock), where the index of the list is equal to the question number -1, while each possible choice has a corresponding dictionary key, with the value being the amount of occurences of the choice
	print(studentz)
	return render_template('paper.html', paper = paper, students = studentz, answers = paper.listify(), processed_questions = processed_questions, range = range, len = len, round = round, no_of_questions = (paper.no_of_questions, range(paper.no_of_questions), ceil(paper.no_of_questions/4)), student_keys = tuple(studentz.keys()))

@app.route('/newPaper', methods = ['GET', 'POST'])
def newPaper():
	class InitializePaper(SubmitButton):
		name = StringField('Name of paper', validators = [DataRequired(), NoneOf(list(map(lambda x: x.name, Paper.query.all())))])
		qn = IntegerField('Number of questions in paper', validators = [DataRequired()])
		choyce = StringField('Possible answers', validators = [DataRequired()])
	form = InitializePaper()
	if form.validate_on_submit():
		db.session.add(Paper(name = form.name.data, no_of_questions = form.qn.data, answers = {}, choices = "0"+form.choyce.data.upper()))
		db.session.commit()
		return redirect(url_for('paperAnswers', name = form.name.data, mode = 'create'))
	return render_template('createPaper.html', form = form)

@app.route('/paper/<name>/answers/<mode>', methods = ['GET', 'POST'])
def paperAnswers(name, mode):
	paper = Paper.query.get(name)
	class InputAnswer(SubmitButton):
		pass
	if mode == "edit":
		for i, answer in zip(range(1, paper.no_of_questions+1), paper.listify()):
			setattr(InputAnswer, str(i), StringField("Q{}".format(i), validators =[AnyOf(merger(paper.choices.lower(), paper.choices.upper())), Length(max=1)], default = answer))
	elif mode == "create":
		for i in range(1, paper.no_of_questions+1):
			setattr(InputAnswer, str(i), StringField("Q{}".format(i), validators = [AnyOf(merger(paper.choices.lower(), paper.choices.upper())), Length(max=1)]))
	form = InputAnswer()
	if form.validate_on_submit():
		answerString = {}
		for i in range(1, paper.no_of_questions+1):
			answerString[i] = getattr(form,str(i)).data.upper()
		paper.answers = answerString
		db.session.commit()
		return redirect(url_for('paperView', name = name))
	return render_template('inputAnswers.html', form = form, questions = list(map(lambda x: str(x), range(1, paper.no_of_questions +1))), getattr = getattr, name=paper.name)

@app.route('/paper/<name>/deletePaper', methods = ['GET', 'POST'])
def deletePaper(name):
	paper = Paper.query.get(name)
	form = SubmitButton()
	form.text = 'Delete'
	if request.method == 'POST':
		db.session.delete(paper)
		db.session.commit()
		return redirect(url_for('index'))
	return render_template('deletePaper.html', form = form, name = paper.name)

@app.route('/paper/<name>/newStudent', methods = ['GET', 'POST'])
def newStudent(name):
	#adding field for each question in form
	paper = Paper.query.get(name)
	class StudentForm(SubmitButton):
		pass
	no_of_questions = paper.no_of_questions
	setattr(StudentForm, "name", StringField('Name of student', validators = [DataRequired(), NoneOf(list(map(lambda x: x.name, paper.students)))]))
	for i in range(1, paper.no_of_questions+1):
		setattr(StudentForm, str(i), StringField("Q{}".format(i), validators =[Length(max=1), AnyOf(merger(paper.choices.lower(), paper.choices.upper()) + [''])]))
	form = StudentForm()
	if form.validate_on_submit():
		#reconversion of student's answers into integer value for storage
		db.session.add(Student(name = form.name.data, paper_id = name, answers = {key: getattr(form,str(i)).data.upper() if getattr(form,str(i)).data.upper() != '' else '0' for key in range(1, no_of_questions+1)}))
		db.session.commit()
		return redirect(url_for('paperView', name = name))
	return render_template('createStudent.html', form = form, questions = list(map(lambda x: str(x),range(1, no_of_questions+1))), getattr = getattr, name = paper.name)

@app.route('/paper/<name>/<student>/edit', methods = ['GET', 'POST'])
def editStudent(name, student):
	paper = Paper.query.get(name)
	student = Student.query.get((student, name))
	class StudentForm(SubmitButton):
		pass
	answers = student.paper.listify()
	setattr(StudentForm, "name", StringField('Name of student', validators = [DataRequired(), NoneOf(list(filter(lambda x: x != student.name, map(lambda x: x.name, paper.students))))], default = student.name))
	for i, answer in zip(range(1, paper.no_of_questions+1), student.listify()):
		setattr(StudentForm, str(i), StringField("Q{}".format(i), validators =[AnyOf(merger(paper.choices.lower(), paper.choices.upper()) + ['']), Length(max=1)], default = answer))
	form = StudentForm()
#Edit student answers doesn't work
	if form.validate_on_submit():
		db.session.delete(student)
		db.session.add(Student(name = form.name.data, paper_id = name, answers = {key: getattr(form,str(i)).data.upper() if getattr(form,str(i)).data.upper() != '' else '0' for key in range(1, paper.no_of_questions+1)}))
		db.session.commit()
		return redirect(url_for('paperView', name = name))
	return render_template('createStudent.html', form = form, name = name, questions = list(map(lambda x: str(x),range(1, paper.no_of_questions+1))), getattr = getattr)

@app.route('/paper/<name>/<student>/delete', methods = ['GET', 'POST'])
def deleteStudent(name, student):
	student = Student.query.get((student, name))
	form = SubmitButton()
	form.text = 'Delete'
	if request.method == 'POST':
		db.session.delete(student)
		db.session.commit()
		return redirect(url_for('paperView', name = name))
	return render_template('deletePaper.html', form = form, name = student.name)

def render_student(paper, student):
	per_row = 5
	per_column = ceil(paper.no_of_questions/per_row)
	style = getSampleStyleSheet()
		# text = Paragraph(, style['Normal'])
		# elements.append(text)
	ans = [['Student name: %s; Mark: %i/%i;'%(student.name, student.mark(), paper.no_of_questions)], ['Q', 'A', 'C', '']*per_row] + [[] for i in range(per_column)]
	print(ans)
	for i in range(paper.no_of_questions):
		print(i)
		stud_ans = student.answers[str(i+1)]
		pape_ans = paper.answers[str(i+1)]
		ans[2 + i % per_column].extend((str(i+1), pape_ans, stud_ans, '✓' if stud_ans == pape_ans else '✕'))
	table = Table(ans, spaceAfter = 20, spaceBefore = 20)
	table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 1, black), ('SPAN', (0, 0), (-1, 0)), ('NOSPLIT', (0,0), (-1,-1)), ('TOPPADDING', (0,2),(-1,-1), 3), ('BOTTOMPADDING', (0,2),(-1,-1), 3)]))
	return table

@app.route('/paper/<name>/<student>.pdf')
def viewStudent(name, student):
	buffer = BytesIO()
	doc = SimpleDocTemplate(buffer, topMargin=0, bottomMargin=0)
	doc.build([render_student(Paper.query.get(name), Student.query.get((student, name)))])
	pdf = buffer.getvalue()
	buffer.close()
	response = make_response(pdf)
	response.headers['Content-Type'] = 'application/pdf'
	response.headers['Content-Disposition'] = 'attachment; filename=%s_%s.pdf'%(name, student)
	return response

@app.route('/paper/<name>.pdf')
def printPaper(name):
	paper = Paper.query.get(name)
	elements = [render_student(paper, student) for student in paper.students]
	buffer = BytesIO()
	doc = SimpleDocTemplate(buffer, topMargin=0, bottomMargin=0)
	doc.build(elements)
	pdf = buffer.getvalue()
	buffer.close()
	response = make_response(pdf)
	response.headers['Content-Type'] = 'application/pdf'
	response.headers['Content-Disposition'] = 'attachment; filename=%s.pdf'%(name)
	return response

if __name__=="__main__":
	app.run()