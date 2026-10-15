import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
from typing import Optional

class EmailService:
    """Email Service for sending verification codes and notifications."""
    
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_name = os.getenv("SMTP_FROM_NAME", "媒力 MediaFlow")
    
    async def send_verification_code(self, email: str, code: str, purpose: str) -> bool:
        """
        Send verification code email.
        
        Args:
            email: Recipient email address
            code: 6-digit verification code
            purpose: Purpose of verification (register, reset_password, etc.)
        
        Returns:
            bool: True if sent successfully, False otherwise
        """
        subject = "【媒力 MediaFlow】验证码"
        purpose_text = "注册" if purpose == "register" else "重置密码"
        
        body = f"""您的验证码是：{code}

5 分钟内有效，请勿泄露给他人。

如非本人操作，请忽略此邮件。"""
        
        msg = MIMEMultipart()
        msg['From'] = self.smtp_user
        msg['To'] = email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(1, max_retries + 1):
            try:
                print(f"[Email] Attempt {attempt}/{max_retries}: Sending to {email}")
                print(f"[Email] From: {self.smtp_user}")
                print(f"[Email] SMTP Server: {self.smtp_host}:{self.smtp_port}")
                
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_user, [email], msg.as_string())
                server.quit()
                
                print(f"[Email] 邮件发送成功：{email}")
                return True
                
            except smtplib.SMTPAuthenticationError as e:
                print(f"[Email] 认证失败 (尝试 {attempt}/{max_retries}): {e}")
                print(f"[Email] Check SMTP_USER and SMTP_PASSWORD credentials")
                if attempt < max_retries:
                    print(f"[Email] Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    return False
                    
            except smtplib.SMTPConnectError as e:
                print(f"[Email] 连接失败 (尝试 {attempt}/{max_retries}): {e}")
                print(f"[Email] Check SMTP_HOST and SMTP_PORT settings")
                if attempt < max_retries:
                    print(f"[Email] Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    return False
                    
            except Exception as e:
                print(f"[Email] 发送失败 (尝试 {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    print(f"[Email] Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    return False
        
        return False
