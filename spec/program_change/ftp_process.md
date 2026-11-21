PMS
cd /data/sftp_log_backup
cat *202604* | grep "/tomcat8/webapps/ROOT" | grep " _ i " | wc

SR FTP 조회
cd /data/sftp_log_backup/sftp
cat *202603* | grep "/tomcat8/webapps/P010" | grep "WRITE" | wc

SR 결과
Jan 27 16:40:56 pdssrw01 sftp-server[1209399]: open "/home/ssru/tomcat8/webapps/P010/WEB-INF/views/sr/srRequest.jsp" flags WRITE,CREATE,TRUNCATE mode 0666