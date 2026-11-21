
* 존재하는 파일들에 대한 권한
sudo setfacl -R -m u:bpmu:rX /data/sftp_log_backup

* 새로 생성될 파일들에 대한 권한(-> 이부분은 mv 로 이전된 파일의 경우 적용되지 않음)
sudo setfacl -R -d -m u:bpmu:rX /data/sftp_log_backup

* 권한확인
getfacl /data/sftp_log_backup


sudo setfacl -R -m u:eprocu:rX /data/sftp_log_backup

sudo setfacl -R -d -m u:eprocu:rX /data/sftp_log_backup

getfacl /data/sftp_log_backup


sudo setfacl -R -m u:ssru:rX /data/sftp_log_backup

sudo setfacl -R -d -m u:ssru:rX /data/sftp_log_backup

getfacl /data/sftp_log_backup


* 아래와 같이 mv이후 권한설정 추가(sftplogchecker.sh 파일 수정)
전자조달, PMS 동일(유저만 다름)
================================================================================
mv /var/log/sftp.log /data/sftp_log_backup/sftp/sftplog_`date +%Y%m%d`.log
touch /var/log/sftp.log
chown root:root /var/log/sftp.log
chmod 600 /var/log/sftp.log

cp /var/log/xferlog /var/log/xferlog_`date +%Y%m%d`.log
mv /var/log/xferlog_`date +%Y%m%d`.log /var/log/backup_xferlog/
mv /var/log/xferlog /data/sftp_log_backup/xferlog_`date +%Y%m%d`.log
setfacl -m u:bpmu:rX /data/sftp_log_backup/xferlog_`date +%Y%m%d`.log
touch /var/log/xferlog
chown root:root /var/log/xferlog
chmod 600 /var/log/xferlog

================================================================================
SR sftplogchecker.sh
================================================================================
mv /var/log/sftp.log /data/sftp_log_backup/sftp/sftplog_`date +%Y%m%d`.log
setfacl -m u:ssru:rX /data/sftp_log_backup/sftp/sftplog_`date +%Y%m%d`.log
touch /var/log/sftp.log
chown root:root /var/log/sftp.log
chmod 600 /var/log/sftp.log

cp /var/log/xferlog /var/log/xferlog_`date +%Y%m%d`.log
mv /var/log/xferlog_`date +%Y%m%d`.log /var/log/backup_xferlog/
mv /var/log/xferlog /data/sftp_log_backup/xferlog_`date +%Y%m%d`.log
touch /var/log/xferlog
chown root:root /var/log/xferlog
chmod 600 /var/log/xferlog
================================================================================