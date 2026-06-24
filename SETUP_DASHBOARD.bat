@echo off
title Flipkart Dashboard - Auto Setup
color 0A
cls

echo ============================================================
echo    FLIPKART RTO/RVP DASHBOARD - AUTO SETUP
echo ============================================================
echo.

REM ── STEP 1: Set working folder ──────────────────────────────
set "FOLDER=C:\Users\tiwari.amit\OneDrive - Flipkart Internet Pvt. Ltd\Desktop\Resealing conversion"
cd /d "%FOLDER%"

echo [1/6] Checking files in folder...
echo.
dir /b
echo.

REM ── STEP 2: Check Git installed ─────────────────────────────
echo [2/6] Checking Git installation...
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  !! Git is NOT installed on this computer.
    echo  !! Opening Git download page now...
    echo  !! Please install Git, then double-click this file again.
    echo.
    start https://git-scm.com/download/win
    pause
    exit
)
echo  Git is installed OK
echo.

REM ── STEP 3: Create .streamlit folder if missing ─────────────
echo [3/6] Creating .streamlit folder...
if not exist ".streamlit" mkdir ".streamlit"
echo  Done
echo.

REM ── STEP 4: Git init ────────────────────────────────────────
echo [4/6] Initializing Git repository...
git init
git add .
git commit -m "Flipkart RTO RVP Resealing Dashboard - initial commit"
echo  Done
echo.

REM ── STEP 5: Open GitHub to create repo ──────────────────────
echo [5/6] Opening GitHub...
echo.
echo  ============================================================
echo   ACTION NEEDED - Do these 4 things in the browser:
echo  ============================================================
echo.
echo   1. Sign in to GitHub (or create free account)
echo   2. Fill in:
echo         Repository name:  flipkart-dashboard
echo         Visibility:       Private
echo   3. UNCHECK "Add README file"
echo   4. Click "Create repository"
echo.
echo   Then COME BACK HERE and press any key
echo  ============================================================
echo.
start https://github.com/new
pause

REM ── STEP 6: Ask for GitHub username ─────────────────────────
echo.
echo [6/6] Connecting to GitHub...
echo.
set /p GITHUB_USER=Enter your GitHub username (e.g. amittiwari): 
echo.

git remote add origin https://github.com/%GITHUB_USER%/flipkart-dashboard.git
git branch -M main
git push -u origin main

echo.
echo ============================================================
echo   FILES PUSHED TO GITHUB SUCCESSFULLY!
echo ============================================================
echo.
echo  Now opening Streamlit Cloud to deploy...
echo.
echo  ============================================================
echo   ACTION NEEDED in Streamlit:
echo  ============================================================
echo   1. Click "New app"
echo   2. Select repository:  flipkart-dashboard
echo   3. Main file path:     app.py
echo   4. Click "Advanced settings" then "Secrets"
echo   5. Paste your Google service account JSON
echo   6. Click "Deploy"
echo  ============================================================
echo.
start https://share.streamlit.io
echo.
echo  After deploying, copy your app URL and set up UptimeRobot:
start https://uptimerobot.com
echo.
echo ============================================================
echo   ALL DONE! Your dashboard will be live in 2-3 minutes.
echo ============================================================
echo.
pause
