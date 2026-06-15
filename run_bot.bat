@echo off
cd /d "%~dp0"
nodemon --ext py --exec py -3.11 bot.py
