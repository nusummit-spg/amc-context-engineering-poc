@echo off
set "JAVA_HOME=C:\Users\Laptopadmin\.Neo4jDesktop2\Cache\runtime\zulu21.50.19-ca-jre21.0.11-win_x64"
set "PATH=%JAVA_HOME%\bin;%PATH%"
call "C:\Users\Laptopadmin\.Neo4jDesktop2\Data\dbmss\dbms-49637bb0-9857-4a15-80ce-c71aa9f2ed6b\bin\neo4j.bat" console > "c:\Users\Laptopadmin\Desktop\context-engineering\logs\neo4j.log" 2>&1
