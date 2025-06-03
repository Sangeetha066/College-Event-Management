import os
import io
from flask import Flask, request, render_template, send_file, redirect, url_for, session
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from bs4 import BeautifulSoup
from fpdf import FPDF
from PIL import Image

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.secret_key = 'supersecretkey'

# Google Drive Setup
SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = 'credentials.json'
GOOGLE_DRIVE_FOLDER_ID = '1sgccWAi_VT8-PxIFfWPGr177uO5-fdNq'

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=credentials)

class PDF(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_text_color(0, 0, 0)
        self.set_font('DejaVu', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Get form data
        data = {
            'univ': request.form.get('univ_name', ''),
            'college': request.form.get('college_name', ''),
            'dept': request.form.get('dropdown', ''),
            'event_type': request.form.get('event_type', ''),
            'title': request.form.get('event_title', ''),
            'venue': request.form.get('event_venue', ''),
            'date': request.form.get('event_date', ''),
            'participant': request.form.get('participant', ''),
            'resource': request.form.get('resource', ''),
            'count': request.form.get('participant_count', ''),
            'desc': request.form.get('event_description', ''),
            'photo_desc': request.form.get('photo_desc', '').split(',')
        }

        # Upload invitation image
        invitation_path = None
        invitation_file = request.files.get('invitation_image')
        if invitation_file:
            invitation_path = save_and_prepare_image(invitation_file)
            upload_to_drive(os.path.basename(invitation_path), invitation_path)

        # Upload event photos
        photo_paths = []
        for file in request.files.getlist('photos[]'):
            if file and len(photo_paths) < 4:
                path = save_and_prepare_image(file)
                photo_paths.append(path)
                upload_to_drive(os.path.basename(path), path)

        # Generate PDF
        pdf_io = generate_pdf(data, invitation_path, photo_paths)

        # Save & Upload PDF
        pdf_filename = f"{data['title']}_{data['date']}.pdf"
        local_pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename)
        with open(local_pdf_path, 'wb') as f:
            f.write(pdf_io.getvalue())
        upload_to_drive(pdf_filename, local_pdf_path)

        # Store for download in session and redirect to success
        session['pdf_filename'] = pdf_filename
        return redirect(url_for('success'))

    return render_template('index.html')

@app.route('/success')
def success():
    pdf_filename = session.get('pdf_filename')
    return render_template('success.html', pdf_filename=pdf_filename)

@app.route('/download/<filename>')
def download(filename):
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    return send_file(path, download_name=filename, as_attachment=True)

def upload_to_drive(name, path):
    file_metadata = {'name': name, 'parents': [GOOGLE_DRIVE_FOLDER_ID]}
    media = MediaFileUpload(path, resumable=True)
    uploaded = drive_service.files().create(
        body=file_metadata, media_body=media, fields='id').execute()
    print(f"Uploaded {name} with ID {uploaded.get('id')}")

def generate_pdf(data, invitation, photos):
    pdf = PDF()
    pdf.set_margins(10, 10, 10)
    pdf.add_font('DejaVu', '', 'fonts/ttf/DejaVuSans.ttf', uni=True)
    pdf.add_font('DejaVu', 'B', 'fonts/ttf/DejaVuSans-Bold.ttf', uni=True)
    pdf.add_font('DejaVu', 'I', 'fonts/ttf/DejaVuSans-Oblique.ttf', uni=True)
    pdf.add_font('DejaVu', 'BI', 'fonts/ttf/DejaVuSans-BoldOblique.ttf', uni=True)
    pdf.add_page()

    # Header
    pdf.set_font('DejaVu', 'B', 14)
    pdf.set_text_color(0, 0, 255)
    pdf.cell(0, 6, data['univ'], ln=True, align='C')
    pdf.set_font('DejaVu', 'B', 13)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 6, data['college'], ln=True, align='C')
    pdf.cell(0, 6, data['dept'], ln=True, align='C')
    pdf.ln(5)

    # Invitation image
    if invitation:
        pdf.image(invitation, x=10, w=190)
        pdf.ln(10)

    pdf.set_font('DejaVu', '', 11)
    pdf.cell(0, 6, f"Event: {data['title']}", ln=True)
    pdf.cell(0, 6, f"Type: {data['event_type']}", ln=True)
    pdf.cell(0, 6, f"Venue: {data['venue']}", ln=True)
    pdf.cell(0, 6, f"Date: {data['date']}", ln=True)
    pdf.cell(0, 6, f"Participant Count: {data['count']}", ln=True)
    pdf.cell(0, 6, f"Participant: {data['participant']}", ln=True)
    pdf.ln(5)

    # Event Description
    pdf.set_font('DejaVu', 'B', 12)
    pdf.cell(0, 8, "About the Event:", ln=True)
    pdf.set_font('DejaVu', '', 11)
    soup = BeautifulSoup(data['desc'], 'html.parser')
    for element in soup.find_all(['p', 'ul', 'ol', 'li', 'b', 'i']):
        pdf.multi_cell(0, 6, element.text.strip())
    pdf.ln(5)

    # Event Photos
    if photos:
        pdf.set_font('DejaVu', 'B', 12)
        pdf.cell(0, 10, "Event Photos", ln=True)
        for i, path in enumerate(photos):
            pdf.image(path, x=10, w=190, h=90)
            if i < len(data['photo_desc']):
                pdf.set_font('DejaVu', '', 10)
                pdf.multi_cell(0, 6, f"({data['photo_desc'][i].strip()})", align='C')
            pdf.ln(5)

    pdf_output = io.BytesIO()
    pdf_output.write(pdf.output(dest='S').encode('latin1'))
    pdf_output.seek(0)
    return pdf_output

def save_and_prepare_image(file):
    original_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(original_path)

    # Open image and convert to valid JPEG
    try:
        with Image.open(original_path) as img:
            rgb_im = img.convert('RGB')  # convert to RGB in case of PNG/other
            # Force .jpg extension
            jpg_path = os.path.splitext(original_path)[0] + '.jpg'
            rgb_im.save(jpg_path, 'JPEG')
    except Exception as e:
        print(f"Image conversion error: {e}")
        raise RuntimeError("Invalid image format. Please upload a valid image file.")

    # Remove the original uploaded file if it was not .jpg
    if jpg_path != original_path and os.path.exists(original_path):
        os.remove(original_path)

    return jpg_path


if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True)
