@echo off
title CampusOD - Automated Student OD and Leave Management System (MERN Stack)
echo =========================================================================
echo Starting CampusOD Application (Express + Node.js + React + MongoDB)...
echo =========================================================================
echo Initializing MongoDB database and demo accounts...
call npm run seed
echo.
echo Launching React Frontend and Express Backend concurrently...
start http://localhost:5173
npm run dev
pause
