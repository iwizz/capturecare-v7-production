import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

server = smtplib.SMTP('smtp.gmail.com', 587)
server.starttls()
try:
    server.login('tim@iwizz.com.au', 'qdsg vaey yrkz vzjz')
    print('✅ SMTP login successful!')
    msg = MIMEMultipart()
    msg['From'] = 'tim@iwizz.com.au'
    msg['To'] = 'tim@iwizz.com.au'
    msg['Subject'] = 'CaptureCare Test Email'
    msg.attach(MIMEText('This is a test from CaptureCare local setup.', 'plain'))
    server.send_message(msg)
    print('✅ Test email sent to tim@iwizz.com.au! Check your inbox/spam.')
except Exception as e:
    print(f'❌ Error: {e}')
finally:
    server.quit()
