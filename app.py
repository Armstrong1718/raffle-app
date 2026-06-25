from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import random
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///raffle.db'
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-change-this')
app.config['JSON_SORT_KEYS'] = False

db = SQLAlchemy(app)

# Database Models
class Raffle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    prize = db.Column(db.String(200))
    ticket_price = db.Column(db.Float, default=0.0)
    max_entries = db.Column(db.Integer)
    drawing_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='active')  # active, completed, upcoming
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    participants = db.relationship('Participant', backref='raffle', lazy=True, cascade='all, delete-orphan')
    winner_id = db.Column(db.Integer)
    winner_name = db.Column(db.String(100))

class Participant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    raffle_id = db.Column(db.Integer, db.ForeignKey('raffle.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120))
    entries = db.Column(db.Integer, default=1)
    signed_up_at = db.Column(db.DateTime, default=datetime.utcnow)

# Create tables
with app.app_context():
    db.create_all()

# Routes - Public Pages
@app.route('/')
def index():
    active_raffles = Raffle.query.filter_by(status='active').all()
    upcoming_raffles = Raffle.query.filter_by(status='upcoming').all()
    return render_template('index.html', active_raffles=active_raffles, upcoming_raffles=upcoming_raffles)

@app.route('/raffle/<int:raffle_id>')
def raffle_detail(raffle_id):
    raffle = Raffle.query.get_or_404(raffle_id)
    total_entries = sum(p.entries for p in raffle.participants)
    return render_template('raffle_detail.html', raffle=raffle, total_entries=total_entries)

@app.route('/signup/<int:raffle_id>', methods=['GET', 'POST'])
def signup(raffle_id):
    raffle = Raffle.query.get_or_404(raffle_id)
    
    if request.method == 'POST':
        data = request.get_json()
        participant = Participant(
            raffle_id=raffle_id,
            name=data.get('name'),
            phone=data.get('phone'),
            email=data.get('email'),
            entries=int(data.get('entries', 1))
        )
        db.session.add(participant)
        db.session.commit()
        return jsonify({'success': True, 'participant_id': participant.id})
    
    return render_template('signup.html', raffle=raffle)

@app.route('/drawing/<int:raffle_id>')
def drawing(raffle_id):
    raffle = Raffle.query.get_or_404(raffle_id)
    participants = raffle.participants
    return render_template('drawing.html', raffle=raffle, participants=participants)

@app.route('/api/draw/<int:raffle_id>', methods=['POST'])
def api_draw(raffle_id):
    raffle = Raffle.query.get_or_404(raffle_id)
    
    # Create weighted list based on entries
    entries_list = []
    for participant in raffle.participants:
        entries_list.extend([participant.id] * participant.entries)
    
    if not entries_list:
        return jsonify({'error': 'No entries'}), 400
    
    winner_id = random.choice(entries_list)
    winner = Participant.query.get(winner_id)
    
    raffle.winner_id = winner_id
    raffle.winner_name = winner.name
    raffle.status = 'completed'
    db.session.commit()
    
    return jsonify({
        'winner_name': winner.name,
        'winner_phone': winner.phone,
        'entries': winner.entries
    })

# Admin Routes
@app.route('/admin')
def admin_login():
    if 'admin_logged_in' in session:
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_login.html')

@app.route('/admin/login', methods=['POST'])
def admin_do_login():
    data = request.get_json()
    admin_password = os.getenv('ADMIN_PASSWORD', 'admin123')
    
    if data.get('password') == admin_password:
        session['admin_logged_in'] = True
        return jsonify({'success': True})
    return jsonify({'success': False}), 401

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_logged_in' not in session:
        return redirect(url_for('admin_login'))
    
    raffles = Raffle.query.all()
    return render_template('admin_dashboard.html', raffles=raffles)

@app.route('/admin/raffle/create', methods=['POST'])
def admin_create_raffle():
    if 'admin_logged_in' not in session:
        return jsonify({'success': False}), 401
    
    data = request.get_json()
    drawing_date = datetime.fromisoformat(data.get('drawing_date'))
    
    raffle = Raffle(
        title=data.get('title'),
        description=data.get('description'),
        prize=data.get('prize'),
        ticket_price=float(data.get('ticket_price', 0)),
        max_entries=int(data.get('max_entries', 0)) or None,
        drawing_date=drawing_date,
        status=data.get('status', 'active')
    )
    db.session.add(raffle)
    db.session.commit()
    return jsonify({'success': True, 'raffle_id': raffle.id})

@app.route('/admin/raffle/<int:raffle_id>/edit', methods=['POST'])
def admin_edit_raffle(raffle_id):
    if 'admin_logged_in' not in session:
        return jsonify({'success': False}), 401
    
    raffle = Raffle.query.get_or_404(raffle_id)
    data = request.get_json()
    
    raffle.title = data.get('title', raffle.title)
    raffle.description = data.get('description', raffle.description)
    raffle.prize = data.get('prize', raffle.prize)
    raffle.status = data.get('status', raffle.status)
    
    if data.get('drawing_date'):
        raffle.drawing_date = datetime.fromisoformat(data.get('drawing_date'))
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/admin/raffle/<int:raffle_id>/delete', methods=['DELETE'])
def admin_delete_raffle(raffle_id):
    if 'admin_logged_in' not in session:
        return jsonify({'success': False}), 401
    
    raffle = Raffle.query.get_or_404(raffle_id)
    db.session.delete(raffle)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)