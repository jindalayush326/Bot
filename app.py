from flask import Flask, render_template, request, session, flash, redirect, url_for
from openai import OpenAI
from os import getenv
import os
import secrets
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import google.generativeai as genai
import firebase_admin
from firebase_admin import credentials, auth
from PIL import Image
from scripts.helper import process_images, get_gemini_response
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# Load environment variables
load_dotenv()

# Initialize Flask app
secret_key = secrets.token_hex(16)
app = Flask(__name__)
app.secret_key = secret_key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///messages.db'
db = SQLAlchemy(app)

# Initialize Firebase Admin SDK
cred = credentials.Certificate("D:/ml/gemini/agriculture_bot/serviceAccountKey.json")  # Replace with your service account key path
firebase_admin.initialize_app(cred)

# Initialize OpenAI client
client = OpenAI(
    api_key=os.getenv('DEEPINFRA_API_KEY'),
    base_url="https://api.deepinfra.com/v1/openai",
)

# Configure Google generative AI
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

preprompt = """\n\nYOU ARE NOT AN ASSISTANT for help, YOU ARE THE PERSON WITH THE ABOVE NAME. Write the person's next reply in a fictional chat between the above person and User. Write 1 reply only in chat style, italicize actions, and avoid quotation marks. 
Use markdown. Be proactive, creative, and drive the plot and conversation forward. 
Always stay in character and avoid repetition."""

# Define the database model
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('usr.id'))

class User(db.Model):
    __tablename__ = 'usr'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(500), nullable=False)
    dob = db.Column(db.Date, nullable=False)
    system_message = db.Column(db.Text)  # New field for storing the system message
    
    def set_password(self, password):
        self.password = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password, password)

# Create the database tables
with app.app_context():
    db.create_all()

# Create a new route for the sign-in page
@app.route('/signin', methods=['GET', 'POST'])
def signin():
    if 'user_id' in session:
        return redirect(url_for('home'))  # Redirect to home page if user is already logged in
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id  # Set user session
            session['user_name'] = user.name  # Set user name in session
            session['user_username'] = user.username  # Set username in session
            session['user_dob'] = user.dob.strftime('%Y-%m-%d')  # Set dob in session
            session['system_message'] = user.system_message  # Set system message in session
            # Redirect to layout.html page via upload route if system message is empty
            if not user.system_message:
                return redirect(url_for('image'))  # Redirect to upload page
            return redirect(url_for('home'))  # Redirect to home page
        else:
            flash('Incorrect username or password.')
            return redirect(url_for('signin'))  # Redirect to sign in page again
    # Render the sign-in form for GET requests
    return render_template('signin.html')

# Modify the register route to check if a user with the provided username already exists
@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('home'))  # Redirect to home page if user is already logged in
    
    if request.method == 'POST':
        if request.form.get('google_signup'):
            # Handle Google signup
            id_token = request.form.get('id_token')
            try:
                # Verify Firebase ID token
                decoded_token = auth.verify_id_token(id_token)
                # Get user details
                name = decoded_token.get("name")
                email = decoded_token.get("email")
                # Pre-fill the registration form fields with Google user details
                return render_template('register.html', name=name, username=email.split('@')[0])
            except auth.AuthError as e:
                flash("Google signup failed: {}".format(e))
                return redirect(url_for("register"))
            
        # Get user details from the form
        name = request.form['name']
        username = request.form['username']
        password = request.form['password']
        dob_str = request.form['dob']
        dob_date = datetime.strptime(dob_str, '%Y-%m-%d')
        
        # Check if username already exists
        existing_user_same_username = User.query.filter_by(username=username).first()
        if existing_user_same_username:
            # Username already exists, show message
            flash('Username already exists. Please sign in.')
            return redirect(url_for('signin'))  # Redirect to sign in page
        
        # Save user to the database
        user = User(name=name, username=username, dob=dob_date)
        user.set_password(password)  # Set the hashed password
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please sign in.')
        return redirect(url_for('signin'))  # Redirect to sign in page
    
    # Render the registration form for GET requests
    return render_template('register.html')

# Define the route for the home page
@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('register'))  # Redirect to register page if not logged in
    return render_template('home.html')

# Define the route for the file upload page
@app.route('/image', methods=['GET', 'POST'])
def image():
    if 'user_id' not in session:
        return redirect(url_for('register'))  # Redirect to register page if not logged in

    if request.method == 'POST':
        uploaded_files = request.files.getlist('file')
        for uploaded_file in uploaded_files:
            # Process each uploaded file as needed
            pass

        flash('Files uploaded successfully!')
        return redirect(url_for('home'))  # Redirect to home page after file upload

    return render_template('image.html')

# Define the route for uploading files
@app.route('/upload', methods=['POST'])
def upload():
    uploaded_files = request.files.getlist('file')
    for uploaded_file in uploaded_files:
        file_type = uploaded_file.content_type
        if file_type.startswith('image/'):
            # Process image files
            image = Image.open(uploaded_file)
            # Implement the process_images function to handle images
            process_images([image])
        else:
            # Handle other file types
            file_content = uploaded_file.read()
            # Implement a function to process other file types if necessary
            process_other_files(file_content)
    
    flash('Files processed successfully!')
    return redirect(url_for('home'))

# Define the route for sending messages
@app.route('/send_message', methods=['POST'])
def send_message():
    user_message = request.form['message']
    messages = session.get('conversation', [])
    # Retrieve user from the database
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    if user:
        # Retrieve all messages from the database for this user
        previous_messages = Message.query.filter_by(user_id=user_id).all()
        for msg in previous_messages:
            messages.append({"role": msg.role, "content": msg.content})
    else:
        messages=[]

    # Check if system_message is already set in the session
        if 'system_message' not in session:
        # Set the system message from the database
            session['system_message'] = user.system_message if user else None

    # Append system message before user message
    messages.append({"role": "system", "content": session['system_message']})
    messages.append({"role": "user", "content": user_message})
    
    # Save the user message to the database
    user_msg = Message(role='user', content=user_message, user_id=user_id)
    db.session.add(user_msg)
    db.session.commit()
    
    response = client.chat.completions.create(
        model="cognitivecomputations/dolphin-2.6-mixtral-8x7b",
        messages=messages,
    )
    assistant_message = response.choices[0].message.content
    messages.append({"role": "assistant", "content": assistant_message})
    session['conversation'] = messages
    
    # Save the assistant message to the database
    assistant_msg = Message(role='assistant', content=assistant_message, user_id=user_id)
    db.session.add(assistant_msg)
    db.session.commit()

    return {'assistant': assistant_message}

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')
