# 사용자 생성
python -c "from passlib.hash import bcrypt; print(bcrypt.hash('admin'))"
$2b$12$UxrhiHU9iSyr8w/P/QRHuedMeyLXW.LeuU6/e2/e4LXIf4WGhuKtO

# SECRET_KEY 생성
python -c "import secrets; print(secrets.token_hex(32))"   

INSERT INTO auth.app_user (login_id, name, password_hash, role)
VALUES ('admin', '시스템관리자', '$2b$12$xxxx...여기에복붙', 'operator');